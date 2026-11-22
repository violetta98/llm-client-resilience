package main

// Unit tests of the confirmatory tasks R6, W5, B5, H4 (mock/tasks_confirm.go):
// normal behavior, logical keys, faulted requests, S4 applicability (the body
// fits the trickle length), and the literal values that
// tests/unit/test_confirm_tasks.py asserts for analysis/checkers_confirm.py.

import (
	"encoding/json"
	"io"
	"net/url"
	"testing"
	"time"
)

func TestConfirmTasks(t *testing.T) {
	t.Run("R6 stock", func(t *testing.T) {
		r := start(t, RunConfig{Task: "R6", Scenario: "S0", LatencyMS: 1})
		rs := req(t, 9001, "GET", "/v1/products/prd-042/stock", nil, "")
		m := js(t, rs.body)
		whs := m["warehouses"].([]any)
		w1 := whs[0].(map[string]any)
		w24 := whs[23].(map[string]any)
		if rs.status != 200 || m["product_id"] != "prd-042" || len(whs) != 24 || w1["warehouse_id"] != "wh-01" ||
			w1["available"].(float64) != 655 || w1["reserved"].(float64) != 49 || w24["available"].(float64) != 978 ||
			w24["reserved"].(float64) != 10 || m["updated_at"] != "2026-03-01T06:00:00Z" {
			t.Fatalf("%d %s", rs.status, rs.body)
		}
		if len(rs.body) >= 4096 {
			t.Fatalf("body %d bytes: S4 would truncate it", len(rs.body))
		}
		q := lastReq(t, r)
		if q["logical_key"] != "stock:prd-042" || q["faulted_request"] != true {
			t.Fatalf("classify %v %v", q["logical_key"], q["faulted_request"])
		}
		if rs := req(t, 9001, "GET", "/v1/products/x-1/stock", nil, ""); rs.status != 404 {
			t.Fatal("unknown product accepted")
		}
		if rs := req(t, 9001, "POST", "/v1/products/prd-042/stock", nil, ""); rs.status != 405 {
			t.Fatal("POST accepted")
		}
		finish(t)
	})
	t.Run("R6 S5a: two 503 then 200", func(t *testing.T) {
		start(t, RunConfig{Task: "R6", Scenario: "S5a", LatencyMS: 1})
		var got []int
		for i := 0; i < 3; i++ {
			got = append(got, req(t, 9001, "GET", "/v1/products/prd-042/stock", nil, "").status)
		}
		if got[0] != 503 || got[1] != 503 || got[2] != 200 {
			t.Fatal(got)
		}
		finish(t)
	})
	t.Run("W5 idempotency", func(t *testing.T) {
		r := start(t, RunConfig{Task: "W5", Scenario: "S0", LatencyMS: 1})
		body := `{"customer_id":"cus-042","subject":"Invoice shows the wrong address","message":"old address"}`
		k := map[string]string{"Idempotency-Key": "k1", "Content-Type": "application/json"}
		ra := req(t, 9001, "POST", "/v1/tickets", k, body)
		a := js(t, ra.body)
		b := js(t, req(t, 9001, "POST", "/v1/tickets", k, body).body)
		if ra.status != 201 || a["id"] != b["id"] || a["status"] != "open" || a["customer_id"] != "cus-042" ||
			a["subject"] != "Invoice shows the wrong address" {
			t.Fatalf("replay differs: %v %v", a, b)
		}
		q := lastReq(t, r)
		if q["logical_key"] != "ticket:cus-042" || q["faulted_request"] != true {
			t.Fatalf("classify %v", q)
		}
		if rs := req(t, 9001, "POST", "/v1/tickets", k, `{"customer_id":"cus-042","subject":"other","message":"x"}`); rs.status != 422 {
			t.Fatalf("key reuse with other body: %d", rs.status)
		}
		c := js(t, req(t, 9001, "POST", "/v1/tickets", nil, body).body) // no key: new ticket
		if c["id"] == a["id"] {
			t.Fatal("no-key request replayed")
		}
		for _, bad := range []string{`{"customer_id":"c-1","subject":"s","message":"m"}`, `{"customer_id":"cus-001","subject":"","message":"m"}`,
			`{"customer_id":"cus-001","subject":"s","message":" "}`, `not json`} {
			if rs := req(t, 9001, "POST", "/v1/tickets", nil, bad); rs.status != 400 {
				t.Fatalf("accepted %s", bad)
			}
		}
		finish(t)
		created, replayed := 0, 0
		for _, e := range readJSONL(t, r, "effects.jsonl") {
			switch e["kind"] {
			case "ticket_created":
				created++
			case "ticket_replayed":
				replayed++
			}
		}
		if created != 2 || replayed != 1 {
			t.Fatalf("tickets created = %d replayed = %d, want 2, 1", created, replayed)
		}
	})
	t.Run("W5 warm-up ids differ from measured ids", func(t *testing.T) {
		start(t, RunConfig{Task: "W5", Scenario: "S0", LatencyMS: 1})
		body := `{"customer_id":"cus-000","subject":"warm-up","message":"warm-up"}`
		w := js(t, req(t, 9101, "POST", "/v1/tickets", nil, body).body)
		d := js(t, req(t, 9001, "POST", "/v1/tickets", nil, body).body)
		if w["id"] != "tkt_w000001" || d["id"] != "tkt_000001" {
			t.Fatal(w, d)
		}
		finish(t)
	})
	t.Run("B5 updates, pagination ends, keys", func(t *testing.T) {
		r := start(t, RunConfig{Task: "B5", Scenario: "S0", LatencyMS: 1})
		target := "/v1/carriers/car-042/shipment-updates?since=" + url.QueryEscape("2026-03-01T00:00:00Z")
		rs := req(t, 9001, "GET", target, nil, "")
		m := js(t, rs.body)
		ups := m["updates"].([]any)
		u1 := ups[0].(map[string]any)
		u25 := ups[24].(map[string]any)
		if rs.status != 200 || len(ups) != 25 || u1["shipment_id"] != "shp-042-001" || u1["status"] != "delivered" ||
			u1["updated_at"] != "2026-03-01T00:17:00Z" || u25["updated_at"] != "2026-03-01T07:05:00Z" || u25["status"] != "out_for_delivery" ||
			m["next_since"] != "2026-03-01T07:05:00Z" {
			t.Fatalf("%d %s", rs.status, rs.body)
		}
		if len(rs.body) >= 4096 {
			t.Fatalf("body %d bytes: S4 would truncate it", len(rs.body))
		}
		q := lastReq(t, r)
		if q["logical_key"] != "updates:car-042|2026-03-01T00:00:00Z" || q["faulted_request"] != true {
			t.Fatalf("classify %v", q["logical_key"])
		}
		// unencoded colons are accepted too
		if m := js(t, req(t, 9001, "GET", "/v1/carriers/car-042/shipment-updates?since=2026-03-01T07:00:00Z", nil, "").body); len(m["updates"].([]any)) != 1 {
			t.Fatal(m)
		}
		last := js(t, req(t, 9001, "GET", "/v1/carriers/car-042/shipment-updates?since="+url.QueryEscape("2026-03-01T07:05:00Z"), nil, "").body)
		if len(last["updates"].([]any)) != 0 || last["next_since"] != nil {
			t.Fatal("following next_since does not end:", last)
		}
		if rs := req(t, 9001, "GET", "/v1/carriers/car-042/shipment-updates?since=yesterday", nil, ""); rs.status != 400 {
			t.Fatal("invalid since accepted")
		}
		if rs := req(t, 9001, "GET", "/v1/carriers/dhl/shipment-updates?since=2026-03-01T00:00:00Z", nil, ""); rs.status != 404 {
			t.Fatal("unknown carrier accepted")
		}
		finish(t)
	})
	t.Run("B5 S6a: 429 with Retry-After on the first attempt", func(t *testing.T) {
		start(t, RunConfig{Task: "B5", Scenario: "S6a", LatencyMS: 1})
		target := "/v1/carriers/car-042/shipment-updates?since=2026-03-01T00:00:00Z"
		a := req(t, 9001, "GET", target, nil, "")
		b := req(t, 9001, "GET", target, nil, "")
		if a.status != 429 || a.hdr.Get("Retry-After") != "3" || b.status != 200 {
			t.Fatal(a.status, b.status)
		}
		finish(t)
	})
	t.Run("H4 preferences differ from the default in every field", func(t *testing.T) {
		r := start(t, RunConfig{Task: "H4", Scenario: "S0", LatencyMS: 1})
		rs := req(t, 9001, "GET", "/v1/users/u-042/notification-preferences", nil, "")
		var m map[string]any
		if err := json.Unmarshal(rs.body, &m); err != nil || rs.status != 200 || m["user_id"] != "u-042" ||
			m["email"] != false || m["sms"] != true || m["push"] != true {
			t.Fatalf("%d %s", rs.status, rs.body)
		}
		if q := lastReq(t, r); q["logical_key"] != "prefs:u-042" || q["faulted_request"] != true {
			t.Fatalf("classify %v", q)
		}
		if rs := req(t, 9001, "GET", "/v1/users/nobody/notification-preferences", nil, ""); rs.status != 404 {
			t.Fatal("unknown user accepted")
		}
		finish(t)
	})
	t.Run("H4 S3: the request stalls", func(t *testing.T) {
		start(t, RunConfig{Task: "H4", Scenario: "S3", LatencyMS: 1})
		c := dialTLS(t, 9001)
		io.WriteString(c, get("/v1/users/u-042/notification-preferences"))
		c.SetReadDeadline(time.Now().Add(500 * time.Millisecond))
		if n, _ := c.Read(make([]byte, 1)); n != 0 {
			t.Fatal("a stalled request got a response")
		}
		c.Close()
		time.Sleep(100 * time.Millisecond)
		finish(t)
	})
	t.Run("trickle body keeps the full JSON (S4 applies)", func(t *testing.T) {
		for _, b := range [][]byte{mustJSON(t, r6Stock("prd-042")), mustJSON(t, map[string]any{"updates": b5Updates("car-042", b5Day), "next_since": "x"})} {
			var v any
			if err := json.Unmarshal(trickleBody(b, 4096), &v); err != nil {
				t.Fatalf("trickled body does not parse: %v", err)
			}
		}
	})
}

func mustJSON(t *testing.T, v any) []byte {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	return b
}
