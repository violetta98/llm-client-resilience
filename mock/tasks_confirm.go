package main

// Normal behavior of the four CONFIRMATORY tasks R6, W5, B5, H4
// (tasks/<ID>/spec.md, generated from tasks/confirm_catalog.py;
// tasks/CONFIRM_TASKS.md). Added after the protocol-v1 freeze; the existing
// task files are unchanged. The data rules are mirrored in
// analysis/checkers_confirm.py.

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

// ---------------------------------------------------------------- R6 stock levels (read)
type r6State struct{}

var reR6 = regexp.MustCompile(`^/v1/products/([^/]+)/stock$`)
var rePrd = reNNN3("prd")

func r6Stock(id string) map[string]any {
	n, _ := strconv.Atoi(strings.TrimPrefix(id, "prd-"))
	whs := make([]map[string]any, 0, 24)
	for k := 1; k <= 24; k++ {
		whs = append(whs, map[string]any{"warehouse_id": fmt.Sprintf("wh-%02d", k),
			"available": (n*37 + k*101) % 1000, "reserved": (n + k*7) % 50})
	}
	return map[string]any{"product_id": id, "warehouses": whs, "updated_at": "2026-03-01T06:00:00Z"}
}

func (r6State) Classify(dep string, r *Request) (string, bool) {
	if m := reR6.FindStringSubmatch(r.Path); m != nil && r.Method == "GET" {
		return "stock:" + m[1], true
	}
	return "", false
}

func (r6State) Handle(dep string, r *Request) (*Response, []Effect) {
	m := reR6.FindStringSubmatch(r.Path)
	if m == nil {
		return notFound(), nil
	}
	if r.Method != "GET" {
		return methodNA("GET"), nil
	}
	if !rePrd.MatchString(m[1]) {
		return errResp(404, "not_found", "product not found"), nil
	}
	return jsonResp(200, r6Stock(m[1])), nil
}

// ---------------------------------------------------------------- W5 support ticket (Idempotency-Key)
type w5State struct {
	mu     sync.Mutex
	n      int
	prefix string
	idem   map[string]w1Stored
}

var reCus = reNNN3("cus")

func (s *w5State) Classify(dep string, r *Request) (string, bool) {
	if r.Path != "/v1/tickets" || r.Method != "POST" {
		return "", false
	}
	m, _ := jsonBody(r)
	return "ticket:" + strField(m, "customer_id"), true
}

func (s *w5State) Handle(dep string, r *Request) (*Response, []Effect) {
	if r.Path != "/v1/tickets" {
		return notFound(), nil
	}
	if r.Method != "POST" {
		return methodNA("POST"), nil
	}
	m, ok := jsonBody(r)
	cid, subj, msg := strField(m, "customer_id"), strField(m, "subject"), strField(m, "message")
	if !ok || !reCus.MatchString(cid) || strings.TrimSpace(subj) == "" || strings.TrimSpace(msg) == "" {
		return badReq("customer_id (cus-NNN), subject and message are required"), nil
	}
	bh := sha1hex(cid + "\x00" + subj + "\x00" + msg)
	key := r.Get("Idempotency-Key")
	s.mu.Lock()
	defer s.mu.Unlock()
	if key != "" {
		if st, seen := s.idem[key]; seen {
			if st.bodyHash != bh {
				return errResp(422, "idempotency_key_reused", "Idempotency-Key was used with a different body"), nil
			}
			return st.resp, []Effect{{Kind: "ticket_replayed", Key: key}}
		}
	}
	s.n++
	id := fmt.Sprintf("tkt_%s%06d", s.prefix, s.n)
	resp := jsonResp(201, map[string]any{"id": id, "customer_id": cid, "subject": subj, "status": "open", "created_at": "2026-03-01T12:00:00Z"})
	if key != "" {
		s.idem[key] = w1Stored{bh, resp}
	}
	return resp, []Effect{{Kind: "ticket_created", Key: id, Detail: map[string]any{"customer_id": cid, "idempotency_key": key}}}
}

