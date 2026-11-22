package main

import (
	"bytes"
	"fmt"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
)

// firewall manages nftables rules inside the mock's network namespace.
// Base table (installed once):
//   - control port unreachable from the solution's interface,
//   - no forwarding (the mock is never a router to the control network),
//   - an empty "fault" chain into which S1/S9 rules are placed per run.
type firewall interface {
	setup(intIface string, ctlPort int) error
	setFault(rule string) error
	listFault() (string, error)
	// SYN counters (exact, never dropped) per dependency port, reset per run.
	resetCounters() error
	readCounters() (map[int]int64, error)
}

type nftFirewall struct{}

func nft(script string) (string, error) {
	cmd := exec.Command("nft", "-f", "-")
	cmd.Stdin = strings.NewReader(script)
	var out bytes.Buffer
	cmd.Stdout, cmd.Stderr = &out, &out
	err := cmd.Run()
	if err != nil {
		return out.String(), fmt.Errorf("nft: %v: %s", err, out.String())
	}
	return out.String(), nil
}

func (nftFirewall) setup(intIface string, ctlPort int) error {
	_, err := nft(fmt.Sprintf(`
table inet lcr
delete table inet lcr
table inet lcr {
  chain fault {
  }
  counter syn9001 {
  }
  counter syn9002 {
  }
  counter syn9003 {
  }
  chain input {
    type filter hook input priority -10; policy accept;
    iifname "%s" tcp dport %d drop
    iifname "%s" tcp dport 9001 tcp flags & (syn | ack) == syn counter name "syn9001"
    iifname "%s" tcp dport 9002 tcp flags & (syn | ack) == syn counter name "syn9002"
    iifname "%s" tcp dport 9003 tcp flags & (syn | ack) == syn counter name "syn9003"
    iifname "%s" jump fault
  }
  chain forward {
    type filter hook forward priority 0; policy drop;
  }
}
`, intIface, ctlPort, intIface, intIface, intIface, intIface))
	return err
}

func (nftFirewall) resetCounters() error {
	_, err := nft("reset counters table inet lcr\n")
	return err
}

var reCounter = regexp.MustCompile(`counter syn(\d+) \{\s*packets (\d+) bytes`)

func (nftFirewall) readCounters() (map[int]int64, error) {
	out, err := exec.Command("nft", "list", "counters", "table", "inet", "lcr").CombinedOutput()
	if err != nil {
		return nil, fmt.Errorf("nft list counters: %v: %s", err, out)
	}
	m := map[int]int64{}
	for _, x := range reCounter.FindAllStringSubmatch(string(out), -1) {
		p, _ := strconv.Atoi(x[1])
		n, _ := strconv.ParseInt(x[2], 10, 64)
		m[p] = n
	}
	return m, nil
}

func (nftFirewall) setFault(rule string) error {
	s := "flush chain inet lcr fault\n"
	if rule != "" {
		s += "add rule inet lcr fault " + rule + "\n"
	}
	_, err := nft(s)
	return err
}

func (nftFirewall) listFault() (string, error) {
	out, err := exec.Command("nft", "list", "chain", "inet", "lcr", "fault").CombinedOutput()
	return string(out), err
}

// noFirewall is used by in-process unit tests (no NET_ADMIN).
type noFirewall struct{}

func (noFirewall) setup(string, int) error              { return nil }
func (noFirewall) setFault(rule string) error           { return nil }
func (noFirewall) listFault() (string, error)           { return "(firewall disabled)", nil }
func (noFirewall) resetCounters() error                 { return nil }
func (noFirewall) readCounters() (map[int]int64, error) { return nil, nil }
