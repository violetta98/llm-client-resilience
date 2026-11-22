// Advice check (D54): retries with backoff and jitter under one context deadline for the whole call, body included.
package main

import (
	"context"
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

func GetUserProfile(baseURL, userID string) (map[string]any, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	url := strings.TrimRight(baseURL, "/") + "/v1/users/" + userID
	delay := 200 * time.Millisecond
	for attempt := 0; attempt < 4; attempt++ {
		wait := time.Duration(float64(delay) * (0.5 + 0.5*rand.Float64()))
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if err != nil {
			return nil, err
		}
		resp, err := http.DefaultClient.Do(req)
		if err == nil {
			b, rerr := io.ReadAll(resp.Body)
			resp.Body.Close()
			switch {
			case rerr != nil:
				return nil, rerr
			case resp.StatusCode == 200:
				var m map[string]any
				return m, json.Unmarshal(b, &m)
			case resp.StatusCode == 429 || resp.StatusCode >= 502 && resp.StatusCode <= 504:
				if s, e := strconv.Atoi(resp.Header.Get("Retry-After")); e == nil {
					wait = time.Duration(s) * time.Second
				}
			default:
				return nil, fmt.Errorf("status %d", resp.StatusCode)
			}
		} else if ctx.Err() != nil {
			return nil, err
		}
		if dl, _ := ctx.Deadline(); attempt == 3 || time.Now().Add(wait).After(dl) {
			return nil, errors.New("retries exhausted")
		}
		select {
		case <-time.After(wait):
		case <-ctx.Done():
			return nil, ctx.Err()
		}
		if delay *= 2; delay > 2*time.Second {
			delay = 2 * time.Second
		}
	}
	return nil, errors.New("retries exhausted")
}
