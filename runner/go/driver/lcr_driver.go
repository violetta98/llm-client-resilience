// Go driver, compiled together with the solution (package main) and a glue
// file `var lcrTarget any = <Function>`. Same protocol and result schema
// (result/1) as runner/python/driver.py. All identifiers are prefixed "lcr"
// to avoid collisions with solution code.
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"reflect"
	"runtime"
	"runtime/debug"
	"strings"
	"sync"
	"syscall"
	"time"
	"unsafe"
)

// lcrMono returns absolute CLOCK_MONOTONIC ns (raw syscall: no extra modules).
func lcrMono() int64 {
	var ts syscall.Timespec
	syscall.Syscall(syscall.SYS_CLOCK_GETTIME, 1 /* CLOCK_MONOTONIC */, uintptr(unsafe.Pointer(&ts)), 0)
	return ts.Nano()
}

type lcrPlan struct {
	Nonce      string            `json:"nonce"`
	Function   string            `json:"function"`
	Mode       string            `json:"mode"`
	WarmupArgs []json.RawMessage `json:"warmup_args"`
	Calls      []struct {
		Args []json.RawMessage `json:"args"`
	} `json:"calls"`
	LimitS       float64  `json:"limit_s"`
	LingerS      float64  `json:"linger_s"`
	WarmupLimitS float64  `json:"warmup_limit_s"`
	ObserveS     float64  `json:"observe_s"`
	InspectPaths []string `json:"inspect_paths"`
}

type lcrErr struct {
	Type     string  `json:"type"`
	Message  string  `json:"message"`
	Timeout  *bool   `json:"net_timeout,omitempty"`
	Deadline bool    `json:"is_deadline_exceeded,omitempty"`
	Canceled bool    `json:"is_canceled,omitempty"`
	Panic    bool    `json:"panic,omitempty"`
	Stack    string  `json:"stack,omitempty"`
	Chain    *lcrErr `json:"chain,omitempty"`
}

type lcrVal struct {
	Enc       string `json:"enc"`
	Type      string `json:"type"`
	Len       int    `json:"len"`
	Data      string `json:"data"`
	Truncated bool   `json:"truncated,omitempty"`
}

type lcrCall struct {
	Index    int      `json:"index"`
	Status   string   `json:"status,omitempty"`
	TStart   int64    `json:"t_start"`
	TEnd     *int64   `json:"t_end"`
	Duration *float64 `json:"duration_s,omitempty"`
	Value    *lcrVal  `json:"value,omitempty"`
	Error    *lcrErr  `json:"error,omitempty"`
}

type lcrResult struct {
	Schema  string           `json:"schema"`
	Lang    string           `json:"lang"`
	Runtime map[string]any   `json:"runtime"`
	Func    string           `json:"function"`
	Mode    string           `json:"mode"`
	LimitS  float64          `json:"limit_s"`
	Env     map[string]any   `json:"env"`
	Import  map[string]any   `json:"import"`
	Warmup  *lcrCall         `json:"warmup"`
	Calls   []*lcrCall       `json:"calls"`
	TReady  *int64           `json:"t_ready"`
	TStart  *int64           `json:"t_start"`
	TEnd    *int64           `json:"t_end"`
	Status  string           `json:"status"`
	LingerS float64          `json:"linger_s,omitempty"`
	Files   []map[string]any `json:"files"`
}

var (
	lcrMarker   *os.File
	lcrMu       sync.Mutex
	lcrPlanV    lcrPlan
	lcrRes      lcrResult
	lcrFinished bool
)

func lcrEmit(kind, payload string) {
	lcrMu.Lock()
	defer lcrMu.Unlock()
	fmt.Fprintf(lcrMarker, "@@LCR %s %s %s\n", lcrPlanV.Nonce, kind, payload)
}

func lcrFinish(status string, exitAfter float64) {
	lcrMu.Lock()
	if lcrFinished {
		lcrMu.Unlock()
		return
	}
	lcrFinished = true
	lcrRes.Status = status
	lcrRes.Files = lcrInspect(lcrPlanV.InspectPaths)
	b, err := json.Marshal(&lcrRes)
	lcrMu.Unlock()
	if err != nil {
		b = []byte(fmt.Sprintf(`{"schema":"result/1","status":"bad_result_json","error":%q}`, err.Error()))
	}
	lcrEmit("RESULT", string(b))
	if exitAfter > 0 {
		time.Sleep(time.Duration(exitAfter * float64(time.Second)))
	}
	lcrEmit("EXIT", fmt.Sprint(lcrMono()))
	os.Exit(0)
}

func lcrDescribe(err error, depth int) *lcrErr {
	if err == nil {
		return nil
	}
	e := &lcrErr{Type: fmt.Sprintf("%T", err), Message: lcrTrunc(err.Error(), 4000)}
	var ne net.Error
	if errors.As(err, &ne) {
		t := ne.Timeout()
		e.Timeout = &t
	}
	e.Deadline = errors.Is(err, context.DeadlineExceeded) || errors.Is(err, os.ErrDeadlineExceeded)
	e.Canceled = errors.Is(err, context.Canceled)
	if u := errors.Unwrap(err); u != nil && depth < 5 {
		e.Chain = lcrDescribe(u, depth+1)
	}
	return e
}

