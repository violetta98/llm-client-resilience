package main

import (
	"bufio"
	"crypto/tls"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// Ports: one per dependency of a task (faults target these) and a separate,
// always-normal copy of each dependency for the driver's warm-up call.
type portInfo struct {
	Port int    `json:"port"`
	Role string `json:"role"` // "dep" | "warmup"
	Dep  string `json:"dep"`  // "A" | "B" | "C"
}

var portTable = []portInfo{
	{9001, "dep", "A"}, {9002, "dep", "B"}, {9003, "dep", "C"},
	{9101, "warmup", "A"}, {9102, "warmup", "B"}, {9103, "warmup", "C"},
}

func depPort(dep string) int {
	for _, p := range portTable {
		if p.Role == "dep" && p.Dep == dep {
			return p.Port
		}
	}
	return 0
}

// Scenario variants of draft Table III (11 per solution, 12 with S8).
var scenarios = map[string]bool{
	"S0": true, "S1": true, "S2": true, "S3": true, "S4": true,
	"S5a": true, "S5b": true, "S6a": true, "S6b": true, "S7": true, "S8": true, "S9": true,
}

type RunConfig struct {
	RunID    string `json:"run_id"`
	Task     string `json:"task"`
	Scenario string `json:"scenario"`
	FaultDep string `json:"fault_dep,omitempty"` // default: task's DefaultFaultDep
	OutDir   string `json:"out_dir"`             // relative to the data root; must be new

	// Scenario parameters (defaults = draft Table III; overridable only for
	// harness unit tests, and every run records the values used).
	LatencyMS         int     `json:"latency_ms"`
	OutageS           float64 `json:"outage_s"`
	TrickleIntervalMS int     `json:"trickle_interval_ms"`
	TrickleLen        int     `json:"trickle_len"`
	RetryAfterS       int     `json:"retry_after_s"`
	Capture           *bool   `json:"capture,omitempty"`
}

func (c *RunConfig) applyDefaults(t Task) {
	if c.FaultDep == "" {
		c.FaultDep = t.DefaultFaultDep()
	}
	if c.LatencyMS == 0 {
		c.LatencyMS = 150
	}
	if c.OutageS == 0 {
		c.OutageS = 30
	}
	if c.TrickleIntervalMS == 0 {
		c.TrickleIntervalMS = 2000
	}
	if c.TrickleLen == 0 {
		c.TrickleLen = 4096
	}
	if c.RetryAfterS == 0 {
		c.RetryAfterS = 3
	}
	if c.Capture == nil {
		t := true
		c.Capture = &t
	}
}

type Run struct {
	Cfg   RunConfig
	task  Task
	deps  map[string]bool
	state map[string]TaskState // by role

	dir string

	mu       sync.Mutex
	attempts map[string]int
	conns    map[int64]net.Conn

	connSeq          atomic.Int64
	reqSeq           atomic.Int64
	firstFaultAccept atomic.Int64

	wg   sync.WaitGroup
	done chan struct{}

	lConns, lReqs, lResps, lEffects *jsonl

	StartPair clockPair
	capture   *capture
	fwRules   string
}

func (r *Run) isDone() bool {
	select {
	case <-r.done:
		return true
	default:
		return false
	}
}

// sleep waits d or until the run is finished; returns false if interrupted.
func (r *Run) sleep(d time.Duration) bool {
	if d <= 0 {
		return true
	}
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-t.C:
		return true
	case <-r.done:
		return false
	}
}

func (r *Run) addConn(c net.Conn) (int64, bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.isDone() {
		return 0, false
	}
	id := r.connSeq.Add(1)
	r.conns[id] = c
	r.wg.Add(1)
	return id, true
}

func (r *Run) dropConn(id int64) {
	r.mu.Lock()
	delete(r.conns, id)
	r.mu.Unlock()
	r.wg.Done()
}

