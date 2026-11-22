package main

import (
	"encoding/json"
	"fmt"
	"sort"
	"sync"
)

// Effect is a state change caused by a request (draft Section IV-C: effects
// are logged separately from requests).
type Effect struct {
	Kind   string         `json:"kind"` // e.g. payment_created, sms_sent
	Key    string         `json:"key"`  // logical identity (payment id, event id, record id)
	Detail map[string]any `json:"detail,omitempty"`
}

// TaskState is the per-run, per-role (measured vs warm-up) state of a task's
// dependencies.
type TaskState interface {
	// Classify returns the logical-call key of a request (page cursor, record
	// ID, event ID, supplier, ...; "" if none) and whether the request is the
	// faulted request of draft Table IV for scenarios S3-S8.
	Classify(dep string, r *Request) (key string, target bool)
	// Handle produces the normal (fault-free) response and the effects it
	// commits. It is called exactly once per request that is processed
	// (including S8, where the response is then replaced by a reset).
	Handle(dep string, r *Request) (*Response, []Effect)
}

// RunCtx is shared by the measured and warm-up states of one run (e.g. B3
// tokens issued on the warm-up port are valid on the measured API).
type RunCtx struct {
	RunID  string
	Shared sync.Map
}

type Task interface {
	ID() string
	Deps() []string // dependency names, mapped to ports 9001.. in order
	DefaultFaultDep() string
	NewState(rc *RunCtx, role string) TaskState
}

var registry = map[string]Task{}

func register(t Task) { registry[t.ID()] = t }

func taskIDs() []string {
	ids := make([]string, 0, len(registry))
	for id := range registry {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}

func jsonResp(status int, v any, extra ...Header) *Response {
	b, err := json.Marshal(v)
	if err != nil {
		panic(fmt.Sprintf("jsonResp: %v", err))
	}
	h := append([]Header{{"Content-Type", "application/json"}}, extra...)
	return &Response{Status: status, Headers: h, Body: b}
}

func errResp(status int, code, msg string, extra ...Header) *Response {
	return jsonResp(status, map[string]string{"error": code, "message": msg}, extra...)
}