func lcrTrunc(s string, n int) string {
	if len(s) > n {
		return s[:n]
	}
	return s
}

func lcrEncode(v any) *lcrVal {
	out := &lcrVal{Enc: "json", Type: fmt.Sprintf("%T", v)}
	b, err := json.Marshal(v)
	s := string(b)
	if err != nil {
		out.Enc, s = "repr", fmt.Sprintf("%+v", v)
	}
	out.Len = len(s)
	if len(s) > 64<<10 {
		s, out.Truncated = s[:64<<10], true
	}
	out.Data = s
	return out
}

var lcrCtxType = reflect.TypeOf((*context.Context)(nil)).Elem()
var lcrErrType = reflect.TypeOf((*error)(nil)).Elem()

// lcrInvoke calls lcrTarget with JSON arguments converted to its parameter
// types; a leading context.Context parameter gets context.Background().
func lcrInvoke(args []json.RawMessage) (val any, err error) {
	fv := reflect.ValueOf(lcrTarget)
	ft := fv.Type()
	if ft.Kind() != reflect.Func {
		return nil, fmt.Errorf("lcr: target is %s, not a function", ft)
	}
	var in []reflect.Value
	ai := 0
	for i := 0; i < ft.NumIn(); i++ {
		pt := ft.In(i)
		if pt == lcrCtxType {
			in = append(in, reflect.ValueOf(context.Background()))
			continue
		}
		if ai >= len(args) {
			return nil, fmt.Errorf("lcr: signature %s needs more arguments than the %d provided", ft, len(args))
		}
		p := reflect.New(pt)
		if e := json.Unmarshal(args[ai], p.Interface()); e != nil {
			return nil, fmt.Errorf("lcr: argument %d (%s): %v", ai, pt, e)
		}
		in = append(in, p.Elem())
		ai++
	}
	if ai != len(args) {
		return nil, fmt.Errorf("lcr: signature %s takes %d arguments, %d provided", ft, ai, len(args))
	}
	outs := fv.Call(in)
	for _, o := range outs {
		if o.Type().Implements(lcrErrType) && o.Type().Kind() == reflect.Interface {
			if !o.IsNil() {
				err = o.Interface().(error)
			}
		} else if val == nil {
			val = o.Interface()
		}
	}
	return val, err
}

func lcrRunOne(args []json.RawMessage, index int, tStart int64) (c *lcrCall) {
	c = &lcrCall{Index: index, TStart: tStart}
	defer func() {
		if p := recover(); p != nil {
			t := lcrMono()
			d := float64(t-tStart) / 1e9
			c.Status, c.TEnd, c.Duration = "raised", &t, &d
			c.Error = &lcrErr{Type: fmt.Sprintf("panic(%T)", p), Message: lcrTrunc(fmt.Sprint(p), 4000), Panic: true, Stack: lcrTrunc(string(debug.Stack()), 8000)}
		}
	}()
	v, err := lcrInvoke(args)
	t := lcrMono()
	d := float64(t-tStart) / 1e9
	c.TEnd, c.Duration = &t, &d
	if err != nil {
		c.Status, c.Error = "raised", lcrDescribe(err, 0)
		if strings.HasPrefix(err.Error(), "lcr: ") {
			c.Status = "harness_error"
		}
		return c
	}
	c.Status, c.Value = "returned", lcrEncode(v)
	return c
}

func lcrInspect(paths []string) []map[string]any {
	out := []map[string]any{}
	for _, p := range paths {
		d := map[string]any{"path": p, "exists": false}
		if st, err := os.Stat(p); err == nil && st.Mode().IsRegular() {
			if b, err := os.ReadFile(p); err == nil {
				h := sha256.Sum256(b)
				d["exists"], d["size"], d["sha256"] = true, len(b), hex.EncodeToString(h[:])
			}
		}
		out = append(out, d)
	}
	return out
}

func lcrEnv() map[string]any {
	sc := map[string]string{}
	for _, p := range []string{"net/ipv4/tcp_syn_retries", "net/ipv4/tcp_synack_retries", "net/ipv4/tcp_retries1",
		"net/ipv4/tcp_retries2", "net/ipv4/tcp_keepalive_time", "net/ipv4/tcp_keepalive_intvl",
		"net/ipv4/tcp_keepalive_probes", "net/ipv4/tcp_fin_timeout", "net/ipv4/ip_local_port_range",
		"net/ipv4/tcp_tw_reuse", "net/core/somaxconn"} {
		b, err := os.ReadFile("/proc/sys/" + p)
		k := strings.ReplaceAll(p, "/", ".")
		if err != nil {
			sc[k] = "unreadable: " + err.Error()
		} else {
			sc[k] = strings.TrimSpace(string(b))
		}
	}
	var u syscall.Utsname
	syscall.Uname(&u)
	cs := func(a [65]int8) string {
		var b []byte
		for _, c := range a {
			if c == 0 {
				break
			}
			b = append(b, byte(c))
		}
		return string(b)
	}
	host, _ := os.Hostname()
	return map[string]any{"sysctl": sc, "kernel": cs(u.Release), "uname": cs(u.Sysname) + " " + cs(u.Nodename) + " " + cs(u.Release) + " " + cs(u.Version) + " " + cs(u.Machine),
		"cpus": runtime.NumCPU(), "gomaxprocs": runtime.GOMAXPROCS(0), "uid": os.Getuid(), "hostname": host}
}