// bumpAttempt counts requests per logical call (all requests) and, separately,
// faulted-request attempts (the fault rules of S5/S6/S8 count these).
func (r *Run) bumpAttempt(role, dep, key string, target bool) (int, int) {
	if key == "" {
		return 0, 0
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	k := role + "|" + dep + "|" + key
	r.attempts[k]++
	ta := 0
	if target {
		r.attempts["target|"+k]++
		ta = r.attempts["target|"+k]
	}
	return r.attempts[k], ta
}

type Server struct {
	dataRoot string
	tlsCfg   *tls.Config
	fw       firewall
	capIface string
	version  string

	mu      sync.Mutex
	run     *Run
	strays  atomic.Int64
	started int64
}

func (s *Server) current() *Run {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.run
}

func safeRel(p string) bool {
	if p == "" || filepath.IsAbs(p) {
		return false
	}
	c := filepath.Clean(p)
	return c != "." && !strings.HasPrefix(c, "..")
}

func (s *Server) startRun(cfg RunConfig) (*Run, error) {
	t, ok := registry[cfg.Task]
	if !ok {
		return nil, fmt.Errorf("unknown task %q (known: %v)", cfg.Task, taskIDs())
	}
	if !scenarios[cfg.Scenario] {
		return nil, fmt.Errorf("unknown scenario %q", cfg.Scenario)
	}
	if cfg.RunID == "" {
		return nil, errors.New("run_id required")
	}
	if !safeRel(cfg.OutDir) {
		return nil, fmt.Errorf("out_dir must be a relative path inside the data root")
	}
	cfg.applyDefaults(t)
	deps := map[string]bool{}
	for _, d := range t.Deps() {
		deps[d] = true
	}
	if !deps[cfg.FaultDep] {
		return nil, fmt.Errorf("task %s has no dependency %q", t.ID(), cfg.FaultDep)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.run != nil {
		return nil, fmt.Errorf("run %s still active", s.run.Cfg.RunID)
	}
	dir := filepath.Join(s.dataRoot, cfg.OutDir)
	if ents, err := os.ReadDir(dir); err == nil && len(ents) > 0 {
		return nil, fmt.Errorf("out_dir %s exists and is not empty (raw data is never overwritten)", cfg.OutDir)
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, err
	}
	r := &Run{
		Cfg: cfg, task: t, deps: deps, dir: dir,
		attempts: map[string]int{}, conns: map[int64]net.Conn{},
		done: make(chan struct{}),
	}
	rc := &RunCtx{RunID: cfg.RunID}
	r.state = map[string]TaskState{"dep": t.NewState(rc, "dep"), "warmup": t.NewState(rc, "warmup")}
	var err error
	for _, x := range []struct {
		p    **jsonl
		name string
	}{{&r.lConns, "conns.jsonl"}, {&r.lReqs, "requests.jsonl"}, {&r.lResps, "responses.jsonl"}, {&r.lEffects, "effects.jsonl"}} {
		if *x.p, err = openJSONL(dir, x.name); err != nil {
			return nil, err
		}
	}
	// Firewall rules for connection-level faults are in place before the
	// solution container starts, so they apply from the start of the run.
	port := depPort(cfg.FaultDep)
	switch cfg.Scenario {
	case "S1":
		r.fwRules = fmt.Sprintf("tcp dport %d drop", port)
	case "S9":
		r.fwRules = fmt.Sprintf("tcp dport %d reject with tcp reset", port)
	}
	if err := s.fw.setFault(r.fwRules); err != nil {
		return nil, fmt.Errorf("firewall: %w", err)
	}
	if err := s.fw.resetCounters(); err != nil {
		return nil, fmt.Errorf("firewall counters: %w", err)
	}
	if *cfg.Capture && s.capIface != "" {
		c, err := startCapture(s.capIface, filepath.Join(dir, "capture.pcap"), cfg.Scenario == "S4")
		if err != nil {
			s.fw.setFault("")
			return nil, fmt.Errorf("capture: %w", err)
		}
		r.capture = c
	}
	r.StartPair = sampleClockPair()
	s.run = r
	return r, nil
}

type RunSummary struct {
	RunID      string         `json:"run_id"`
	Config     RunConfig      `json:"config"`
	Version    string         `json:"mock_version"`
	StartPair  clockPair      `json:"start_clock"`
	EndPair    clockPair      `json:"end_clock"`
	FwRules    string         `json:"fault_firewall_rules"`
	FwListing  string         `json:"firewall_listing_at_finish"`
	Counts     map[string]int `json:"counts"`
	Capture    *captureStats  `json:"capture,omitempty"`
	OutageFrom int64          `json:"s7_outage_start_mono_ns,omitempty"`
	Strays     int64          `json:"stray_connections_between_runs"`
	S4Segments []segment      `json:"s4_server_data_segments,omitempty"`
	SynCounts  map[int]int64  `json:"syn_packets_nft,omitempty"` // exact SYN count per port (incl. retransmissions)
	Errors     []string       `json:"errors,omitempty"`
}

func (s *Server) finishRun() (*RunSummary, error) {
	s.mu.Lock()
	r := s.run
	s.mu.Unlock()
	if r == nil {
		return nil, errors.New("no active run")
	}
	sum := &RunSummary{RunID: r.Cfg.RunID, Config: r.Cfg, Version: s.version, StartPair: r.StartPair,
		FwRules: r.fwRules, Counts: map[string]int{}, Strays: s.strays.Load()}
	sum.FwListing, _ = s.fw.listFault()
	if c, err := s.fw.readCounters(); err != nil {
		sum.Errors = append(sum.Errors, err.Error())
	} else {
		sum.SynCounts = c
	}
	close(r.done)
	r.mu.Lock()
	for _, c := range r.conns {
		c.Close()
	}
	r.mu.Unlock()
	waitCh := make(chan struct{})
	go func() { r.wg.Wait(); close(waitCh) }()
	select {
	case <-waitCh:
	case <-time.After(3 * time.Second):
		sum.Errors = append(sum.Errors, "connection goroutines did not finish within 3 s")
	}
	sum.EndPair = sampleClockPair()
	if err := s.fw.setFault(""); err != nil {
		sum.Errors = append(sum.Errors, "firewall reset: "+err.Error())
	}
	sum.OutageFrom = r.firstFaultAccept.Load()
	if r.Cfg.Scenario != "S7" {
		sum.OutageFrom = 0
	}
	sum.Counts["conns"] = r.lConns.Close()
	sum.Counts["requests"] = r.lReqs.Close()
	sum.Counts["responses"] = r.lResps.Close()
	sum.Counts["effects"] = r.lEffects.Close()
	if r.capture != nil {
		st, err := r.capture.stop()
		if err != nil {
			sum.Errors = append(sum.Errors, "capture stop: "+err.Error())
		}
		sum.Capture = st
		pk, err := readPcap(filepath.Join(r.dir, "capture.pcap"))
		if err != nil {
			sum.Errors = append(sum.Errors, "pcap parse: "+err.Error())
		} else {
			conv := newClockConv(r.StartPair, sum.EndPair)
			n, err := writeSyns(filepath.Join(r.dir, "syns.jsonl"), pk, conv)
			if err != nil {
				sum.Errors = append(sum.Errors, "syns: "+err.Error())
			}
			sum.Counts["syns"] = n
			sum.Counts["packets"] = len(pk)
			if r.Cfg.Scenario == "S4" {
				sum.S4Segments = serverDataSegments(pk, depPort(r.Cfg.FaultDep), conv)
			}
		}
	}
	if err := writeJSON(filepath.Join(r.dir, "run.json"), sum); err != nil {
		sum.Errors = append(sum.Errors, "run.json: "+err.Error())
	}
	s.mu.Lock()
	s.run = nil
	s.mu.Unlock()
	return sum, nil
}

// ---------------------------------------------------------------------------
// Dependency connections

func (s *Server) serve(ln net.Listener, p portInfo) {
	for {
		c, err := ln.Accept()
		if err != nil {
			if errors.Is(err, net.ErrClosed) {
				return
			}
			time.Sleep(10 * time.Millisecond)
			continue
		}
		go s.serveConn(c.(*net.TCPConn), p)
	}
}

func remotePort(c net.Conn) int {
	if a, ok := c.RemoteAddr().(*net.TCPAddr); ok {
		return a.Port
	}
	return 0
}

type connEvent struct {
	RunID   string `json:"run_id"`
	Ev      string `json:"ev"` // accept | tls_ok | tls_error | raw_bytes | closed
	T       int64  `json:"t"`
	ConnID  int64  `json:"conn_id"`
	Port    int    `json:"port"`
	Role    string `json:"role"`
	Dep     string `json:"dep"`
	SrcPort int    `json:"src_port,omitempty"`
	TLSVer  string `json:"tls_version,omitempty"`
	ALPN    string `json:"alpn,omitempty"`
	SNI     string `json:"sni,omitempty"`
	Bytes   int64  `json:"bytes,omitempty"`
	Reason  string `json:"reason,omitempty"`
	Note    string `json:"note,omitempty"`
}

func (s *Server) serveConn(c *net.TCPConn, p portInfo) {
	tAccept := monoNS()
	r := s.current()
	if r == nil {
		s.strays.Add(1)
		c.SetLinger(0)
		c.Close()
		return
	}
	cid, ok := r.addConn(c)
	if !ok {
		c.Close()
		return
	}
	defer r.dropConn(cid)
	c.SetNoDelay(true)
	faulted := p.Role == "dep" && p.Dep == r.Cfg.FaultDep
	if faulted {
		r.firstFaultAccept.CompareAndSwap(0, tAccept)
	}
	ev := func(e connEvent) {
		e.RunID, e.ConnID, e.Port, e.Role, e.Dep = r.Cfg.RunID, cid, p.Port, p.Role, p.Dep
		if e.T == 0 {
			e.T = monoNS()
		}
		r.lConns.Write(e)
	}
	ev(connEvent{Ev: "accept", T: tAccept, SrcPort: remotePort(c)})
	closeReason := "server_closed"
	defer func() {
		c.Close()
		ev(connEvent{Ev: "closed", Reason: closeReason})
	}()

	if faulted && r.Cfg.Scenario == "S2" {
		// TLS stall: TCP accepted, ClientHello read and discarded, nothing sent.
		buf := make([]byte, 4096)
		var total int64
		first := true
		for {
			n, err := c.Read(buf)
			if n > 0 {
				total += int64(n)
				if first {
					ev(connEvent{Ev: "raw_bytes", Bytes: int64(n), Note: "first bytes (ClientHello) received; no reply by design"})
					first = false
				}
			}
			if err != nil {
				closeReason = classifyReadErr(err, r)
				ev(connEvent{Ev: "raw_bytes", Bytes: total, Note: "total bytes received while stalled"})
				return
			}
		}
	}

	tc := tls.Server(c, s.tlsCfg)
	if err := tc.Handshake(); err != nil {
		closeReason = "tls_error"
		ev(connEvent{Ev: "tls_error", Reason: err.Error()})
		return
	}
	cs := tc.ConnectionState()
	ev(connEvent{Ev: "tls_ok", TLSVer: tls.VersionName(cs.Version), ALPN: cs.NegotiatedProtocol, SNI: cs.ServerName})

	br := bufio.NewReaderSize(tc, 32<<10)
	for seq := 1; ; seq++ {
		req, err := readRequest(br, monoNS, func(q *Request) error {
			if strings.EqualFold(q.Get("Expect"), "100-continue") {
				_, err := tc.Write([]byte("HTTP/1.1 100 Continue\r\n\r\n"))
				return err
			}
			return nil
		})
		if err != nil {
			if errors.Is(err, errNoRequest) {
				closeReason = classifyReadErr(err, r)
				if closeReason == "server_closed" {
					closeReason = "peer_closed"
				}
				return
			}
			closeReason = "bad_request"
			ev(connEvent{Ev: "bad_request", Reason: err.Error()})
			if req != nil && req.TFirstByte != 0 && !r.isDone() {
				tc.Write(headBytes(400, nil, 0, true, time.Now()))
			}
			return
		}
		keep, reason := s.handle(r, p, cid, seq, tc, c, br, req)
		if !keep {
			closeReason = reason
			if r.isDone() {
				closeReason = "run_finished"
			}
			return
		}
	}
}

func classifyReadErr(err error, r *Run) string {
	if r.isDone() {
		return "run_finished"
	}
	if errors.Is(err, io.EOF) || errors.Is(err, errNoRequest) {
		return "peer_closed"
	}
	if strings.Contains(err.Error(), "reset by peer") {
		return "peer_reset"
	}
	return "read_error: " + err.Error()
}

type reqRecord struct {
	RunID         string   `json:"run_id"`
	ReqID         int64    `json:"req_id"`
	ConnID        int64    `json:"conn_id"`
	Seq           int      `json:"seq_on_conn"`
	Port          int      `json:"port"`
	Role          string   `json:"role"`
	Dep           string   `json:"dep"`
	TFirst        int64    `json:"t_first_byte"`
	THeaders      int64    `json:"t_headers"`
	TDone         int64    `json:"t_done"`
	Method        string   `json:"method"`
	Target        string   `json:"target"`
	Path          string   `json:"path"`
	Query         string   `json:"query,omitempty"`
	Proto         string   `json:"proto"`
	Headers       []Header `json:"headers"`
	Body          Body     `json:"body"`
	Chunked       bool     `json:"chunked,omitempty"`
	Key           string   `json:"logical_key,omitempty"`
	Target4       bool     `json:"faulted_request"`
	Attempt       int      `json:"attempt,omitempty"`
	TargetAttempt int      `json:"faulted_request_attempt,omitempty"`
	Fault         string   `json:"fault,omitempty"`
	OutageRel     float64  `json:"s7_t_since_outage_start_s,omitempty"`
}

type respRecord struct {
	RunID        string   `json:"run_id"`
	ReqID        int64    `json:"req_id"`
	ConnID       int64    `json:"conn_id"`
	Fault        string   `json:"fault,omitempty"`
	Status       int      `json:"status,omitempty"`
	Headers      []Header `json:"headers,omitempty"`
	Body         *Body    `json:"body,omitempty"`
	THeadStart   int64    `json:"t_head_start,omitempty"`
	THeadSent    int64    `json:"t_head_sent,omitempty"`
	TBodyDone    int64    `json:"t_body_done,omitempty"`
	TEnd         int64    `json:"t_end"`
	Outcome      string   `json:"outcome"` // complete | stalled | reset | trickle_aborted | write_error | run_finished
	BytesWritten int      `json:"body_bytes_written"`
	TrickleTimes []int64  `json:"trickle_write_times,omitempty"`
	Error        string   `json:"error,omitempty"`
}

type effectRecord struct {
	RunID  string `json:"run_id"`
	T      int64  `json:"t"`
	ReqID  int64  `json:"req_id"`
	ConnID int64  `json:"conn_id"`
	Role   string `json:"role"`
	Dep    string `json:"dep"`
	Effect
}

// decideFault implements draft Table III for one request.
func (r *Run) decideFault(p portInfo, key string, target bool, attempt int, tDone int64) string {
	if p.Role != "dep" || p.Dep != r.Cfg.FaultDep {
		return ""
	}
	switch r.Cfg.Scenario {
	case "S3":
		if target {
			return "stall"
		}
	case "S4":
		if target {
			return "trickle"
		}
	case "S5a", "S5b":
		if target && attempt <= 2 {
			return "503_transient"
		}
	case "S6a", "S6b":
		if target && attempt == 1 {
			return "429"
		}
	case "S7":
		start := r.firstFaultAccept.Load()
		if start != 0 && float64(tDone-start) < r.Cfg.OutageS*1e9 {
			return "503_outage"
		}
	case "S8":
		if target && attempt == 1 {
			return "commit_reset"
		}
	}
	return ""
}

// handle serves one request; returns whether the connection stays open and,
// if not, why it is closed.
func (s *Server) handle(r *Run, p portInfo, cid int64, seq int, tc *tls.Conn, raw *net.TCPConn, br *bufio.Reader, req *Request) (bool, string) {
	keep, reason := s.handle1(r, p, cid, seq, tc, raw, br, req)
	if !keep && reason == "" {
		reason = "server_closed"
	}
	return keep, reason
}

func (s *Server) handle1(r *Run, p portInfo, cid int64, seq int, tc *tls.Conn, raw *net.TCPConn, br *bufio.Reader, req *Request) (bool, string) {
	rid := r.reqSeq.Add(1)
	if !r.deps[p.Dep] {
		// Port of a dependency this task does not have.
		r.lReqs.Write(reqRecord{RunID: r.Cfg.RunID, ReqID: rid, ConnID: cid, Seq: seq, Port: p.Port, Role: p.Role, Dep: p.Dep,
			TFirst: req.TFirstByte, THeaders: req.THeadersDone, TDone: req.TDone, Method: req.Method, Target: req.Target,
			Path: req.Path, Query: req.RawQuery, Proto: req.Proto, Headers: req.Headers, Body: logBody(req.Body), Fault: "no_such_dependency"})
		return s.writeResponse(r, rid, cid, tc, req, errResp(404, "not_found", "no such service on this port"), "", time.Now()), ""
	}
	st := r.state[p.Role]
	key, target := st.Classify(p.Dep, req)
	attempt, tAttempt := r.bumpAttempt(p.Role, p.Dep, key, target)
	fault := r.decideFault(p, key, target, tAttempt, req.TDone)
	rec := reqRecord{RunID: r.Cfg.RunID, ReqID: rid, ConnID: cid, Seq: seq, Port: p.Port, Role: p.Role, Dep: p.Dep,
		TFirst: req.TFirstByte, THeaders: req.THeadersDone, TDone: req.TDone, Method: req.Method, Target: req.Target,
		Path: req.Path, Query: req.RawQuery, Proto: req.Proto, Headers: req.Headers, Body: logBody(req.Body), Chunked: req.Chunked,
		Key: key, Target4: target, Attempt: attempt, TargetAttempt: tAttempt, Fault: fault}
	if r.Cfg.Scenario == "S7" && p.Role == "dep" && p.Dep == r.Cfg.FaultDep {
		rec.OutageRel = float64(req.TDone-r.firstFaultAccept.Load()) / 1e9
	}
	r.lReqs.Write(rec)

	latency := time.Duration(r.Cfg.LatencyMS) * time.Millisecond
	commit := func() *Response {
		resp, effs := st.Handle(p.Dep, req)
		for _, e := range effs {
			r.lEffects.Write(effectRecord{RunID: r.Cfg.RunID, T: monoNS(), ReqID: rid, ConnID: cid, Role: p.Role, Dep: p.Dep, Effect: e})
		}
		return resp
	}

	switch fault {
	case "stall":
		// Request read; nothing is ever sent. Keep reading so that the time
		// the client gives up (closes) is recorded.
		r.lResps.Write(respRecord{RunID: r.Cfg.RunID, ReqID: rid, ConnID: cid, Fault: fault, TEnd: monoNS(), Outcome: "stalled"})
		_, err := io.Copy(io.Discard, br)
		if err == nil {
			return false, "peer_closed"
		}
		return false, classifyReadErr(err, r)
	case "commit_reset":
		commit()
		if !r.sleep(latency) {
			r.lResps.Write(respRecord{RunID: r.Cfg.RunID, ReqID: rid, ConnID: cid, Fault: fault, TEnd: monoNS(), Outcome: "run_finished"})
			return false, ""
		}
		raw.SetLinger(0) // close() now sends RST; no TLS close_notify
		raw.Close()
		r.lResps.Write(respRecord{RunID: r.Cfg.RunID, ReqID: rid, ConnID: cid, Fault: fault, TEnd: monoNS(), Outcome: "reset"})
		return false, "server_reset"
	case "503_transient", "503_outage":
		if !r.sleep(latency) {
			return false, ""
		}
		var extra []Header
		if fault == "503_transient" && r.Cfg.Scenario == "S5b" {
			extra = append(extra, Header{"Retry-After", "1"})
		}
		return s.writeResponse(r, rid, cid, tc, req, errResp(503, "unavailable", "service temporarily unavailable", extra...), fault, time.Now()), ""
	case "429":
		if !r.sleep(latency) {
			return false, ""
		}
		now := time.Now()
		ra := strconv.Itoa(r.Cfg.RetryAfterS)
		if r.Cfg.Scenario == "S6b" {
			// HTTP-date has 1 s resolution: send the 429 exactly on a whole
			// second so that Date + N s is exactly N s after the response,
			// whichever reference (Date or receipt time) the client uses.
			next := now.Truncate(time.Second).Add(time.Second)
			if !r.sleep(time.Until(next)) {
				return false, ""
			}
			now = next
			ra = httpDate(next.Add(time.Duration(r.Cfg.RetryAfterS) * time.Second))
		}
		return s.writeResponse(r, rid, cid, tc, req, errResp(429, "rate_limited", "too many requests", Header{"Retry-After", ra}), fault, now), ""
	case "trickle":
		resp := commit()
		if !r.sleep(latency) {
			return false, ""
		}
		return s.trickle(r, rid, cid, tc, req, resp), ""
	}
	resp := commit()
	if !r.sleep(latency) {
		r.lResps.Write(respRecord{RunID: r.Cfg.RunID, ReqID: rid, ConnID: cid, TEnd: monoNS(), Outcome: "run_finished"})
		return false, ""
	}
	return s.writeResponse(r, rid, cid, tc, req, resp, "", time.Now()), ""
}

func (s *Server) writeResponse(r *Run, rid, cid int64, tc *tls.Conn, req *Request, resp *Response, fault string, date time.Time) bool {
	closeAfter := req.WantsClose()
	body := resp.Body
	if req.Method == "HEAD" {
		body = nil
	}
	rec := respRecord{RunID: r.Cfg.RunID, ReqID: rid, ConnID: cid, Fault: fault, Status: resp.Status, Headers: resp.Headers}
	lb := logBody(resp.Body)
	rec.Body = &lb
	rec.THeadStart = monoNS()
	buf := append(headBytes(resp.Status, resp.Headers, len(resp.Body), closeAfter, date), body...)
	_, err := tc.Write(buf)
	rec.THeadSent = monoNS()
	rec.TBodyDone, rec.TEnd = rec.THeadSent, rec.THeadSent
	if err != nil {
		rec.Outcome, rec.Error = "write_error", err.Error()
		r.lResps.Write(rec)
		return false
	}
	rec.Outcome, rec.BytesWritten = "complete", len(body)
	r.lResps.Write(rec)
	return !closeAfter
}

// trickleBody pads the JSON body to n bytes with LEADING whitespace (allowed
// before a JSON value), so no parser - streaming or not - can obtain the value
// before the last byte arrives (D19). A body longer than n is truncated.
func trickleBody(b []byte, n int) []byte {
	body := make([]byte, n)
	if len(b) >= n {
		copy(body, b)
		return body
	}
	pad := n - len(b)
	for i := 0; i < pad; i++ {
		body[i] = ' '
	}
	copy(body[pad:], b)
	return body
}

// trickle: status and headers at once with Content-Length = TrickleLen, then
// one body byte every TrickleInterval (first byte one interval after headers).
func (s *Server) trickle(r *Run, rid, cid int64, tc *tls.Conn, req *Request, resp *Response) bool {
	body := trickleBody(resp.Body, r.Cfg.TrickleLen)
	rec := respRecord{RunID: r.Cfg.RunID, ReqID: rid, ConnID: cid, Fault: "trickle", Status: resp.Status, Headers: resp.Headers}
	rec.THeadStart = monoNS()
	if _, err := tc.Write(headBytes(resp.Status, resp.Headers, len(body), req.WantsClose(), time.Now())); err != nil {
		rec.Outcome, rec.Error, rec.TEnd = "write_error", err.Error(), monoNS()
		r.lResps.Write(rec)
		return false
	}
	rec.THeadSent = monoNS()
	// Log a record now (long-running), and the final one when it ends.
	r.lResps.Write(respRecord{RunID: r.Cfg.RunID, ReqID: rid, ConnID: cid, Fault: "trickle", Status: resp.Status,
		THeadStart: rec.THeadStart, THeadSent: rec.THeadSent, TEnd: rec.THeadSent, Outcome: "trickle_headers_sent"})
	interval := time.Duration(r.Cfg.TrickleIntervalMS) * time.Millisecond
	next := time.Now().Add(interval)
	for i := 0; i < len(body); i++ {
		if !r.sleep(time.Until(next)) {
			rec.Outcome = "run_finished"
			break
		}
		next = next.Add(interval)
		if _, err := tc.Write(body[i : i+1]); err != nil {
			rec.Outcome, rec.Error = "trickle_aborted", err.Error()
			break
		}
		rec.BytesWritten++
		rec.TrickleTimes = append(rec.TrickleTimes, monoNS())
	}
	rec.TEnd = monoNS()
	if rec.BytesWritten == len(body) {
		rec.Outcome, rec.TBodyDone = "complete", rec.TEnd
		r.lResps.Write(rec)
		return !req.WantsClose()
	}
	r.lResps.Write(rec)
	return false
}
