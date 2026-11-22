package main

import (
	"bufio"
	"bytes"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

// capture runs tcpdump in the mock's network namespace. Every TCP packet to or
// from the dependency ports is captured (headers only), so connection attempts
// that never reach the application (S1, S2, S9) are visible, and S4 byte gaps
// can be verified on the wire.
type capture struct {
	cmd    *exec.Cmd
	stderr *bytes.Buffer
	mu     *sync.Mutex
	done   chan error
}

type captureStats struct {
	Captured   int    `json:"packets_captured"`
	Received   int    `json:"packets_received_by_filter"`
	DroppedKer int    `json:"packets_dropped_by_kernel"`
	Stderr     string `json:"tcpdump_stderr"`
}

// All packets of the dependency ports in S4 (byte gaps are verified on the
// wire); elsewhere only control segments (SYN, FIN, RST), which carry every
// connection attempt and close at a fraction of the volume (a client in a
// tight reconnect loop produces >20,000 attempts/s).
const captureFilterAll = "tcp and (port 9001 or port 9002 or port 9003)"
const captureFilterCtl = captureFilterAll + " and (tcp[tcpflags] & (tcp-syn|tcp-fin|tcp-rst) != 0)"

type lockedBuf struct {
	mu *sync.Mutex
	b  *bytes.Buffer
}

func (l lockedBuf) Write(p []byte) (int, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.b.Write(p)
}

func startCapture(iface, path string, all bool) (*capture, error) {
	filter := captureFilterCtl
	if all {
		filter = captureFilterAll
	}
	cmd := exec.Command("tcpdump", "-Z", "root", "-i", iface, "-n", "-U", "--immediate-mode", "-s", "128", "-B", "65536",
		"--time-stamp-precision=nano", "-w", path, filter)
	c := &capture{cmd: cmd, stderr: &bytes.Buffer{}, mu: &sync.Mutex{}, done: make(chan error, 1)}
	cmd.Stderr = lockedBuf{c.mu, c.stderr}
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	go func() { c.done <- cmd.Wait() }()
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		c.mu.Lock()
		s := c.stderr.String()
		c.mu.Unlock()
		if strings.Contains(s, "listening on") {
			return c, nil
		}
		select {
		case err := <-c.done:
			return nil, fmt.Errorf("tcpdump exited: %v: %s", err, s)
		case <-time.After(10 * time.Millisecond):
		}
	}
	cmd.Process.Kill()
	return nil, errors.New("tcpdump did not start listening within 10 s")
}

var reStat = regexp.MustCompile(`(\d+) packets? (captured|received by filter|dropped by kernel)`)

func (c *capture) stop() (*captureStats, error) {
	// Give in-flight packets (e.g. a final RST) a moment to be written.
	time.Sleep(300 * time.Millisecond)
	c.cmd.Process.Signal(syscall.SIGINT)
	var err error
	select {
	case err = <-c.done:
	case <-time.After(5 * time.Second):
		c.cmd.Process.Kill()
		err = errors.New("tcpdump did not exit on SIGINT")
	}
	c.mu.Lock()
	s := c.stderr.String()
	c.mu.Unlock()
	st := &captureStats{Stderr: s}
	for _, m := range reStat.FindAllStringSubmatch(s, -1) {
		n, _ := strconv.Atoi(m[1])
		switch m[2] {
		case "captured":
			st.Captured = n
		case "received by filter":
			st.Received = n
		case "dropped by kernel":
			st.DroppedKer = n
		}
	}
	var ee *exec.ExitError
	if errors.As(err, &ee) {
		err = nil // tcpdump exits non-zero on SIGINT in some builds
	}
	if st.DroppedKer > 0 {
		err = errors.Join(err, fmt.Errorf("%d packets dropped by kernel", st.DroppedKer))
	}
	// Integrity: every packet that matched the filter must be in the file.
	if st.Captured < st.Received {
		err = errors.Join(err, fmt.Errorf("capture incomplete: %d captured < %d received by filter", st.Captured, st.Received))
	}
	return st, err
}