func main() {
	planPath := os.Getenv("LCR_PLAN")
	if planPath == "" {
		planPath = "/plan/plan.json"
	}
	b, err := os.ReadFile(planPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "lcr: plan:", err)
		os.Exit(2)
	}
	if err := json.Unmarshal(b, &lcrPlanV); err != nil {
		fmt.Fprintln(os.Stderr, "lcr: plan:", err)
		os.Exit(2)
	}
	// Markers on a duplicate of fd 1; the solution's stdout goes to stderr.
	mfd, _ := syscall.Dup(1)
	lcrMarker = os.NewFile(uintptr(mfd), "markers")
	syscall.Dup3(2, 1, 0)

	bi, _ := debug.ReadBuildInfo()
	deps := map[string]string{}
	if bi != nil {
		for _, d := range bi.Deps {
			deps[d.Path] = d.Version
		}
	}
	lcrRes = lcrResult{Schema: "result/1", Lang: "go", Func: lcrPlanV.Function, Mode: lcrPlanV.Mode, LimitS: lcrPlanV.LimitS,
		Runtime: map[string]any{"go": runtime.Version(), "deps": deps}, Env: lcrEnv(),
		Import: map[string]any{"ok": true, "signature": reflect.TypeOf(lcrTarget).String()}}

	// --- warm-up -------------------------------------------------------------
	wl := lcrPlanV.WarmupLimitS
	if wl == 0 {
		wl = 60
	}
	wt := time.AfterFunc(time.Duration(wl*float64(time.Second)), func() { lcrFinish("warmup_no_return", 0) })
	lcrRes.Warmup = lcrRunOne(lcrPlanV.WarmupArgs, 0, lcrMono())
	wt.Stop()

	// --- measured call(s) ----------------------------------------------------
	tr := lcrMono()
	lcrRes.TReady = &tr
	lcrEmit("READY", fmt.Sprint(tr))
	ts := lcrMono()
	lcrRes.TStart = &ts
	lcrEmit("START", fmt.Sprint(ts))
	n := len(lcrPlanV.Calls)
	calls := make([]*lcrCall, n)
	var cmu sync.Mutex
	starts := make([]int64, n)
	lcrMu.Lock()
	lcrRes.Calls = calls
	lcrMu.Unlock()
	remaining := time.Duration(lcrPlanV.LimitS*float64(time.Second)) - time.Duration(lcrMono()-ts)
	timer := time.AfterFunc(remaining, func() {
		lcrMu.Lock()
		cmu.Lock()
		for i := range calls {
			if calls[i] == nil {
				st := starts[i]
				if st == 0 {
					st = ts
				}
				calls[i] = &lcrCall{Index: i, Status: "no_return", TStart: st}
			}
		}
		cmu.Unlock()
		lcrMu.Unlock()
		lcrFinish("no_return", 0)
	})
	if n == 1 {
		starts[0] = ts
		c := lcrRunOne(lcrPlanV.Calls[0].Args, 0, ts)
		cmu.Lock()
		calls[0] = c
		cmu.Unlock()
	} else {
		var wg sync.WaitGroup
		gate := make(chan struct{})
		for i := range lcrPlanV.Calls {
			wg.Add(1)
			go func(i int) {
				defer wg.Done()
				<-gate
				st := lcrMono()
				cmu.Lock()
				starts[i] = st
				cmu.Unlock()
				c := lcrRunOne(lcrPlanV.Calls[i].Args, i, st)
				cmu.Lock()
				calls[i] = c
				cmu.Unlock()
			}(i)
		}
		close(gate)
		wg.Wait()
	}
	if !timer.Stop() {
		select {} // the watchdog is reporting no_return and exits
	}
	te := lcrMono()
	lcrMu.Lock()
	lcrRes.TEnd = &te
	lcrMu.Unlock()
	lcrEmit("END", fmt.Sprint(te))
	status := "mixed"
	all := func(s string) bool {
		for _, c := range calls {
			if c.Status != s {
				return false
			}
		}
		return true
	}
	if all("returned") {
		status = "returned"
	} else if all("raised") {
		status = "raised"
	}
	linger := lcrPlanV.LingerS
	if obs := lcrPlanV.ObserveS - float64(lcrMono()-ts)/1e9; obs > linger {
		linger = obs
	}
	lcrRes.LingerS = linger
	lcrFinish(status, linger)
}
