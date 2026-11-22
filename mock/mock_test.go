package main

// Unit tests of the mock's byte-level behavior per scenario. They run the
// real server in-process on 127.0.0.1 (firewall and capture disabled; S1/S9
// and packet capture are covered by the container integration tests in
// tests/integration).

import (
	"bufio"
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

var (
	srv     *Server
	caPool  *x509.CertPool
	runCtr  int
	runMu   sync.Mutex
	dataDir string
)

// T0: a test-only write task, so that S8 (commit then reset) can be tested
// independently of the benchmark tasks.
type taskT0 struct{}

func (taskT0) ID() string                         { return "T0" }
func (taskT0) Deps() []string                     { return []string{"A", "B"} }
func (taskT0) DefaultFaultDep() string            { return "A" }
func (taskT0) NewState(*RunCtx, string) TaskState { return &t0State{} }

type t0State struct {
	mu sync.Mutex
	n  int
}

func (*t0State) Classify(dep string, r *Request) (string, bool) {
	return "thing:" + r.Path, r.Method == "POST"
}
func (s *t0State) Handle(dep string, r *Request) (*Response, []Effect) {
	if r.Method != "POST" {
		return jsonResp(200, map[string]string{"ok": "get"}), nil
	}
	s.mu.Lock()
	s.n++
	n := s.n
	s.mu.Unlock()
	return jsonResp(201, map[string]any{"created": n, "len": len(r.Body)}), []Effect{{Kind: "thing_created", Key: fmt.Sprint(n)}}
}

func TestMain(m *testing.M) {
	register(taskT0{})
	var err error
	dataDir, err = os.MkdirTemp("", "mocktest")
	if err != nil {
		panic(err)
	}
	tlsCfg, err := loadTLS("../certs/mock.pem", "../certs/mock-key.pem")
	if err != nil {
		panic(err)
	}
	ca, err := os.ReadFile("../certs/ca.pem")
	if err != nil {
		panic(err)
	}
	caPool = x509.NewCertPool()
	caPool.AppendCertsFromPEM(ca)
	srv = &Server{dataRoot: dataDir, tlsCfg: tlsCfg, fw: noFirewall{}, version: "test"}
	if err := srv.listenDeps("127.0.0.1"); err != nil {
		panic(err)
	}
	os.Exit(m.Run())
}

func start(t *testing.T, cfg RunConfig) *Run {
	t.Helper()
	runMu.Lock()
	runCtr++
	n := runCtr
	runMu.Unlock()
	if cfg.RunID == "" {
		cfg.RunID = fmt.Sprintf("t%d", n)
	}
	if cfg.OutDir == "" {
		cfg.OutDir = cfg.RunID
	}
	f := false
	cfg.Capture = &f
	r, err := srv.startRun(cfg)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if srv.current() == r {
			srv.finishRun()
		}
	})
	return r
}

