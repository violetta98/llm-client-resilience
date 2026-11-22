package main

// Minimal HTTP/1.1 wire handling. net/http is deliberately not used for the
// dependency ports: the scenarios need byte-level control over when (and
// whether) each byte of a response is written.

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const (
	maxHeaderBytes = 64 << 10
	maxBodyBytes   = 16 << 20
)

type Header struct {
	Name  string `json:"name"`
	Value string `json:"value"`
}

type Request struct {
	Method   string
	Target   string
	Path     string
	RawQuery string
	Query    url.Values
	Proto    string
	Headers  []Header
	Body     []byte
	Chunked  bool

	TFirstByte   int64
	THeadersDone int64
	TDone        int64
}

func (r *Request) Get(name string) string {
	for _, h := range r.Headers {
		if strings.EqualFold(h.Name, name) {
			return h.Value
		}
	}
	return ""
}

func (r *Request) Has(name string) bool {
	for _, h := range r.Headers {
		if strings.EqualFold(h.Name, name) {
			return true
		}
	}
	return false
}

// WantsClose reports whether the connection must be closed after the response.
func (r *Request) WantsClose() bool {
	c := strings.ToLower(r.Get("Connection"))
	if r.Proto == "HTTP/1.0" {
		return !strings.Contains(c, "keep-alive")
	}
	return strings.Contains(c, "close")
}

var (
	errNoRequest  = errors.New("connection closed before a request")
	errBadRequest = errors.New("malformed request")
)

// readLine reads one CRLF- (or LF-) terminated line, enforcing a byte budget.
func readLine(br *bufio.Reader, budget *int) (string, error) {
	var sb strings.Builder
	for {
		frag, err := br.ReadSlice('\n')
		*budget -= len(frag)
		if *budget < 0 {
			return "", fmt.Errorf("%w: header too large", errBadRequest)
		}
		sb.Write(frag)
		if err == nil {
			break
		}
		if err == bufio.ErrBufferFull {
			continue
		}
		return sb.String(), err
	}
	s := sb.String()
	s = strings.TrimSuffix(s, "\n")
	s = strings.TrimSuffix(s, "\r")
	return s, nil
}

// readRequest parses one request. onFirstByte is called as soon as the first
// byte of the request is available; onHeaders after the header block (used to
// send "100 Continue").
func readRequest(br *bufio.Reader, onFirstByte func() int64, onHeaders func(*Request) error) (*Request, error) {
	if _, err := br.Peek(1); err != nil {
		return nil, errNoRequest
	}
	req := &Request{TFirstByte: onFirstByte()}
	budget := maxHeaderBytes
	var line string
	var err error
	for {
		line, err = readLine(br, &budget)
		if err != nil {
			return req, fmt.Errorf("%w: %v", errBadRequest, err)
		}
		if line != "" { // RFC 9112 §2.2: ignore leading empty lines
			break
		}
	}
	parts := strings.SplitN(line, " ", 3)
	if len(parts) != 3 || !strings.HasPrefix(parts[2], "HTTP/1.") {
		return req, fmt.Errorf("%w: request line %q", errBadRequest, line)
	}
	req.Method, req.Target, req.Proto = parts[0], parts[1], parts[2]
	u, perr := url.ParseRequestURI(req.Target)
	if perr != nil {
		return req, fmt.Errorf("%w: target %q", errBadRequest, req.Target)
	}
	req.Path, req.RawQuery = u.Path, u.RawQuery
	req.Query = u.Query()
	for {
		line, err = readLine(br, &budget)
		if err != nil {
			return req, fmt.Errorf("%w: %v", errBadRequest, err)
		}
		if line == "" {
			break
		}
		i := strings.IndexByte(line, ':')
		if i <= 0 {
			return req, fmt.Errorf("%w: header %q", errBadRequest, line)
		}
		req.Headers = append(req.Headers, Header{Name: line[:i], Value: strings.TrimSpace(line[i+1:])})
	}
	req.THeadersDone = monoNS()
	if onHeaders != nil {
		if err := onHeaders(req); err != nil {
			return req, err
		}
	}
	te := strings.ToLower(req.Get("Transfer-Encoding"))
	switch {
	case strings.Contains(te, "chunked"):
		req.Chunked = true
		body, err := readChunked(br)
		if err != nil {
			return req, err
		}
		req.Body = body
	case req.Has("Content-Length"):
		n, err := strconv.Atoi(strings.TrimSpace(req.Get("Content-Length")))
		if err != nil || n < 0 || n > maxBodyBytes {
			return req, fmt.Errorf("%w: content-length", errBadRequest)
		}
		req.Body = make([]byte, n)
		if _, err := io.ReadFull(br, req.Body); err != nil {
			return req, fmt.Errorf("%w: body: %v", errBadRequest, err)
		}
	}
	req.TDone = monoNS()
	return req, nil
}

func readChunked(br *bufio.Reader) ([]byte, error) {
	var body []byte
	budget := maxHeaderBytes
	for {
		line, err := readLine(br, &budget)
		if err != nil {
			return body, fmt.Errorf("%w: chunk size: %v", errBadRequest, err)
		}
		if i := strings.IndexByte(line, ';'); i >= 0 {
			line = line[:i]
		}
		n, err := strconv.ParseInt(strings.TrimSpace(line), 16, 64)
		if err != nil || n < 0 || int64(len(body))+n > maxBodyBytes {
			return body, fmt.Errorf("%w: chunk size %q", errBadRequest, line)
		}
		if n == 0 {
			for { // trailers
				t, err := readLine(br, &budget)
				if err != nil {
					return body, fmt.Errorf("%w: trailer: %v", errBadRequest, err)
				}
				if t == "" {
					return body, nil
				}
			}
		}
		chunk := make([]byte, n)
		if _, err := io.ReadFull(br, chunk); err != nil {
			return body, fmt.Errorf("%w: chunk: %v", errBadRequest, err)
		}
		body = append(body, chunk...)
		if _, err := readLine(br, &budget); err != nil {
			return body, fmt.Errorf("%w: chunk crlf: %v", errBadRequest, err)
		}
	}
}

type Response struct {
	Status  int
	Headers []Header
	Body    []byte
}

func httpDate(t time.Time) string { return t.UTC().Format(http.TimeFormat) }

// headBytes renders the status line and headers. Date is always set (from
// date, so callers can align it with Retry-After); Content-Length is always
// explicit; Connection is "close" when closeAfter is true.
func headBytes(status int, hdrs []Header, contentLength int, closeAfter bool, date time.Time) []byte {
	var sb strings.Builder
	fmt.Fprintf(&sb, "HTTP/1.1 %d %s\r\n", status, http.StatusText(status))
	fmt.Fprintf(&sb, "Date: %s\r\n", httpDate(date))
	for _, h := range hdrs {
		fmt.Fprintf(&sb, "%s: %s\r\n", h.Name, h.Value)
	}
	fmt.Fprintf(&sb, "Content-Length: %d\r\n", contentLength)
	if closeAfter {
		sb.WriteString("Connection: close\r\n")
	} else {
		sb.WriteString("Connection: keep-alive\r\n")
	}
	sb.WriteString("\r\n")
	return []byte(sb.String())
}