// ---------------------------------------------------------------- B5 shipment updates (background)
type b5State struct{}

var reB5 = regexp.MustCompile(`^/v1/carriers/([^/]+)/shipment-updates$`)
var reCar = reNNN3("car")
var b5Status = []string{"picked_up", "in_transit", "out_for_delivery", "delivered", "exception"}
var b5Day = time.Date(2026, 3, 1, 0, 0, 0, 0, time.UTC)

// b5Updates: the carrier's 25 updates (k * 17 minutes after midnight) with updated_at > since.
func b5Updates(carrier string, since time.Time) []map[string]any {
	n, _ := strconv.Atoi(strings.TrimPrefix(carrier, "car-"))
	out := []map[string]any{}
	for k := 1; k <= 25; k++ {
		t := b5Day.Add(time.Duration(k*17) * time.Minute)
		if !t.After(since) {
			continue
		}
		out = append(out, map[string]any{"shipment_id": fmt.Sprintf("shp-%03d-%03d", n, k), "status": b5Status[(n+k)%5],
			"updated_at": t.Format("2006-01-02T15:04:05Z")})
	}
	return out
}

func (b5State) Classify(dep string, r *Request) (string, bool) {
	if m := reB5.FindStringSubmatch(r.Path); m != nil && r.Method == "GET" {
		return "updates:" + m[1] + "|" + r.Query.Get("since"), true
	}
	return "", false
}

func (b5State) Handle(dep string, r *Request) (*Response, []Effect) {
	m := reB5.FindStringSubmatch(r.Path)
	if m == nil {
		return notFound(), nil
	}
	if r.Method != "GET" {
		return methodNA("GET"), nil
	}
	if !reCar.MatchString(m[1]) {
		return errResp(404, "not_found", "carrier not found"), nil
	}
	since, err := time.Parse(time.RFC3339, r.Query.Get("since"))
	if err != nil {
		return badReq("since must be an RFC 3339 time"), nil
	}
	ups := b5Updates(m[1], since)
	var next any
	if len(ups) > 0 {
		next = ups[len(ups)-1]["updated_at"]
	}
	return jsonResp(200, map[string]any{"updates": ups, "next_since": next}), nil
}

// ---------------------------------------------------------------- H4 notification preferences (handler)
type h4State struct{}

var reH4 = regexp.MustCompile(`^/v1/users/([^/]+)/notification-preferences$`)

func (h4State) Classify(dep string, r *Request) (string, bool) {
	if m := reH4.FindStringSubmatch(r.Path); m != nil && r.Method == "GET" {
		return "prefs:" + m[1], true
	}
	return "", false
}

func (h4State) Handle(dep string, r *Request) (*Response, []Effect) {
	m := reH4.FindStringSubmatch(r.Path)
	if m == nil {
		return notFound(), nil
	}
	if r.Method != "GET" {
		return methodNA("GET"), nil
	}
	if !reUser.MatchString(m[1]) {
		return errResp(404, "not_found", "user not found"), nil
	}
	// The opposite of the documented default {email: true, sms: false, push: false} in every field.
	return jsonResp(200, map[string]any{"user_id": m[1], "email": false, "sms": true, "push": true, "updated_at": "2026-02-20T08:00:00Z"}), nil
}

func init() {
	one := []string{"A"}
	register(simpleTask{"R6", one, "A", func(*RunCtx, string) TaskState { return r6State{} }})
	register(simpleTask{"W5", one, "A", func(_ *RunCtx, role string) TaskState {
		return &w5State{prefix: rolePrefix(role), idem: map[string]w1Stored{}}
	}})
	register(simpleTask{"B5", one, "A", func(*RunCtx, string) TaskState { return b5State{} }})
	register(simpleTask{"H4", one, "A", func(*RunCtx, string) TaskState { return h4State{} }})
}
