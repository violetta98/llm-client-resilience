package main

// Unit tests of the task endpoints (normal behavior, logical keys, faulted
// requests) through the real server on 127.0.0.1.

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/url"
	"strings"
	"testing"
	"time"
)

func req(t *testing.T, port int, method, target string, hdr map[string]string, body string) *resp {
	t.Helper()
	c := dialTLS(t, port)
	defer c.Close()
	var sb strings.Builder
	fmt.Fprintf(&sb, "%s %s HTTP/1.1\r\nHost: x\r\n", method, target)
	for k, v := range hdr {
		fmt.Fprintf(&sb, "%s: %s\r\n", k, v)
	}
	fmt.Fprintf(&sb, "Content-Length: %d\r\n\r\n%s", len(body), body)
	rs, err := roundTrip(t, c, sb.String())
	if err != nil {
		t.Fatal(err)
	}
	return rs
}

func js(t *testing.T, b []byte) map[string]any {
	t.Helper()
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		t.Fatalf("json %q: %v", b, err)
	}
	return m
}

func lastReq(t *testing.T, r *Run) map[string]any {
	t.Helper()
	q := readJSONL(t, r, "requests.jsonl")
	return q[len(q)-1]
}

func TestTaskEndpoints(t *testing.T) {
	t.Run("P1 P2 P3 pilot", func(t *testing.T) {
		start(t, RunConfig{Task: "P1", Scenario: "S0", LatencyMS: 1})
		rs := req(t, 9001, "GET", "/v1/rates/EUR/USD", nil, "")
		m := js(t, rs.body)
		if rs.status != 200 || m["rate"].(float64) != p1Rate("EUR", "USD") || m["base"] != "EUR" {
			t.Fatalf("%d %s", rs.status, rs.body)
		}
		if rs := req(t, 9001, "GET", "/v1/rates/eur/USD", nil, ""); rs.status != 404 {
			t.Fatal("lower-case code accepted")
		}
		finish(t)
		r := start(t, RunConfig{Task: "P2", Scenario: "S0", LatencyMS: 1})
		rs = req(t, 9001, "POST", "/v1/tickets/t-042/comments", map[string]string{"Content-Type": "application/json"}, `{"text":"hi"}`)
		if rs.status != 201 || js(t, rs.body)["ticket_id"] != "t-042" {
			t.Fatalf("%d %s", rs.status, rs.body)
		}
		if rs := req(t, 9001, "POST", "/v1/tickets/t-042/comments", nil, `{"text":""}`); rs.status != 400 {
			t.Fatal("empty text accepted")
		}
		finish(t)
		if es := readJSONL(t, r, "effects.jsonl"); len(es) != 1 || es[0]["kind"] != "comment_created" {
			t.Fatalf("effects %v", es)
		}
		start(t, RunConfig{Task: "P3", Scenario: "S0", LatencyMS: 1})
		rs = req(t, 9001, "GET", "/v1/estimates?postal_code=30-042", nil, "")
		if rs.status != 200 || js(t, rs.body)["days"].(float64) != 2 {
			t.Fatalf("%d %s", rs.status, rs.body)
		}
		finish(t)
	})
	t.Run("R2", func(t *testing.T) {
		start(t, RunConfig{Task: "R2", Scenario: "S0", LatencyMS: 1})
		rs := req(t, 9001, "GET", "/v1/products?q=running+shoes&category=sports&max_price=120.0", nil, "")
		m := js(t, rs.body)
		items := m["items"].([]any)
		it := items[0].(map[string]any)
		if rs.status != 200 || len(items) != 3 || it["name"] != "Running Shoes 1" || it["price"].(float64) != 60 {
			t.Fatalf("%d %s", rs.status, rs.body)
		}
		if rs := req(t, 9001, "GET", "/v1/products?category=sports&max_price=1", nil, ""); rs.status != 400 {
			t.Fatal("missing q accepted")
		}
		finish(t)
	})
	t.Run("R3", func(t *testing.T) {
		start(t, RunConfig{Task: "R3", Scenario: "S0", LatencyMS: 1})
		rs := req(t, 9001, "GET", "/v1/reports/rep-042/download", nil, "")
		h := sha256.Sum256(rs.body)
		want := sha256.Sum256(reportContent("rep-042"))
		if rs.status != 200 || len(rs.body) != 65536 || h != want || rs.hdr.Get("Content-Type") != "application/octet-stream" {
			t.Fatalf("%d len=%d", rs.status, len(rs.body))
		}
		finish(t)
	})
	t.Run("R4 pages and faulted second page", func(t *testing.T) {
		r := start(t, RunConfig{Task: "R4", Scenario: "S0", LatencyMS: 1})
		var all []any
		cursor := ""
		for i := 0; i < 5; i++ {
			target := "/v1/customers/c-042/orders"
			if cursor != "" {
				target += "?cursor=" + url.QueryEscape(cursor)
			}
			m := js(t, req(t, 9001, "GET", target, nil, "").body)
			all = append(all, m["orders"].([]any)...)
			q := lastReq(t, r)
			if (i == 1) != (q["faulted_request"] == true) {
				t.Fatalf("page %d faulted=%v", i+1, q["faulted_request"])
			}
			if m["next_cursor"] == nil {
				break
			}
			cursor = m["next_cursor"].(string)
		}
		if len(all) != 120 || all[119].(map[string]any)["id"] != "o-042-120" {
			t.Fatalf("got %d orders", len(all))
		}
		finish(t)
	})
	t.Run("R5", func(t *testing.T) {
		start(t, RunConfig{Task: "R5", Scenario: "S0", LatencyMS: 1})
		if m := js(t, req(t, 9001, "GET", "/v1/flags/new-checkout", nil, "").body); m["enabled"] != true {
			t.Fatal(m)
		}
		finish(t)
	})
	t.Run("W1 idempotency", func(t *testing.T) {
		r := start(t, RunConfig{Task: "W1", Scenario: "S0", LatencyMS: 1})
		body := `{"order_id":"ord-042","amount":"49.90","currency":"EUR"}`
		k := map[string]string{"Idempotency-Key": "k1", "Content-Type": "application/json"}
		a := js(t, req(t, 9001, "POST", "/v1/payments", k, body).body)
		b := js(t, req(t, 9001, "POST", "/v1/payments", k, body).body)
		if a["id"] != b["id"] || a["status"] != "succeeded" {
			t.Fatalf("replay differs: %v %v", a, b)
		}
		if rs := req(t, 9001, "POST", "/v1/payments", k, `{"order_id":"ord-042","amount":"1.00","currency":"EUR"}`); rs.status != 422 {
			t.Fatalf("key reuse with other body: %d", rs.status)
		}
		c := js(t, req(t, 9001, "POST", "/v1/payments", nil, body).body) // no key: new payment
		if c["id"] == a["id"] {
			t.Fatal("no-key request replayed")
		}
		if rs := req(t, 9001, "POST", "/v1/payments", nil, `{"order_id":"x","amount":"49.9","currency":"EUR"}`); rs.status != 400 {
			t.Fatal("bad amount accepted")
		}
		finish(t)
		n := 0
		for _, e := range readJSONL(t, r, "effects.jsonl") {
			if e["kind"] == "payment_created" {
				n++
			}
		}
		if n != 2 {
			t.Fatalf("payments created = %d, want 2", n)
		}
	})
	t.Run("W2", func(t *testing.T) {
		r := start(t, RunConfig{Task: "W2", Scenario: "S0", LatencyMS: 1})
		body := `{"to":"+48500100042","body":"hi"}`
		a := js(t, req(t, 9001, "POST", "/v1/messages", map[string]string{"Idempotency-Key": "k"}, body).body)
		b := js(t, req(t, 9001, "POST", "/v1/messages", map[string]string{"Idempotency-Key": "k"}, body).body)
		if a["id"] == b["id"] {
			t.Fatal("W2 must ignore Idempotency-Key")
		}
		finish(t)
		if n := len(readJSONL(t, r, "effects.jsonl")); n != 2 {
			t.Fatalf("sms effects %d", n)
		}
	})
	t.Run("W3", func(t *testing.T) {
		start(t, RunConfig{Task: "W3", Scenario: "S0", LatencyMS: 1})
		m := js(t, req(t, 9001, "PUT", "/v1/documents/doc-042", map[string]string{"Content-Type": "text/plain; charset=utf-8"}, "héllo").body)
		h := sha256.Sum256([]byte("héllo"))
		if m["sha256"] != hex.EncodeToString(h[:]) || m["size"].(float64) != 6 || m["version"].(float64) != 1 {
			t.Fatal(m)
		}
		finish(t)
	})
	t.Run("W4", func(t *testing.T) {
		start(t, RunConfig{Task: "W4", Scenario: "S0", LatencyMS: 1})
		if rs := req(t, 9001, "DELETE", "/v1/subscriptions/sub-042", nil, ""); rs.status != 200 {
			t.Fatal(rs.status)
		}
		if rs := req(t, 9001, "DELETE", "/v1/subscriptions/sub-042", nil, ""); rs.status != 404 {
			t.Fatal("second DELETE should be 404")
		}
		finish(t)
	})
	t.Run("B1 rate limit and fifth record", func(t *testing.T) {
		r := start(t, RunConfig{Task: "B1", Scenario: "S0", LatencyMS: 1})
		codes := map[int]int{}
		for i := 1; i <= 14; i++ { // burst of 14 within ~0.1 s: 10 pass, then 429
			id := fmt.Sprintf("rec-a42-%02d", i)
			rs := req(t, 9001, "PUT", "/v1/records/"+id, nil, fmt.Sprintf(`{"id":"%s","value":1}`, id))
			codes[rs.status]++
			if rs.status == 429 && rs.hdr.Get("Retry-After") != "1" {
				t.Fatal("429 without Retry-After: 1")
			}
			q := lastReq(t, r)
			if (i == 5) != (q["faulted_request"] == true) {
				t.Fatalf("record %d faulted=%v", i, q["faulted_request"])
			}
		}
		if codes[200] < 10 || codes[429] < 1 {
			t.Fatalf("codes %v", codes)
		}
		time.Sleep(1100 * time.Millisecond)
		if rs := req(t, 9001, "PUT", "/v1/records/rec-b00-01", nil, `{"id":"rec-b00-01"}`); rs.status != 200 {
			t.Fatal("other invocation rate-limited")
		}
		if rs := req(t, 9001, "PUT", "/v1/records/rec-a42-15", nil, `{"id":"rec-a42-99"}`); rs.status != 400 {
			t.Fatal("id mismatch accepted")
		}
		finish(t)
	})
	t.Run("B2 completes after 3 s; first status not faulted", func(t *testing.T) {
		r := start(t, RunConfig{Task: "B2", Scenario: "S0", LatencyMS: 1})
		m := js(t, req(t, 9001, "GET", "/v1/exports/exp-042", nil, "").body)
		if m["status"] != "running" || lastReq(t, r)["faulted_request"] == true {
			t.Fatal(m)
		}
		js(t, req(t, 9001, "GET", "/v1/exports/exp-042", nil, "").body)
		if lastReq(t, r)["faulted_request"] != true {
			t.Fatal("second status request not faulted")
		}
		time.Sleep(3 * time.Second)
		m = js(t, req(t, 9001, "GET", "/v1/exports/exp-042", nil, "").body)
		if m["status"] != "completed" || m["result_url"] != "https://files.example.com/exports/exp-042.csv" {
			t.Fatal(m)
		}
		finish(t)
	})
	t.Run("B3 tokens across ports, basic auth", func(t *testing.T) {
		start(t, RunConfig{Task: "B3", Scenario: "S0", LatencyMS: 1})
		form := map[string]string{"Content-Type": "application/x-www-form-urlencoded"}
		w := js(t, req(t, 9101, "POST", "/oauth/token", form, "grant_type=client_credentials&client_id=client-1&client_secret=s3cr3t").body)
		tok := w["access_token"].(string)
		m := js(t, req(t, 9002, "GET", "/v1/accounts/acc-042/balance", map[string]string{"Authorization": "Bearer " + tok}, "").body)
		if m["balance"] != "1250.00" {
			t.Fatalf("warm-up token rejected on measured API: %v", m)
		}
		if rs := req(t, 9002, "GET", "/v1/accounts/acc-042/balance", map[string]string{"Authorization": "Bearer nope"}, ""); rs.status != 401 {
			t.Fatal("bad token accepted")
		}
		basic := map[string]string{"Content-Type": "application/x-www-form-urlencoded", "Authorization": "Basic Y2xpZW50LTE6czNjcjN0"}
		if rs := req(t, 9001, "POST", "/oauth/token", basic, "grant_type=client_credentials"); rs.status != 200 {
			t.Fatalf("basic auth: %d", rs.status)
		}
		if rs := req(t, 9001, "POST", "/oauth/token", form, "grant_type=client_credentials&client_id=client-1&client_secret=x"); rs.status != 401 {
			t.Fatal("bad secret accepted")
		}
		finish(t)
	})
	t.Run("B4 dedup", func(t *testing.T) {
		r := start(t, RunConfig{Task: "B4", Scenario: "S0", LatencyMS: 1})
		ev := `{"id":"evt_042","type":"invoice.paid"}`
		a := js(t, req(t, 9001, "POST", "/hooks/acme", nil, ev).body)
		b := js(t, req(t, 9001, "POST", "/hooks/acme", nil, ev).body)
		if a["duplicate"] != nil || b["duplicate"] != true {
			t.Fatal(a, b)
		}
		finish(t)
		acc := 0
		for _, e := range readJSONL(t, r, "effects.jsonl") {
			if e["kind"] == "delivery_accepted" {
				acc++
			}
		}
		if acc != 1 {
			t.Fatal(acc)
		}
	})
	t.Run("H1", func(t *testing.T) {
		start(t, RunConfig{Task: "H1", Scenario: "S0", LatencyMS: 1})
		if m := js(t, req(t, 9001, "GET", "/v1/users/u-042", nil, "").body); m["id"] != "u-042" {
			t.Fatal(m)
		}
		m := js(t, req(t, 9002, "GET", "/v1/users/u-042/recommendations", nil, "").body)
		if len(m["items"].([]any)) != 3 {
			t.Fatal(m)
		}
		finish(t)
	})
	t.Run("H2", func(t *testing.T) {
		start(t, RunConfig{Task: "H2", Scenario: "S0", LatencyMS: 1})
		if m := js(t, req(t, 9001, "GET", "/instances/db-42/healthz", nil, "").body); m["status"] != "ok" {
			t.Fatal(m)
		}
		finish(t)
	})
	t.Run("H3 prices per supplier; fault only on A", func(t *testing.T) {
		start(t, RunConfig{Task: "H3", Scenario: "S5a", LatencyMS: 1})
		if rs := req(t, 9001, "GET", "/v1/quotes?sku=sku-042", nil, ""); rs.status != 503 {
			t.Fatal("A not faulted")
		}
		for port, want := range map[int]float64{9002: 10.10, 9003: 11.25} {
			if m := js(t, req(t, port, "GET", "/v1/quotes?sku=sku-042", nil, "").body); m["price"].(float64) != want {
				t.Fatal(m)
			}
		}
		finish(t)
	})
	t.Run("B2 S5: 2nd and 3rd status requests get 503", func(t *testing.T) {
		start(t, RunConfig{Task: "B2", Scenario: "S5a", LatencyMS: 1})
		var got []int
		for i := 0; i < 4; i++ {
			got = append(got, req(t, 9001, "GET", "/v1/exports/exp-042", nil, "").status)
		}
		if fmt.Sprint(got) != "[200 503 503 200]" {
			t.Fatal(got)
		}
		finish(t)
	})
}