// ---------------------------------------------------------------------------
// Minimal pcap reader (Ethernet / Linux SLL / SLL2, IPv4, TCP).

type packet struct {
	RealNS  int64
	SrcPort int
	DstPort int
	Src     string
	Dst     string
	Flags   uint8
	Seq     uint32
	Payload int
}

const (
	tcpFIN = 0x01
	tcpSYN = 0x02
	tcpRST = 0x04
	tcpPSH = 0x08
	tcpACK = 0x10
)

func readPcap(path string) ([]packet, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	r := bufio.NewReader(f)
	gh := make([]byte, 24)
	if _, err := io.ReadFull(r, gh); err != nil {
		return nil, fmt.Errorf("pcap header: %w", err)
	}
	var bo binary.ByteOrder = binary.LittleEndian
	magic := bo.Uint32(gh[0:4])
	nano := false
	switch magic {
	case 0xa1b2c3d4:
	case 0xa1b23c4d:
		nano = true
	default:
		bo = binary.BigEndian
		magic = bo.Uint32(gh[0:4])
		switch magic {
		case 0xa1b2c3d4:
		case 0xa1b23c4d:
			nano = true
		default:
			return nil, fmt.Errorf("bad pcap magic %x", gh[0:4])
		}
	}
	link := bo.Uint32(gh[20:24])
	var out []packet
	ph := make([]byte, 16)
	for {
		if _, err := io.ReadFull(r, ph); err != nil {
			if err == io.EOF || err == io.ErrUnexpectedEOF {
				return out, nil
			}
			return out, err
		}
		sec, frac := int64(bo.Uint32(ph[0:4])), int64(bo.Uint32(ph[4:8]))
		incl := bo.Uint32(ph[8:12])
		data := make([]byte, incl)
		if _, err := io.ReadFull(r, data); err != nil {
			return out, nil // truncated last record (capture stopped mid-write)
		}
		ts := sec*1e9 + frac
		if !nano {
			ts = sec*1e9 + frac*1e3
		}
		if p, ok := parseFrame(link, data); ok {
			p.RealNS = ts
			out = append(out, p)
		}
	}
}

func parseFrame(link uint32, d []byte) (packet, bool) {
	var ip []byte
	switch link {
	case 1: // Ethernet
		if len(d) < 14 {
			return packet{}, false
		}
		et := binary.BigEndian.Uint16(d[12:14])
		off := 14
		if et == 0x8100 && len(d) >= 18 {
			et, off = binary.BigEndian.Uint16(d[16:18]), 18
		}
		if et != 0x0800 {
			return packet{}, false
		}
		ip = d[off:]
	case 113: // Linux SLL
		if len(d) < 16 || binary.BigEndian.Uint16(d[14:16]) != 0x0800 {
			return packet{}, false
		}
		ip = d[16:]
	case 276: // Linux SLL2
		if len(d) < 20 || binary.BigEndian.Uint16(d[0:2]) != 0x0800 {
			return packet{}, false
		}
		ip = d[20:]
	default:
		return packet{}, false
	}
	if len(ip) < 20 || ip[0]>>4 != 4 || ip[9] != 6 {
		return packet{}, false
	}
	ihl := int(ip[0]&0x0f) * 4
	total := int(binary.BigEndian.Uint16(ip[2:4]))
	if len(ip) < ihl+20 {
		return packet{}, false
	}
	t := ip[ihl:]
	doff := int(t[12]>>4) * 4
	p := packet{
		Src:     fmt.Sprintf("%d.%d.%d.%d", ip[12], ip[13], ip[14], ip[15]),
		Dst:     fmt.Sprintf("%d.%d.%d.%d", ip[16], ip[17], ip[18], ip[19]),
		SrcPort: int(binary.BigEndian.Uint16(t[0:2])),
		DstPort: int(binary.BigEndian.Uint16(t[2:4])),
		Seq:     binary.BigEndian.Uint32(t[4:8]),
		Flags:   t[13],
		Payload: total - ihl - doff,
	}
	if p.Payload < 0 {
		p.Payload = 0
	}
	return p, true
}

