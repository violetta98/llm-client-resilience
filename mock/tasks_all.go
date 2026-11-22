package main

// Normal behavior of the dependencies of tasks R2-H3 (tasks/<ID>/spec.md,
// generated from tasks/catalog.py; approved 2026-11-05). R1 is in task_r1.go.

import (
	"crypto/rand"
	"crypto/sha1"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

// simpleTask wires a task ID to a state constructor.
type simpleTask struct {
	id    string
	deps  []string
	fault string
	mk    func(rc *RunCtx, role string) TaskState
}

func (t simpleTask) ID() string                                 { return t.id }
func (t simpleTask) Deps() []string                             { return t.deps }
func (t simpleTask) DefaultFaultDep() string                    { return t.fault }
func (t simpleTask) NewState(rc *RunCtx, role string) TaskState { return t.mk(rc, role) }

func notFound() *Response       { return errResp(404, "not_found", "not found") }
func badReq(m string) *Response { return errResp(400, "invalid_request", m) }
func methodNA(allow string) *Response {
	return errResp(405, "method_not_allowed", "use "+allow, Header{"Allow", allow})
}

func sha1hex(s string) string  { h := sha1.Sum([]byte(s)); return hex.EncodeToString(h[:]) }
func round2(f float64) float64 { return math.Round(f*100) / 100 }

func titleCase(s string) string {
	ws := strings.Fields(s)
	for i, w := range ws {
		ws[i] = strings.ToUpper(w[:1]) + w[1:]
	}
	return strings.Join(ws, " ")
}

var (
	reNNN3 = func(prefix string) *regexp.Regexp { return regexp.MustCompile(`^` + prefix + `-[0-9]{3}$`) }
	reUser = reNNN3("u")
)

func profileOf(id string) map[string]any {
	n := strings.TrimPrefix(id, "u-")
	return map[string]any{"id": id, "name": "User " + n, "email": fmt.Sprintf("user%s@example.com", n), "created_at": "2024-01-15T09:30:00Z"}
}

// ---------------------------------------------------------------- R2 search
type r2State struct{}

func (r2State) Classify(dep string, r *Request) (string, bool) {
	if r.Path == "/v1/products" {
		return "search:" + r.Query.Get("q") + "|" + r.Query.Get("category") + "|" + r.Query.Get("max_price"), true
	}
	return "", false
}

func (r2State) Handle(dep string, r *Request) (*Response, []Effect) {
	if r.Path != "/v1/products" {
		return notFound(), nil
	}
	if r.Method != "GET" {
		return methodNA("GET"), nil
	}
	q, cat := r.Query.Get("q"), r.Query.Get("category")
	mp, err := strconv.ParseFloat(r.Query.Get("max_price"), 64)
	if strings.TrimSpace(q) == "" || cat == "" || err != nil || mp <= 0 {
		return badReq("q, category and max_price are required"), nil
	}
	h := sha1hex(q + "|" + cat)[:6]
	items := []map[string]any{}
	for k, f := range []float64{0.5, 0.7, 0.9} {
		items = append(items, map[string]any{"id": fmt.Sprintf("p-%s-%d", h, k+1), "name": fmt.Sprintf("%s %d", titleCase(q), k+1),
			"category": cat, "price": round2(mp * f)})
	}
	return jsonResp(200, map[string]any{"items": items, "total": len(items)}), nil
}

// ---------------------------------------------------------------- R3 report download
type r3State struct{}

var reR3 = regexp.MustCompile(`^/v1/reports/([^/]+)/download$`)
var reRep = reNNN3("rep")

// reportContent: 65,536 deterministic bytes (SHA-256 counter stream).
func reportContent(id string) []byte {
	out := make([]byte, 0, 65536)
	for i := 0; len(out) < 65536; i++ {
		h := sha256.Sum256([]byte(fmt.Sprintf("%s:%d", id, i)))
		out = append(out, h[:]...)
	}
	return out[:65536]
}

func (r3State) Classify(dep string, r *Request) (string, bool) {
	if m := reR3.FindStringSubmatch(r.Path); m != nil {
		return "report:" + m[1], true
	}
	return "", false
}

func (r3State) Handle(dep string, r *Request) (*Response, []Effect) {
	m := reR3.FindStringSubmatch(r.Path)
	if m == nil || !reRep.MatchString(m[1]) {
		return notFound(), nil
	}
	if r.Method != "GET" {
		return methodNA("GET"), nil
	}
	return &Response{Status: 200, Headers: []Header{{"Content-Type", "application/octet-stream"},
		{"Content-Disposition", fmt.Sprintf(`attachment; filename="%s.bin"`, m[1])}}, Body: reportContent(m[1])}, nil
}

// ---------------------------------------------------------------- R4 paginated orders
type r4State struct{}

var reR4 = regexp.MustCompile(`^/v1/customers/([^/]+)/orders$`)
var reCust = reNNN3("c")

func r4Cursor(cust string, page int) string {
	return fmt.Sprintf("pg%d.%s", page, sha1hex(fmt.Sprintf("%s|%d", cust, page))[:8])
}

func r4Order(cust string, i int) map[string]any {
	n := strings.TrimPrefix(cust, "c-")
	return map[string]any{"id": fmt.Sprintf("o-%s-%03d", n, i), "created_at": fmt.Sprintf("2025-%02d-%02dT10:00:00Z", 1+(i-1)/28%12, 1+(i-1)%28),
		"total": fmt.Sprintf("%d.%02d", 10+i, (i*37)%100)}
}

func (r4State) Classify(dep string, r *Request) (string, bool) {
	m := reR4.FindStringSubmatch(r.Path)
	if m == nil {
		return "", false
	}
	c := r.Query.Get("cursor")
	page := "1"
	if c != "" {
		page = c
	}
	return "orders:" + m[1] + "|" + page, c != "" && c == r4Cursor(m[1], 2)
}

func (r4State) Handle(dep string, r *Request) (*Response, []Effect) {
	m := reR4.FindStringSubmatch(r.Path)
	if m == nil || !reCust.MatchString(m[1]) {
		return notFound(), nil
	}
	if r.Method != "GET" {
		return methodNA("GET"), nil
	}
	cust := m[1]
	page := 1
	if c := r.Query.Get("cursor"); c != "" {
		switch c {
		case r4Cursor(cust, 2):
			page = 2
		case r4Cursor(cust, 3):
			page = 3
		default:
			return badReq("unknown cursor"), nil
		}
	}
	from, to := (page-1)*50+1, page*50
	if to > 120 {
		to = 120
	}
	orders := []map[string]any{}
	for i := from; i <= to; i++ {
		orders = append(orders, r4Order(cust, i))
	}
	var next any
	if page < 3 {
		next = r4Cursor(cust, page+1)
	}
	return jsonResp(200, map[string]any{"orders": orders, "next_cursor": next}), nil
}

// ---------------------------------------------------------------- R5 feature flag
type r5State struct{}

var reR5 = regexp.MustCompile(`^/v1/flags/([^/]+)$`)
var reFlag = regexp.MustCompile(`^[a-z0-9-]+$`)

func (r5State) Classify(dep string, r *Request) (string, bool) {
	if m := reR5.FindStringSubmatch(r.Path); m != nil {
		return "flag:" + m[1], true
	}
	return "", false
}

func (r5State) Handle(dep string, r *Request) (*Response, []Effect) {
	m := reR5.FindStringSubmatch(r.Path)
	if m == nil || !reFlag.MatchString(m[1]) {
		return notFound(), nil
	}
	if r.Method != "GET" {
		return methodNA("GET"), nil
	}
	return jsonResp(200, map[string]any{"key": m[1], "enabled": true}), nil
}

// ---------------------------------------------------------------- W1 payments (Idempotency-Key)
type w1State struct {
	mu     sync.Mutex
	n      int
	prefix string
	idem   map[string]w1Stored
}

type w1Stored struct {
	bodyHash string
	resp     *Response
}

var reAmount = regexp.MustCompile(`^[0-9]+\.[0-9]{2}$`)
var reCurrency = regexp.MustCompile(`^[A-Z]{3}$`)

func jsonBody(r *Request) (map[string]any, bool) {
	var m map[string]any
	if err := json.Unmarshal(r.Body, &m); err != nil {
		return nil, false
	}
	return m, true
}

func strField(m map[string]any, k string) string {
	s, _ := m[k].(string)
	return s
}

func (s *w1State) Classify(dep string, r *Request) (string, bool) {
	if r.Path != "/v1/payments" || r.Method != "POST" {
		return "", false
	}
	m, _ := jsonBody(r)
	return "payment:" + strField(m, "order_id"), true
}

func (s *w1State) Handle(dep string, r *Request) (*Response, []Effect) {
	if r.Path != "/v1/payments" {
		return notFound(), nil
	}
	if r.Method != "POST" {
		return methodNA("POST"), nil
	}
	m, ok := jsonBody(r)
	oid, amt, cur := strField(m, "order_id"), strField(m, "amount"), strField(m, "currency")
	if !ok || oid == "" || !reAmount.MatchString(amt) || !reCurrency.MatchString(cur) {
		return badReq("order_id, amount (e.g. \"49.90\") and currency (ISO 4217) are required"), nil
	}
	canon, _ := json.Marshal(map[string]string{"order_id": oid, "amount": amt, "currency": cur})
	bh := sha1hex(string(canon))
	key := r.Get("Idempotency-Key")
	s.mu.Lock()
	defer s.mu.Unlock()
	if key != "" {
		if st, seen := s.idem[key]; seen {
			if st.bodyHash != bh {
				return errResp(422, "idempotency_key_reused", "Idempotency-Key was used with a different body"), nil
			}
			return st.resp, []Effect{{Kind: "payment_replayed", Key: key}}
		}
	}
	s.n++
	id := fmt.Sprintf("pay_%s%06d", s.prefix, s.n)
	resp := jsonResp(201, map[string]any{"id": id, "order_id": oid, "amount": amt, "currency": cur, "status": "succeeded"})
	if key != "" {
		s.idem[key] = w1Stored{bh, resp}
	}
	return resp, []Effect{{Kind: "payment_created", Key: id, Detail: map[string]any{"order_id": oid, "idempotency_key": key}}}
}

// ---------------------------------------------------------------- W2 SMS (no idempotency)
type w2State struct {
	mu     sync.Mutex
	n      int
	prefix string
}

var rePhone = regexp.MustCompile(`^\+[0-9]{8,15}$`)

func (s *w2State) Classify(dep string, r *Request) (string, bool) {
	if r.Path != "/v1/messages" || r.Method != "POST" {
		return "", false
	}
	m, _ := jsonBody(r)
	return "sms:" + strField(m, "to") + "|" + sha1hex(strField(m, "body"))[:8], true
}

func (s *w2State) Handle(dep string, r *Request) (*Response, []Effect) {
	if r.Path != "/v1/messages" {
		return notFound(), nil
	}
	if r.Method != "POST" {
		return methodNA("POST"), nil
	}
	m, ok := jsonBody(r)
	to, body := strField(m, "to"), strField(m, "body")
	if !ok || !rePhone.MatchString(to) || body == "" {
		return badReq("invalid phone number or body"), nil
	}
	s.mu.Lock()
	s.n++
	id := fmt.Sprintf("msg_%s%06d", s.prefix, s.n)
	s.mu.Unlock()
	return jsonResp(202, map[string]any{"id": id, "status": "queued"}),
		[]Effect{{Kind: "sms_sent", Key: id, Detail: map[string]any{"to": to, "body_sha1": sha1hex(body)}}}
}

// ---------------------------------------------------------------- W3 document PUT
type w3State struct {
	mu   sync.Mutex
	docs map[string]int
}

var reW3 = regexp.MustCompile(`^/v1/documents/([^/]+)$`)
var reDoc = reNNN3("doc")

func (s *w3State) Classify(dep string, r *Request) (string, bool) {
	if m := reW3.FindStringSubmatch(r.Path); m != nil && r.Method == "PUT" {
		return "doc:" + m[1], true
	}
	return "", false
}

func (s *w3State) Handle(dep string, r *Request) (*Response, []Effect) {
	m := reW3.FindStringSubmatch(r.Path)
	if m == nil || !reDoc.MatchString(m[1]) {
		return notFound(), nil
	}
	if r.Method != "PUT" {
		return methodNA("PUT"), nil
	}
	if len(r.Body) == 0 {
		return badReq("empty body"), nil
	}
	sum := sha256.Sum256(r.Body)
	s.mu.Lock()
	s.docs[m[1]]++
	v := s.docs[m[1]]
	s.mu.Unlock()
	h := hex.EncodeToString(sum[:])
	return jsonResp(200, map[string]any{"id": m[1], "size": len(r.Body), "sha256": h, "version": v}),
		[]Effect{{Kind: "document_written", Key: m[1], Detail: map[string]any{"size": len(r.Body), "sha256": h, "version": v}}}
}

// ---------------------------------------------------------------- W4 subscription DELETE
type w4State struct {
	mu       sync.Mutex
	canceled map[string]bool
}

var reW4 = regexp.MustCompile(`^/v1/subscriptions/([^/]+)$`)
var reSub = reNNN3("sub")

func (s *w4State) Classify(dep string, r *Request) (string, bool) {
	if m := reW4.FindStringSubmatch(r.Path); m != nil && r.Method == "DELETE" {
		return "sub:" + m[1], true
	}
	return "", false
}

func (s *w4State) Handle(dep string, r *Request) (*Response, []Effect) {
	m := reW4.FindStringSubmatch(r.Path)
	if m == nil || !reSub.MatchString(m[1]) {
		return notFound(), nil
	}
	if r.Method != "DELETE" {
		return methodNA("DELETE"), nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.canceled[m[1]] {
		return errResp(404, "not_found", "subscription not found or already canceled"), nil
	}
	s.canceled[m[1]] = true
	return jsonResp(200, map[string]any{"id": m[1], "status": "canceled"}), []Effect{{Kind: "subscription_canceled", Key: m[1]}}
}

// ---------------------------------------------------------------- B1 records PUT, rate-limited
type bucket struct {
	tokens float64
	last   time.Time
}

type b1State struct {
	mu      sync.Mutex
	buckets map[string]*bucket
	ver     map[string]int
}

var reB1 = regexp.MustCompile(`^/v1/records/([^/]+)$`)
var reRec = regexp.MustCompile(`^rec-([a-z0-9]+)-[0-9]{2}$`)

const b1Rate, b1Burst = 10.0, 10.0

func (s *b1State) Classify(dep string, r *Request) (string, bool) {
	if m := reB1.FindStringSubmatch(r.Path); m != nil && r.Method == "PUT" {
		return "record:" + m[1], strings.HasSuffix(m[1], "-05")
	}
	return "", false
}

func (s *b1State) Handle(dep string, r *Request) (*Response, []Effect) {
	m := reB1.FindStringSubmatch(r.Path)
	if m == nil {
		return notFound(), nil
	}
	if r.Method != "PUT" {
		return methodNA("PUT"), nil
	}
	pm := reRec.FindStringSubmatch(m[1])
	if pm == nil {
		return notFound(), nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	// Rate limit per invocation (record-id prefix): token bucket 10/s, burst 10.
	b := s.buckets[pm[1]]
	now := time.Now()
	if b == nil {
		b = &bucket{tokens: b1Burst, last: now}
		s.buckets[pm[1]] = b
	}
	b.tokens = math.Min(b1Burst, b.tokens+now.Sub(b.last).Seconds()*b1Rate)
	b.last = now
	if b.tokens < 1 {
		return errResp(429, "rate_limited", "rate limit of 10 requests per second exceeded", Header{"Retry-After", "1"}),
			[]Effect{{Kind: "rate_limited", Key: m[1]}}
	}
	b.tokens--
	body, ok := jsonBody(r)
	if !ok || strField(body, "id") != m[1] {
		return badReq("the body must be the record, with the same id as the path"), nil
	}
	s.ver[m[1]]++
	v := s.ver[m[1]]
	return jsonResp(200, map[string]any{"id": m[1], "version": v}),
		[]Effect{{Kind: "record_written", Key: m[1], Detail: map[string]any{"version": v, "body_sha1": sha1hex(string(r.Body))}}}
}

// ---------------------------------------------------------------- B2 export polling
type b2State struct {
	mu    sync.Mutex
	first map[string]time.Time
	seen  map[string]int
}

var reB2 = regexp.MustCompile(`^/v1/exports/([^/]+)$`)
var reExp = reNNN3("exp")

const b2CompleteAfter = 3 * time.Second

func (s *b2State) Classify(dep string, r *Request) (string, bool) {
	m := reB2.FindStringSubmatch(r.Path)
	if m == nil || r.Method != "GET" {
		return "", false
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.first[m[1]]; !ok {
		s.first[m[1]] = time.Now()
	}
	s.seen[m[1]]++
	// Faulted requests: status requests after the first one.
	return "export:" + m[1], s.seen[m[1]] > 1
}

func (s *b2State) Handle(dep string, r *Request) (*Response, []Effect) {
	m := reB2.FindStringSubmatch(r.Path)
	if m == nil || !reExp.MatchString(m[1]) {
		return notFound(), nil
	}
	if r.Method != "GET" {
		return methodNA("GET"), nil
	}
	s.mu.Lock()
	first := s.first[m[1]]
	s.mu.Unlock()
	if time.Since(first) < b2CompleteAfter {
		return jsonResp(200, map[string]any{"id": m[1], "status": "running", "result_url": nil}), nil
	}
	return jsonResp(200, map[string]any{"id": m[1], "status": "completed",
		"result_url": "https://files.example.com/exports/" + m[1] + ".csv"}), nil
}

// ---------------------------------------------------------------- B3 token + API
type b3State struct{ rc *RunCtx }

var reB3 = regexp.MustCompile(`^/v1/accounts/([^/]+)/balance$`)
var reAcc = reNNN3("acc")

func (s *b3State) Classify(dep string, r *Request) (string, bool) {
	if dep == "A" && r.Path == "/oauth/token" {
		return "token", false
	}
	if m := reB3.FindStringSubmatch(r.Path); dep == "B" && m != nil {
		return "balance:" + m[1], true
	}
	return "", false
}

func (s *b3State) Handle(dep string, r *Request) (*Response, []Effect) {
	switch dep {
	case "A":
		if r.Path != "/oauth/token" {
			return notFound(), nil
		}
		if r.Method != "POST" {
			return methodNA("POST"), nil
		}
		form, _ := url.ParseQuery(string(r.Body))
		id, secret := form.Get("client_id"), form.Get("client_secret")
		if id == "" { // client_secret_basic is accepted too
			if u, p, ok := basicAuth(r.Get("Authorization")); ok {
				id, secret = u, p
			}
		}
		if form.Get("grant_type") != "client_credentials" {
			return errResp(400, "unsupported_grant_type", "grant_type must be client_credentials"), nil
		}
		if id != "client-1" || secret != "s3cr3t" {
			return errResp(401, "invalid_client", "invalid client credentials"), nil
		}
		b := make([]byte, 16)
		rand.Read(b)
		tok := "tok_" + hex.EncodeToString(b)
		s.rc.Shared.Store("b3token:"+tok, true)
		return jsonResp(200, map[string]any{"access_token": tok, "token_type": "Bearer", "expires_in": 3600}),
			[]Effect{{Kind: "token_issued", Key: tok[:12]}}
	case "B":
		m := reB3.FindStringSubmatch(r.Path)
		if m == nil {
			return notFound(), nil
		}
		if r.Method != "GET" {
			return methodNA("GET"), nil
		}
		auth := r.Get("Authorization")
		tok := strings.TrimSpace(strings.TrimPrefix(auth, "Bearer"))
		if _, ok := s.rc.Shared.Load("b3token:" + tok); !ok || !strings.HasPrefix(auth, "Bearer ") {
			return errResp(401, "invalid_token", "missing, invalid or expired token", Header{"WWW-Authenticate", `Bearer error="invalid_token"`}), nil
		}
		if !reAcc.MatchString(m[1]) {
			return notFound(), nil
		}
		return jsonResp(200, map[string]any{"account_id": m[1], "balance": "1250.00", "currency": "EUR"}), nil
	}
	return notFound(), nil
}

func basicAuth(h string) (string, string, bool) {
	if !strings.HasPrefix(h, "Basic ") {
		return "", "", false
	}
	b, err := decodeB64(strings.TrimPrefix(h, "Basic "))
	if err != nil {
		return "", "", false
	}
	u, p, ok := strings.Cut(string(b), ":")
	if !ok {
		return "", "", false
	}
	u, _ = url.QueryUnescape(u)
	p, _ = url.QueryUnescape(p)
	return u, p, true
}

// ---------------------------------------------------------------- B4 webhook receiver
type b4State struct {
	mu   sync.Mutex
	seen map[string]bool
}

func (s *b4State) Classify(dep string, r *Request) (string, bool) {
	if r.Path != "/hooks/acme" || r.Method != "POST" {
		return "", false
	}
	m, _ := jsonBody(r)
	return "event:" + strField(m, "id"), true
}

func (s *b4State) Handle(dep string, r *Request) (*Response, []Effect) {
	if r.Path != "/hooks/acme" {
		return notFound(), nil
	}
	if r.Method != "POST" {
		return methodNA("POST"), nil
	}
	m, ok := jsonBody(r)
	id := strField(m, "id")
	if !ok || id == "" {
		return badReq("the body must be a JSON event with an id"), nil
	}
	effs := []Effect{{Kind: "delivery_received", Key: id}}
	s.mu.Lock()
	dup := s.seen[id]
	s.seen[id] = true
	s.mu.Unlock()
	if dup {
		return jsonResp(200, map[string]any{"received": true, "duplicate": true}), effs
	}
	return jsonResp(200, map[string]any{"received": true}), append(effs, Effect{Kind: "delivery_accepted", Key: id})
}

// ---------------------------------------------------------------- H1 profile + recommendations
type h1State struct{}

var reH1Recs = regexp.MustCompile(`^/v1/users/([^/]+)/recommendations$`)

func (h1State) Classify(dep string, r *Request) (string, bool) {
	if m := reH1Recs.FindStringSubmatch(r.Path); dep == "B" && m != nil {
		return "recs:" + m[1], true
	}
	if m := r1Path.FindStringSubmatch(r.Path); dep == "A" && m != nil {
		return "profile:" + m[1], false
	}
	return "", false
}

func (h1State) Handle(dep string, r *Request) (*Response, []Effect) {
	if r.Method != "GET" {
		return methodNA("GET"), nil
	}
	switch dep {
	case "A":
		if m := r1Path.FindStringSubmatch(r.Path); m != nil && reUser.MatchString(m[1]) {
			return jsonResp(200, profileOf(m[1])), nil
		}
	case "B":
		if m := reH1Recs.FindStringSubmatch(r.Path); m != nil && reUser.MatchString(m[1]) {
			n := strings.TrimPrefix(m[1], "u-")
			items := []map[string]any{}
			for k := 1; k <= 3; k++ {
				items = append(items, map[string]any{"product_id": fmt.Sprintf("p-%s-%d", n, k), "title": fmt.Sprintf("Product %d", k)})
			}
			return jsonResp(200, map[string]any{"items": items}), nil
		}
	}
	return notFound(), nil
}

// ---------------------------------------------------------------- H2 readiness
type h2State struct{}

var reH2 = regexp.MustCompile(`^/instances/([a-z0-9-]+)/healthz$`)

func (h2State) Classify(dep string, r *Request) (string, bool) {
	if m := reH2.FindStringSubmatch(r.Path); m != nil {
		return "health:" + m[1], true
	}
	return "", false
}

func (h2State) Handle(dep string, r *Request) (*Response, []Effect) {
	if reH2.MatchString(r.Path) && (r.Method == "GET" || r.Method == "HEAD") {
		return jsonResp(200, map[string]any{"status": "ok"}), nil
	}
	return notFound(), nil
}

// ---------------------------------------------------------------- H3 supplier quotes
type h3State struct{}

var reSku = reNNN3("sku")
var h3Price = map[string]struct {
	name  string
	price float64
}{"A": {"s1", 9.40}, "B": {"s2", 10.10}, "C": {"s3", 11.25}}

func (h3State) Classify(dep string, r *Request) (string, bool) {
	if r.Path == "/v1/quotes" {
		return "quote:" + dep + "|" + r.Query.Get("sku"), true
	}
	return "", false
}

func (h3State) Handle(dep string, r *Request) (*Response, []Effect) {
	if r.Path != "/v1/quotes" {
		return notFound(), nil
	}
	if r.Method != "GET" {
		return methodNA("GET"), nil
	}
	sku := r.Query.Get("sku")
	if !reSku.MatchString(sku) {
		return errResp(404, "unknown_sku", "unknown SKU"), nil
	}
	p := h3Price[dep]
	return jsonResp(200, map[string]any{"supplier": p.name, "sku": sku, "price": p.price, "currency": "EUR"}), nil
}

func rolePrefix(role string) string {
	if role == "warmup" {
		return "w"
	}
	return ""
}

func init() {
	one := []string{"A"}
	register(simpleTask{"R2", one, "A", func(*RunCtx, string) TaskState { return r2State{} }})
	register(simpleTask{"R3", one, "A", func(*RunCtx, string) TaskState { return r3State{} }})
	register(simpleTask{"R4", one, "A", func(*RunCtx, string) TaskState { return r4State{} }})
	register(simpleTask{"R5", one, "A", func(*RunCtx, string) TaskState { return r5State{} }})
	register(simpleTask{"W1", one, "A", func(_ *RunCtx, role string) TaskState {
		return &w1State{prefix: rolePrefix(role), idem: map[string]w1Stored{}}
	}})
	register(simpleTask{"W2", one, "A", func(_ *RunCtx, role string) TaskState { return &w2State{prefix: rolePrefix(role)} }})
	register(simpleTask{"W3", one, "A", func(*RunCtx, string) TaskState { return &w3State{docs: map[string]int{}} }})
	register(simpleTask{"W4", one, "A", func(*RunCtx, string) TaskState { return &w4State{canceled: map[string]bool{}} }})
	register(simpleTask{"B1", one, "A", func(*RunCtx, string) TaskState {
		return &b1State{buckets: map[string]*bucket{}, ver: map[string]int{}}
	}})
	register(simpleTask{"B2", one, "A", func(*RunCtx, string) TaskState {
		return &b2State{first: map[string]time.Time{}, seen: map[string]int{}}
	}})
	register(simpleTask{"B3", []string{"A", "B"}, "B", func(rc *RunCtx, _ string) TaskState { return &b3State{rc: rc} }})
	register(simpleTask{"B4", one, "A", func(*RunCtx, string) TaskState { return &b4State{seen: map[string]bool{}} }})
	register(simpleTask{"H1", []string{"A", "B"}, "B", func(*RunCtx, string) TaskState { return h1State{} }})
	register(simpleTask{"H2", one, "A", func(*RunCtx, string) TaskState { return h2State{} }})
	register(simpleTask{"H3", []string{"A", "B", "C"}, "A", func(*RunCtx, string) TaskState { return h3State{} }})
}

func decodeB64(s string) ([]byte, error) {
	return base64.StdEncoding.DecodeString(strings.TrimSpace(s))
}
