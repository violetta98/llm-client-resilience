package main

import (
	"bufio"
	"encoding/base64"
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"unicode/utf8"
)

// jsonl is an append-only JSON-lines writer that flushes after every record,
// so a crash loses nothing that was already observed.
type jsonl struct {
	mu sync.Mutex
	f  *os.File
	w  *bufio.Writer
	n  int
}

func openJSONL(dir, name string) (*jsonl, error) {
	f, err := os.OpenFile(filepath.Join(dir, name), os.O_CREATE|os.O_WRONLY|os.O_EXCL, 0o644)
	if err != nil {
		return nil, err
	}
	return &jsonl{f: f, w: bufio.NewWriter(f)}, nil
}

func (j *jsonl) Write(v any) {
	if j == nil {
		return
	}
	b, err := json.Marshal(v)
	if err != nil {
		b, _ = json.Marshal(map[string]string{"marshal_error": err.Error()})
	}
	j.mu.Lock()
	defer j.mu.Unlock()
	if j.f == nil {
		return
	}
	j.w.Write(b)
	j.w.WriteByte('\n')
	j.w.Flush()
	j.n++
}

func (j *jsonl) Close() int {
	if j == nil {
		return 0
	}
	j.mu.Lock()
	defer j.mu.Unlock()
	if j.f != nil {
		j.w.Flush()
		j.f.Sync()
		j.f.Close()
		j.f = nil
	}
	return j.n
}

const maxLoggedBody = 64 << 10

// Body is a logged message body: UTF-8 text verbatim, otherwise base64;
// truncated to 64 KiB with the full length recorded.
type Body struct {
	Len       int    `json:"len"`
	Encoding  string `json:"enc,omitempty"` // "utf8" | "base64"
	Data      string `json:"data,omitempty"`
	Truncated bool   `json:"truncated,omitempty"`
}

func logBody(b []byte) Body {
	out := Body{Len: len(b)}
	if len(b) == 0 {
		return out
	}
	if len(b) > maxLoggedBody {
		b = b[:maxLoggedBody]
		out.Truncated = true
	}
	if utf8.Valid(b) {
		out.Encoding, out.Data = "utf8", string(b)
	} else {
		out.Encoding, out.Data = "base64", base64.StdEncoding.EncodeToString(b)
	}
	return out
}