// clockConv maps CLOCK_REALTIME (pcap) to CLOCK_MONOTONIC using the offsets
// sampled at run start and end (linear interpolation absorbs NTP slewing).
type clockConv struct{ a, b clockPair }

func newClockConv(a, b clockPair) clockConv { return clockConv{a, b} }

func (c clockConv) mono(real int64) int64 {
	oa := c.a.RealNS - c.a.MonoNS
	ob := c.b.RealNS - c.b.MonoNS
	if c.b.RealNS == c.a.RealNS {
		return real - oa
	}
	f := float64(real-c.a.RealNS) / float64(c.b.RealNS-c.a.RealNS)
	return real - (oa + int64(f*float64(ob-oa)))
}

type synRecord struct {
	TMono          int64  `json:"t"`
	TReal          int64  `json:"t_real_ns"`
	Src            string `json:"src"`
	SrcPort        int    `json:"src_port"`
	DstPort        int    `json:"dst_port"`
	Dep            string `json:"dep"`
	Seq            uint32 `json:"seq"`
	Attempt        int    `json:"attempt"`        // index of the new source port (1-based) per dst port
	Retransmission bool   `json:"retransmission"` // repeated SYN from an already seen source port
	Reply          string `json:"server_reply"`   // synack | rst | none
}

func depOfPort(port int) string {
	for _, p := range portTable {
		if p.Port == port {
			return p.Dep
		}
	}
	return ""
}

// writeSyns writes one record per client SYN (connection attempt) seen on
// the dependency ports: a new source port is a new attempt, a repeated SYN
// from the same source port a kernel retransmission.
func writeSyns(path string, pk []packet, conv clockConv) (int, error) {
	f, err := os.Create(path)
	if err != nil {
		return 0, err
	}
	defer f.Close()
	w := bufio.NewWriter(f)
	defer w.Flush()
	seen := map[string]bool{}
	attempts := map[int]int{}
	// server replies by (client port, server port)
	reply := map[string]string{}
	for _, p := range pk {
		if p.Flags&tcpSYN != 0 && p.Flags&tcpACK != 0 {
			reply[fmt.Sprintf("%d>%d", p.DstPort, p.SrcPort)] = "synack"
		} else if p.Flags&tcpRST != 0 && depOfPort(p.SrcPort) != "" {
			k := fmt.Sprintf("%d>%d", p.DstPort, p.SrcPort)
			if reply[k] == "" {
				reply[k] = "rst"
			}
		}
	}
	n := 0
	for _, p := range pk {
		if p.Flags&tcpSYN == 0 || p.Flags&tcpACK != 0 || depOfPort(p.DstPort) == "" {
			continue
		}
		k := fmt.Sprintf("%d>%d", p.SrcPort, p.DstPort)
		rec := synRecord{TMono: conv.mono(p.RealNS), TReal: p.RealNS, Src: p.Src, SrcPort: p.SrcPort, DstPort: p.DstPort,
			Dep: depOfPort(p.DstPort), Seq: p.Seq, Retransmission: seen[k], Reply: reply[k]}
		if rec.Reply == "" {
			rec.Reply = "none"
		}
		if !seen[k] {
			attempts[p.DstPort]++
			seen[k] = true
		}
		rec.Attempt = attempts[p.DstPort]
		b, _ := json.Marshal(rec)
		w.Write(b)
		w.WriteByte('\n')
		n++
	}
	return n, nil
}

type segment struct {
	TMono   int64 `json:"t"`
	DstPort int   `json:"client_port"`
	Payload int   `json:"payload"`
}

func serverDataSegments(pk []packet, port int, conv clockConv) []segment {
	var out []segment
	for _, p := range pk {
		if p.SrcPort == port && p.Payload > 0 {
			out = append(out, segment{conv.mono(p.RealNS), p.DstPort, p.Payload})
		}
	}
	return out
}
