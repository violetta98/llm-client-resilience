// Advice check (D55, revised D56): retries with backoff and jitter under one context deadline for the whole call, body
// included. GetUserProfileContext takes the caller's context and adds at most 10 s; GetUserProfile is the signature
// of the benchmark task. Each attempt gets a child context with min(own timeout, time left); Retry-After is honored in
// both forms, a date relative to the server's Date header; a Retry-After that does not fit the time left fails at
// once; TLS certificate errors are not retried.
package main

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"strconv"
	"strings"
	"time"
)

const perAttempt = 4 * time.Second

func retryAfter(v, date string) (time.Duration, bool) {
	v = strings.TrimSpace(v)
	if v == "" {
		return 0, false
	}
	if s, err := strconv.Atoi(v); err == nil && s >= 0 {
		return time.Duration(min(s, 86400)) * time.Second, true // clamp: no overflow into a negative wait
	}
	if t, err := http.ParseTime(v); err == nil {
		now := time.Now() // a date is server time: measure it from the server's Date header when present
		if d, err := http.ParseTime(date); err == nil {
			now = d
		}
		if d := t.Sub(now); d > 0 {
			return d, true
		}
		return 0, true
	}
	return 0, false
}

// once returns (profile, Retry-After and Date of a retryable status, retryable?, error).
func once(ctx context.Context, url string) (map[string]any, [2]string, bool, error) {
	dl, _ := ctx.Deadline()
	budget := time.Until(dl)
	if budget <= 0 {
		return nil, [2]string{}, false, context.DeadlineExceeded
	}
	actx, cancel := context.WithTimeout(ctx, min(perAttempt, budget))
	defer cancel()
	req, err := http.NewRequestWithContext(actx, http.MethodGet, url, nil)
	if err != nil {
		return nil, [2]string{}, false, err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		var cerr *tls.CertificateVerificationError
		return nil, [2]string{}, ctx.Err() == nil && !errors.As(err, &cerr), err
	}
	defer resp.Body.Close()
	switch {
	case resp.StatusCode == 429 || resp.StatusCode >= 502 && resp.StatusCode <= 504:
		return nil, [2]string{resp.Header.Get("Retry-After"), resp.Header.Get("Date")}, true, fmt.Errorf("status %d", resp.StatusCode)
	case resp.StatusCode != 200:
		return nil, [2]string{}, false, fmt.Errorf("status %d", resp.StatusCode)
	}
	b, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, [2]string{}, ctx.Err() == nil, err
	}
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		return nil, [2]string{}, false, err
	}
	return m, [2]string{}, false, nil
}

func GetUserProfile(baseURL, userID string) (map[string]any, error) {
	return GetUserProfileContext(context.Background(), baseURL, userID)
}

func GetUserProfileContext(parent context.Context, baseURL, userID string) (map[string]any, error) {
	ctx, cancel := context.WithTimeout(parent, 10*time.Second)
	defer cancel()
	dl, _ := ctx.Deadline()
	url := strings.TrimRight(baseURL, "/") + "/v1/users/" + userID
	delay := 200 * time.Millisecond
	for attempt := 0; attempt < 4; attempt++ {
		m, ra, retryable, err := once(ctx, url)
		if err == nil {
			return m, nil
		}
		if !retryable || attempt == 3 {
			return nil, err
		}
		wait, fromServer := retryAfter(ra[0], ra[1])
		if !fromServer {
			wait = time.Duration(float64(delay) * (0.5 + 0.5*rand.Float64()))
		}
		if time.Now().Add(wait).After(dl) {
			return nil, fmt.Errorf("no time left for the next attempt: %w", err)
		}
		select {
		case <-time.After(wait):
		case <-ctx.Done():
			return nil, ctx.Err()
		}
		delay = min(2*delay, 2*time.Second)
	}
	return nil, errors.New("retries exhausted")
}
