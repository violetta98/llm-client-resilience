// Advice check (D56, revised D57): a payment POST retried under one context deadline with an Idempotency-Key that
// identifies one payment intent: the caller passes it (and stores it with the intent), or it is derived from the whole
// request (order, amount, currency), so a corrected payment gets a new key. The body is identical in every attempt, so
// a 422 is not retried; a 409 (first request still in progress) is retried later. CreatePaymentContext takes the
// caller's context and key and adds at most 10 s; CreatePayment is the task's signature. At most four attempts, each with min(own timeout, time left); 429/502-504 and transport errors are
// retried with backoff and jitter; Retry-After in both forms, a date measured from the server's Date header; a
// Retry-After that does not fit the time left fails at once; TLS certificate errors are not retried.
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/tls"
	"encoding/hex"
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
		now := time.Now()
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

func once(ctx context.Context, url string, body []byte, key string) (map[string]any, [2]string, bool, error) {
	dl, _ := ctx.Deadline()
	budget := time.Until(dl)
	if budget <= 0 {
		return nil, [2]string{}, false, context.DeadlineExceeded
	}
	actx, cancel := context.WithTimeout(ctx, min(perAttempt, budget))
	defer cancel()
	req, err := http.NewRequestWithContext(actx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, [2]string{}, false, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Idempotency-Key", key)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		var cerr *tls.CertificateVerificationError
		return nil, [2]string{}, ctx.Err() == nil && !errors.As(err, &cerr), err
	}
	defer resp.Body.Close()
	switch {
	case resp.StatusCode == 409 || resp.StatusCode == 429 || resp.StatusCode >= 502 && resp.StatusCode <= 504:
		return nil, [2]string{resp.Header.Get("Retry-After"), resp.Header.Get("Date")}, true, fmt.Errorf("status %d", resp.StatusCode)
	case resp.StatusCode == 422:
		return nil, [2]string{}, false, errors.New("Idempotency-Key reused with a different body")
	case resp.StatusCode != 200 && resp.StatusCode != 201:
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

func CreatePayment(baseURL, orderID, amount, currency string) (map[string]any, error) {
	return CreatePaymentContext(context.Background(), baseURL, orderID, amount, currency, "")
}

func CreatePaymentContext(parent context.Context, baseURL, orderID, amount, currency, key string) (map[string]any, error) {
	ctx, cancel := context.WithTimeout(parent, 10*time.Second)
	defer cancel()
	dl, _ := ctx.Deadline()
	url := strings.TrimRight(baseURL, "/") + "/v1/payments"
	body, _ := json.Marshal(map[string]string{"order_id": orderID, "amount": amount, "currency": currency})
	if key == "" {
		sum := sha256.Sum256(body)
		key = "payment-" + hex.EncodeToString(sum[:16])
	}
	delay := 200 * time.Millisecond
	for attempt := 0; attempt < 4; attempt++ {
		m, ra, retryable, err := once(ctx, url, body, key)
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
