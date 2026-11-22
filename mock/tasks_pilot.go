package main

// Normal behavior of the three PILOT tasks P1-P3 (pilot/tasks/<ID>/spec.md,
// generated from tasks/pilot_catalog.py). They are outside the benchmark.

import (
	"fmt"
	"math"
	"regexp"
	"strconv"
	"sync"
)

// ---------------------------------------------------------------- P1 exchange rate
type p1State struct{}

var reP1 = regexp.MustCompile(`^/v1/rates/([^/]+)/([^/]+)$`)
var reCcy = regexp.MustCompile(`^[A-Z]{3}$`)

func p1Rate(base, quote string) float64 {
	if base == quote {
		return 1.0
	}
	n, _ := strconv.ParseUint(sha1hex(base + "/" + quote)[:4], 16, 32)
	return math.Round((0.5+float64(n)/65536)*10000) / 10000
}

func (p1State) Classify(dep string, r *Request) (string, bool) {
	if m := reP1.FindStringSubmatch(r.Path); m != nil && r.Method == "GET" {
		return "rate:" + m[1] + "/" + m[2], true
	}
	return "", false
}

func (p1State) Handle(dep string, r *Request) (*Response, []Effect) {
	m := reP1.FindStringSubmatch(r.Path)
	if m == nil || !reCcy.MatchString(m[1]) || !reCcy.MatchString(m[2]) {
		return errResp(404, "not_found", "unknown currency pair"), nil
	}
	if r.Method != "GET" {
		return methodNA("GET"), nil
	}
	return jsonResp(200, map[string]any{"base": m[1], "quote": m[2], "rate": p1Rate(m[1], m[2]), "as_of": "2026-03-01T12:00:00Z"}), nil
}

// ---------------------------------------------------------------- P2 ticket comment (no idempotency)
type p2State struct {
	mu     sync.Mutex
	n      int
	prefix string
}

var reP2 = regexp.MustCompile(`^/v1/tickets/([^/]+)/comments$`)
var reTicket = reNNN3("t")

func (s *p2State) Classify(dep string, r *Request) (string, bool) {
	if m := reP2.FindStringSubmatch(r.Path); m != nil && r.Method == "POST" {
		return "comment:" + m[1], true
	}
	return "", false
}

func (s *p2State) Handle(dep string, r *Request) (*Response, []Effect) {
	m := reP2.FindStringSubmatch(r.Path)
	if m == nil || !reTicket.MatchString(m[1]) {
		return errResp(404, "not_found", "ticket not found"), nil
	}
	if r.Method != "POST" {
		return methodNA("POST"), nil
	}
	b, ok := jsonBody(r)
	text := strField(b, "text")
	if !ok || text == "" {
		return badReq("empty text"), nil
	}
	s.mu.Lock()
	s.n++
	id := fmt.Sprintf("cmt_%s%06d", s.prefix, s.n)
	s.mu.Unlock()
	return jsonResp(201, map[string]any{"id": id, "ticket_id": m[1], "created_at": "2026-03-01T12:00:00Z"}),
		[]Effect{{Kind: "comment_created", Key: id, Detail: map[string]any{"ticket_id": m[1], "text_sha1": sha1hex(text)}}}
}

// ---------------------------------------------------------------- P3 delivery estimate
type p3State struct{}

var rePostal = regexp.MustCompile(`^[0-9]{2}-[0-9]{3}$`)

func (p3State) Classify(dep string, r *Request) (string, bool) {
	if r.Path == "/v1/estimates" {
		return "estimate:" + r.Query.Get("postal_code"), true
	}
	return "", false
}

func (p3State) Handle(dep string, r *Request) (*Response, []Effect) {
	if r.Path != "/v1/estimates" {
		return notFound(), nil
	}
	if r.Method != "GET" {
		return methodNA("GET"), nil
	}
	pc := r.Query.Get("postal_code")
	if !rePostal.MatchString(pc) {
		return errResp(404, "not_found", "unknown postal code"), nil
	}
	return jsonResp(200, map[string]any{"postal_code": pc, "days": 2}), nil
}

func init() {
	one := []string{"A"}
	register(simpleTask{"P1", one, "A", func(*RunCtx, string) TaskState { return p1State{} }})
	register(simpleTask{"P2", one, "A", func(_ *RunCtx, role string) TaskState { return &p2State{prefix: rolePrefix(role)} }})
	register(simpleTask{"P3", one, "A", func(*RunCtx, string) TaskState { return p3State{} }})
}