func finish(t *testing.T) *RunSummary {
	t.Helper()
	s, err := srv.finishRun()
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func readJSONL(t *testing.T, r *Run, name string) []map[string]any {
	t.Helper()
	b, err := os.ReadFile(filepath.Join(r.dir, name))
	if err != nil {
		t.Fatal(err)
	}
	var out []map[string]any
	for _, l := range bytes.Split(bytes.TrimSpace(b), []byte("\n")) {
		if len(l) == 0 {
			continue
		}
		var m map[string]any
		if err := json.Unmarshal(l, &m); err != nil {
			t.Fatal(err)
		}
		out = append(out, m)
	}
	return out
}

func dialTLS(t *testing.T, port int, alpn ...string) *tls.Conn {
	t.Helper()
	if len(alpn) == 0 {
		alpn = []string{"http/1.1"}
	}
	c, err := tls.DialWithDialer(&net.Dialer{Timeout: 2 * time.Second}, "tcp", fmt.Sprintf("127.0.0.1:%d", port),
		&tls.Config{RootCAs: caPool, NextProtos: alpn})
	if err != nil {
		t.Fatal(err)
	}
	return c
}

type resp struct {
	status int
	hdr    http.Header
	body   []byte
	tHead  time.Duration
}

func roundTrip(t *testing.T, c net.Conn, raw string) (*resp, error) {
	t.Helper()
	t0 := time.Now()
	if _, err := io.WriteString(c, raw); err != nil {
		return nil, err
	}
	br := bufio.NewReader(c)
	hr, err := http.ReadResponse(br, nil)
	if err != nil {
		return nil, err
	}
	th := time.Since(t0)
	b, err := io.ReadAll(hr.Body)
	if err != nil {
		return nil, err
	}
	return &resp{hr.StatusCode, hr.Header, b, th}, nil
}

func get(path string) string {
	return "GET " + path + " HTTP/1.1\r\nHost: x\r\n\r\n"
}

// ---------------------------------------------------------------------------

func TestS0NormalLatencyDateALPN(t *testing.T) {
	r := start(t, RunConfig{Task: "R1", Scenario: "S0"})
	c := dialTLS(t, 9001, "h2", "http/1.1")
	defer c.Close()
	if p := c.ConnectionState().NegotiatedProtocol; p != "http/1.1" {
		t.Fatalf("ALPN = %q, want http/1.1", p)
	}
	for i := 0; i < 2; i++ { // keep-alive: two requests on one connection
		rs, err := roundTrip(t, c, get("/v1/users/u-042"))
		if err != nil {
			t.Fatal(err)
		}
		if rs.status != 200 || !strings.Contains(string(rs.body), `"id":"u-042"`) {
			t.Fatalf("got %d %s", rs.status, rs.body)
		}
		if rs.tHead < 140*time.Millisecond || rs.tHead > 250*time.Millisecond {
			t.Fatalf("latency %v, want ~150ms", rs.tHead)
		}
		if _, err := http.ParseTime(rs.hdr.Get("Date")); err != nil {
			t.Fatalf("Date header: %v", err)
		}
	}
	rs, _ := roundTrip(t, c, get("/v1/users/nobody"))
	if rs.status != 404 {
		t.Fatalf("unknown user: %d", rs.status)
	}
	finish(t)
	reqs := readJSONL(t, r, "requests.jsonl")
	if len(reqs) != 3 || reqs[0]["attempt"].(float64) != 1 || reqs[1]["attempt"].(float64) != 2 {
		t.Fatalf("requests log: %v", reqs)
	}
	if reqs[0]["conn_id"] != reqs[1]["conn_id"] {
		t.Fatal("keep-alive requests on different connections")
	}
}

func TestUpgradeH2cIgnored(t *testing.T) {
	start(t, RunConfig{Task: "R1", Scenario: "S0"})
	c := dialTLS(t, 9001)
	defer c.Close()
	rs, err := roundTrip(t, c, "GET /v1/users/u-001 HTTP/1.1\r\nHost: x\r\nConnection: Upgrade, HTTP2-Settings\r\nUpgrade: h2c\r\nHTTP2-Settings: AAMAAABkAAQCAAAAAAIAAAAA\r\n\r\n")
	if err != nil || rs.status != 200 {
		t.Fatalf("h2c upgrade request: %v %v", err, rs)
	}
	finish(t)
}

func TestChunkedAndExpectContinue(t *testing.T) {
	r := start(t, RunConfig{Task: "T0", Scenario: "S0"})
	c := dialTLS(t, 9001)
	defer c.Close()
	rs, err := roundTrip(t, c, "POST /x HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n6;ext=1\r\n world\r\n0\r\nTrailer: v\r\n\r\n")
	if err != nil || rs.status != 201 || !strings.Contains(string(rs.body), `"len":11`) {
		t.Fatalf("chunked: %v %+v", err, rs)
	}
	// Expect: 100-continue -> interim 100, then the final response.
	io.WriteString(c, "POST /y HTTP/1.1\r\nHost: x\r\nContent-Length: 3\r\nExpect: 100-continue\r\n\r\n")
	br := bufio.NewReader(c)
	c.SetReadDeadline(time.Now().Add(2 * time.Second))
	line, _ := br.ReadString('\n')
	if !strings.HasPrefix(line, "HTTP/1.1 100") {
		t.Fatalf("no 100 Continue: %q", line)
	}
	br.ReadString('\n')
	io.WriteString(c, "abc")
	hr, err := http.ReadResponse(br, nil)
	if err != nil || hr.StatusCode != 201 {
		t.Fatalf("after 100: %v", err)
	}
	finish(t)
	if n := len(readJSONL(t, r, "effects.jsonl")); n != 2 {
		t.Fatalf("effects = %d", n)
	}
}

// S2: TCP accepted, ClientHello read, nothing ever sent back.
func TestS2TLSStall(t *testing.T) {
	r := start(t, RunConfig{Task: "R1", Scenario: "S2"})
	raw, err := net.Dial("tcp", "127.0.0.1:9001")
	if err != nil {
		t.Fatal(err)
	}
	cnt := &countConn{Conn: raw}
	tc := tls.Client(cnt, &tls.Config{RootCAs: caPool, ServerName: "127.0.0.1"})
	tc.SetDeadline(time.Now().Add(3 * time.Second))
	t0 := time.Now()
	err = tc.Handshake()
	if err == nil || time.Since(t0) < 2900*time.Millisecond {
		t.Fatalf("handshake should stall: err=%v after %v", err, time.Since(t0))
	}
	if cnt.n != 0 {
		t.Fatalf("server sent %d bytes during TLS stall", cnt.n)
	}
	// Warm-up port of the same dependency is unaffected.
	w := dialTLS(t, 9101)
	rs, err := roundTrip(t, w, get("/v1/users/u-000"))
	if err != nil || rs.status != 200 {
		t.Fatalf("warm-up port affected: %v", err)
	}
	w.Close()
	raw.Close()
	finish(t)
	ev := readJSONL(t, r, "conns.jsonl")
	found := false
	for _, e := range ev {
		if e["ev"] == "raw_bytes" && e["port"].(float64) == 9001 && e["bytes"].(float64) > 0 {
			found = true
		}
	}
	if !found {
		t.Fatalf("ClientHello bytes not logged: %v", ev)
	}
}

type countConn struct {
	net.Conn
	n int
}

func (c *countConn) Read(b []byte) (int, error) {
	n, err := c.Conn.Read(b)
	c.n += n
	return n, err
}

// S3: request read, no response bytes, socket stays open; client close logged.
func TestS3ResponseStall(t *testing.T) {
	r := start(t, RunConfig{Task: "R1", Scenario: "S3"})
	c := dialTLS(t, 9001)
	io.WriteString(c, get("/v1/users/u-001"))
	c.SetReadDeadline(time.Now().Add(3 * time.Second))
	buf := make([]byte, 1)
	n, err := c.Read(buf)
	var ne net.Error
	if n != 0 || !errors.As(err, &ne) || !ne.Timeout() {
		t.Fatalf("expected read timeout with 0 bytes, got n=%d err=%v", n, err)
	}
	// a retry of the same logical call stalls too
	c2 := dialTLS(t, 9001)
	io.WriteString(c2, get("/v1/users/u-001"))
	c2.SetReadDeadline(time.Now().Add(1 * time.Second))
	if n, _ := c2.Read(buf); n != 0 {
		t.Fatal("retry was answered")
	}
	c.Close()
	c2.Close()
	time.Sleep(200 * time.Millisecond)
	finish(t)
	ev := readJSONL(t, r, "conns.jsonl")
	closed := 0
	for _, e := range ev {
		if e["ev"] == "closed" && e["reason"] == "peer_closed" {
			closed++
		}
	}
	if closed != 2 {
		t.Fatalf("client close not recorded: %v", ev)
	}
	rs := readJSONL(t, r, "responses.jsonl")
	if len(rs) != 2 || rs[0]["outcome"] != "stalled" {
		t.Fatalf("responses: %v", rs)
	}
}

// S4: headers at once (Content-Length 4096), then exactly one byte per 2 s.
func TestTrickleBodyLeadingPad(t *testing.T) {
	b := trickleBody([]byte(`{"a":1}`), 16)
	if string(b) != "         {\"a\":1}" || len(b) != 16 {
		t.Fatalf("got %q", b)
	}
	if b := trickleBody([]byte("0123456789"), 4); string(b) != "0123" {
		t.Fatalf("truncation: %q", b)
	}
}

func TestS4TrickleByteGaps(t *testing.T) {
	r := start(t, RunConfig{Task: "R1", Scenario: "S4"})
	c := dialTLS(t, 9001)
	defer c.Close()
	t0 := time.Now()
	io.WriteString(c, get("/v1/users/u-001"))
	br := bufio.NewReader(c)
	hr, err := http.ReadResponse(br, nil)
	if err != nil {
		t.Fatal(err)
	}
	tHead := time.Since(t0)
	if hr.ContentLength != 4096 || tHead > 300*time.Millisecond {
		t.Fatalf("headers: CL=%d after %v", hr.ContentLength, tHead)
	}
	var times []time.Time
	one := make([]byte, 64)
	for len(times) < 3 {
		c.SetReadDeadline(time.Now().Add(3 * time.Second))
		n, err := hr.Body.Read(one)
		if err != nil {
			t.Fatal(err)
		}
		if n != 1 {
			t.Fatalf("read %d bytes at once, want 1", n)
		}
		times = append(times, time.Now())
	}
	gaps := []time.Duration{times[0].Sub(t0) - tHead, times[1].Sub(times[0]), times[2].Sub(times[1])}
	for i, g := range gaps {
		if g < 1950*time.Millisecond || g > 2080*time.Millisecond {
			t.Fatalf("gap %d = %v, want 2 s", i, g)
		}
	}
	c.Close()
	time.Sleep(100 * time.Millisecond)
	finish(t)
	rs := readJSONL(t, r, "responses.jsonl")
	last := rs[len(rs)-1]
	if last["outcome"] == "complete" {
		t.Fatalf("trickle should not complete: %v", last)
	}
}

func TestS5TransientPerLogicalCall(t *testing.T) {
	for _, sc := range []string{"S5a", "S5b"} {
		t.Run(sc, func(t *testing.T) {
			start(t, RunConfig{Task: "R1", Scenario: sc})
			c := dialTLS(t, 9001)
			defer c.Close()
			for _, user := range []string{"u-001", "u-002"} {
				for i := 1; i <= 3; i++ {
					rs, err := roundTrip(t, c, get("/v1/users/"+user))
					if err != nil {
						t.Fatal(err)
					}
					want := 503
					if i == 3 {
						want = 200
					}
					if rs.status != want {
						t.Fatalf("%s attempt %d: %d", user, i, rs.status)
					}
					ra := rs.hdr.Get("Retry-After")
					if want == 503 && ((sc == "S5a" && ra != "") || (sc == "S5b" && ra != "1")) {
						t.Fatalf("Retry-After = %q in %s", ra, sc)
					}
				}
			}
			finish(t)
		})
	}
}

func TestS6RateLimit(t *testing.T) {
	t.Run("S6a", func(t *testing.T) {
		start(t, RunConfig{Task: "R1", Scenario: "S6a"})
		c := dialTLS(t, 9001)
		defer c.Close()
		rs, _ := roundTrip(t, c, get("/v1/users/u-001"))
		if rs.status != 429 || rs.hdr.Get("Retry-After") != "3" {
			t.Fatalf("got %d RA=%q", rs.status, rs.hdr.Get("Retry-After"))
		}
		rs, _ = roundTrip(t, c, get("/v1/users/u-001"))
		if rs.status != 200 {
			t.Fatalf("second attempt %d", rs.status)
		}
		finish(t)
	})
	t.Run("S6b", func(t *testing.T) {
		start(t, RunConfig{Task: "R1", Scenario: "S6b"})
		c := dialTLS(t, 9001)
		defer c.Close()
		rs, _ := roundTrip(t, c, get("/v1/users/u-001"))
		recv := time.Now()
		d, err1 := http.ParseTime(rs.hdr.Get("Date"))
		ra, err2 := http.ParseTime(rs.hdr.Get("Retry-After"))
		if rs.status != 429 || err1 != nil || err2 != nil || ra.Sub(d) != 3*time.Second {
			t.Fatalf("got %d Date=%q RA=%q", rs.status, rs.hdr.Get("Date"), rs.hdr.Get("Retry-After"))
		}
		// sent on a whole second: receipt is within a few ms after Date
		if off := recv.Sub(d); off < 0 || off > 60*time.Millisecond {
			t.Fatalf("429 not aligned to whole second: receipt-Date = %v", off)
		}
		finish(t)
	})
}

func TestS7OutageWindow(t *testing.T) {
	r := start(t, RunConfig{Task: "R1", Scenario: "S7", OutageS: 1.5})
	c := dialTLS(t, 9001)
	defer c.Close()
	t0 := time.Now()
	var statuses []int
	for time.Since(t0) < 2200*time.Millisecond {
		rs, err := roundTrip(t, c, get(fmt.Sprintf("/v1/users/u-%03d", len(statuses)%10)))
		if err != nil {
			t.Fatal(err)
		}
		if rs.hdr.Get("Retry-After") != "" {
			t.Fatal("S7 503 must not carry Retry-After")
		}
		statuses = append(statuses, rs.status)
	}
	if statuses[0] != 503 || statuses[len(statuses)-1] != 200 {
		t.Fatalf("statuses %v", statuses)
	}
	// monotone: 503...503 200...200
	for i := 1; i < len(statuses); i++ {
		if statuses[i-1] == 200 && statuses[i] == 503 {
			t.Fatalf("503 after recovery: %v", statuses)
		}
	}
	sum := finish(t)
	if sum.OutageFrom == 0 {
		t.Fatal("outage start not recorded")
	}
	for _, q := range readJSONL(t, r, "requests.jsonl") {
		rel := q["s7_t_since_outage_start_s"]
		f, _ := rel.(float64)
		if (q["fault"] == "503_outage") != (f < 1.5) {
			t.Fatalf("request at %.3fs fault=%v", f, q["fault"])
		}
	}
}

// S8: the effect is committed, then the connection is reset without a response.
func TestS8CommitThenReset(t *testing.T) {
	r := start(t, RunConfig{Task: "T0", Scenario: "S8"})
	c := dialTLS(t, 9001)
	_, err := roundTrip(t, c, "POST /pay HTTP/1.1\r\nHost: x\r\nContent-Length: 2\r\n\r\n{}")
	if err == nil || !(strings.Contains(err.Error(), "reset") || errors.Is(err, io.ErrUnexpectedEOF) || errors.Is(err, io.EOF)) {
		t.Fatalf("expected reset, got %v", err)
	}
	if !strings.Contains(err.Error(), "reset by peer") {
		t.Logf("note: client saw %v (RST may surface as EOF depending on timing)", err)
	}
	c.Close()
	c2 := dialTLS(t, 9001)
	defer c2.Close()
	rs, err := roundTrip(t, c2, "POST /pay HTTP/1.1\r\nHost: x\r\nContent-Length: 2\r\n\r\n{}")
	if err != nil || rs.status != 201 {
		t.Fatalf("retry: %v", err)
	}
	finish(t)
	eff := readJSONL(t, r, "effects.jsonl")
	if len(eff) != 2 {
		t.Fatalf("effects %v", eff)
	}
	rsp := readJSONL(t, r, "responses.jsonl")
	if rsp[0]["outcome"] != "reset" {
		t.Fatalf("responses %v", rsp)
	}
}

func TestFaultTargetsOnlyFaultedDependency(t *testing.T) {
	start(t, RunConfig{Task: "T0", Scenario: "S5a", FaultDep: "A"})
	b := dialTLS(t, 9002)
	defer b.Close()
	rs, err := roundTrip(t, b, "POST /z HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n")
	if err != nil || rs.status != 201 {
		t.Fatalf("dependency B affected: %v %v", err, rs)
	}
	// a dependency the task does not have answers 404
	cc := dialTLS(t, 9003)
	defer cc.Close()
	rs, _ = roundTrip(t, cc, get("/"))
	if rs.status != 404 {
		t.Fatalf("port of absent dependency: %d", rs.status)
	}
	finish(t)
}

func TestNeverOverwrite(t *testing.T) {
	start(t, RunConfig{Task: "R1", Scenario: "S0", RunID: "dup", OutDir: "dup"})
	c := dialTLS(t, 9001)
	roundTrip(t, c, get("/v1/users/u-001"))
	c.Close()
	finish(t)
	f := false
	if _, err := srv.startRun(RunConfig{Task: "R1", Scenario: "S0", RunID: "dup2", OutDir: "dup", Capture: &f}); err == nil {
		srv.finishRun()
		t.Fatal("run into a non-empty out_dir was accepted")
	}
	if _, err := srv.startRun(RunConfig{Task: "R1", Scenario: "S0", RunID: "x", OutDir: "../escape", Capture: &f}); err == nil {
		srv.finishRun()
		t.Fatal("out_dir escape accepted")
	}
}

func TestStrayConnectionBetweenRuns(t *testing.T) {
	before := srv.strays.Load()
	c, err := net.Dial("tcp", "127.0.0.1:9001")
	if err != nil {
		t.Fatal(err)
	}
	c.SetReadDeadline(time.Now().Add(time.Second))
	_, err = c.Read(make([]byte, 1))
	c.Close()
	if err == nil {
		t.Fatal("stray connection was served")
	}
	time.Sleep(50 * time.Millisecond)
	if srv.strays.Load() != before+1 {
		t.Fatal("stray not counted")
	}
}

// ---------------------------------------------------------------------------
// pcap parsing and SYN attribution on a synthetic capture.

func frame(src, dst int, flags uint8, payload int) []byte {
	ip := make([]byte, 20+20+payload)
	ip[0] = 0x45
	binary.BigEndian.PutUint16(ip[2:4], uint16(len(ip)))
	ip[9] = 6
	copy(ip[12:16], []byte{10, 77, 0, 3})
	copy(ip[16:20], []byte{10, 77, 0, 2})
	tcp := ip[20:]
	binary.BigEndian.PutUint16(tcp[0:2], uint16(src))
	binary.BigEndian.PutUint16(tcp[2:4], uint16(dst))
	tcp[12] = 5 << 4
	tcp[13] = flags
	eth := make([]byte, 14)
	binary.BigEndian.PutUint16(eth[12:14], 0x0800)
	return append(eth, ip...)
}

func TestPcapSynAttribution(t *testing.T) {
	var buf bytes.Buffer
	gh := make([]byte, 24)
	binary.LittleEndian.PutUint32(gh[0:4], 0xa1b23c4d)
	binary.LittleEndian.PutUint32(gh[16:20], 128)
	binary.LittleEndian.PutUint32(gh[20:24], 1)
	buf.Write(gh)
	add := func(sec int64, f []byte) {
		ph := make([]byte, 16)
		binary.LittleEndian.PutUint32(ph[0:4], uint32(sec))
		binary.LittleEndian.PutUint32(ph[8:12], uint32(len(f)))
		binary.LittleEndian.PutUint32(ph[12:16], uint32(len(f)))
		buf.Write(ph)
		buf.Write(f)
	}
	add(100, frame(40000, 9001, tcpSYN, 0))
	add(101, frame(40000, 9001, tcpSYN, 0)) // kernel retransmission
	add(103, frame(40001, 9001, tcpSYN, 0)) // new attempt
	add(103, frame(9001, 40001, tcpRST|tcpACK, 0))
	add(104, frame(9001, 40001, tcpPSH|tcpACK, 7)) // data segment
	add(105, frame(40002, 9101, tcpSYN, 0))        // warm-up port: counted under dep A port 9101
	p := filepath.Join(t.TempDir(), "x.pcap")
	os.WriteFile(p, buf.Bytes(), 0o644)
	pk, err := readPcap(p)
	if err != nil || len(pk) != 6 {
		t.Fatalf("readPcap: %v %d", err, len(pk))
	}
	conv := newClockConv(clockPair{RealNS: 0, MonoNS: 0}, clockPair{RealNS: 1000e9, MonoNS: 1000e9})
	out := filepath.Join(t.TempDir(), "syns.jsonl")
	n, err := writeSyns(out, pk, conv)
	if err != nil || n != 4 {
		t.Fatalf("syns: %v n=%d", err, n)
	}
	b, _ := os.ReadFile(out)
	lines := strings.Split(strings.TrimSpace(string(b)), "\n")
	var recs []synRecord
	for _, l := range lines {
		var s synRecord
		json.Unmarshal([]byte(l), &s)
		recs = append(recs, s)
	}
	if recs[0].Attempt != 1 || recs[0].Retransmission || recs[1].Attempt != 1 || !recs[1].Retransmission ||
		recs[2].Attempt != 2 || recs[2].Reply != "rst" || recs[0].Reply != "none" {
		t.Fatalf("attribution: %+v", recs)
	}
	segs := serverDataSegments(pk, 9001, conv)
	if len(segs) != 1 || segs[0].Payload != 7 {
		t.Fatalf("segments %+v", segs)
	}
}

func TestClockConv(t *testing.T) {
	c := newClockConv(clockPair{RealNS: 1000, MonoNS: 10}, clockPair{RealNS: 2000, MonoNS: 1012})
	if got := c.mono(1000); got != 10 {
		t.Fatal(got)
	}
	if got := c.mono(2000); got != 1012 {
		t.Fatal(got)
	}
	if got := c.mono(1500); got != 511 {
		t.Fatal(got)
	}
}
