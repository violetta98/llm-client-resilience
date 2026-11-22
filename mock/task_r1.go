package main

// R1 — Fetch a user profile (PROVISIONAL spec for E0; finalized and approved at E2).
//   GET {base}/v1/users/{user_id}
//   200 {"id","name","email","created_at"} for ids of the form u-NNN; 404 otherwise.

import (
	"fmt"
	"regexp"
	"strings"
)

type taskR1 struct{}

func (taskR1) ID() string                         { return "R1" }
func (taskR1) Deps() []string                     { return []string{"A"} }
func (taskR1) DefaultFaultDep() string            { return "A" }
func (taskR1) NewState(*RunCtx, string) TaskState { return &r1State{} }

type r1State struct{}

var r1Path = regexp.MustCompile(`^/v1/users/([^/]+)$`)

func (*r1State) Classify(dep string, r *Request) (string, bool) {
	if m := r1Path.FindStringSubmatch(r.Path); m != nil && r.Method == "GET" {
		return "user:" + m[1], true
	}
	return "", false
}

var r1ID = regexp.MustCompile(`^u-[0-9]{3}$`)

func (*r1State) Handle(dep string, r *Request) (*Response, []Effect) {
	m := r1Path.FindStringSubmatch(r.Path)
	if m == nil {
		return errResp(404, "not_found", "no such endpoint"), nil
	}
	if r.Method != "GET" {
		return errResp(405, "method_not_allowed", "use GET", Header{"Allow", "GET"}), nil
	}
	id := m[1]
	if !r1ID.MatchString(id) {
		return errResp(404, "not_found", "user not found"), nil
	}
	n := strings.TrimPrefix(id, "u-")
	return jsonResp(200, map[string]any{
		"id":         id,
		"name":       "User " + n,
		"email":      fmt.Sprintf("user%s@example.com", n),
		"created_at": "2024-01-15T09:30:00Z",
	}), nil
}

func init() { register(taskR1{}) }
