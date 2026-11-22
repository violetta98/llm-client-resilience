// lcr-prepare: builds a Go solution together with the driver (no network).
// Input: /src/solution.go, /src/target.txt (function name).
// Output: /out/solution.bin, /out/prepare.json, /out/build/ (exact sources compiled).
package main

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

var (
	rePkg     = regexp.MustCompile(`(?m)^package\s+[A-Za-z_][A-Za-z0-9_]*`)
	reMain    = regexp.MustCompile(`(?m)^func\s+main\s*\(\s*\)`)
	reMissing = regexp.MustCompile(`(?m)(no required module provides package|cannot find package|package \S+ is not in std|cannot find module providing package)\s*"?([^\s";:]+)?`)
	reIdent   = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)
)

func main() {
	t0 := time.Now()
	out := map[string]any{"schema": "prepare/1", "lang": "go"}
	finish := func(cat string) {
		out["category"] = cat
		out["duration_s"] = time.Since(t0).Seconds()
		b, _ := json.MarshalIndent(out, "", " ")
		os.WriteFile("/out/prepare.json", b, 0o644)
		os.Exit(0)
	}
	ver, _ := exec.Command("go", "version").Output()
	out["tool"] = strings.TrimSpace(string(ver))
	src, err := os.ReadFile("/src/solution.go")
	if err != nil {
		out["errors"] = []string{err.Error()}
		finish("harness_error")
	}
	tb, _ := os.ReadFile("/src/target.txt")
	target := strings.TrimSpace(string(tb))
	if !reIdent.MatchString(target) {
		out["errors"] = []string{"bad target function name " + target}
		finish("harness_error")
	}
	s := string(src)
	rewrites := []string{}
	if loc := rePkg.FindStringIndex(s); loc != nil {
		if s[loc[0]:loc[1]] != "package main" {
			rewrites = append(rewrites, "package clause "+s[loc[0]:loc[1]]+" -> package main")
		}
		s = s[:loc[0]] + "package main" + s[loc[1]:]
	} else {
		s = "package main\n\n" + s
		rewrites = append(rewrites, "added package main")
	}
	if reMain.MatchString(s) {
		s = reMain.ReplaceAllString(s, "func lcrUnusedSolutionMain()")
		rewrites = append(rewrites, "renamed func main")
	}
	out["rewrites"] = rewrites
	b := "/tmp/build"
	os.MkdirAll(b, 0o755)
	cp := func(from, to string) {
		d, _ := os.ReadFile(from)
		os.WriteFile(filepath.Join(b, to), d, 0o644)
	}
	cp("/opt/lcr-go/libs/go.mod", "go.mod")
	cp("/opt/lcr-go/libs/go.sum", "go.sum")
	cp("/opt/lcr-go/driver/lcr_driver.go", "lcr_driver.go")
	os.WriteFile(filepath.Join(b, "solution.go"), []byte(s), 0o644)
	os.WriteFile(filepath.Join(b, "lcr_glue.go"), []byte("package main\n\nvar lcrTarget any = "+target+"\n"), 0o644)
	cmd := exec.Command("go", "build", "-trimpath", "-o", "/out/solution.bin", ".")
	cmd.Dir = b
	cmd.Env = append(os.Environ(), "GOFLAGS=-mod=mod", "GOPROXY=off", "GOTOOLCHAIN=local", "CGO_ENABLED=0",
		"GOCACHE=/gocache", "GOMODCACHE=/opt/lcr-go/pkg/mod", "HOME=/tmp")
	log, err := cmd.CombinedOutput()
	os.MkdirAll("/out/build", 0o755)
	for _, f := range []string{"solution.go", "lcr_glue.go"} {
		d, _ := os.ReadFile(filepath.Join(b, f))
		os.WriteFile(filepath.Join("/out/build", f), d, 0o644)
	}
	out["build_log"] = strings.TrimSpace(string(log))
	if err != nil {
		os.Remove("/out/solution.bin")
		if ms := reMissing.FindAllStringSubmatch(string(log), -1); ms != nil {
			var miss []string
			for _, m := range ms {
				miss = append(miss, m[2])
			}
			out["missing"] = miss
			finish("missing_dependency")
		}
		finish("compile_error")
	}
	finish("ok")
}
