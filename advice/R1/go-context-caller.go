// Advice check (D56): as go-context-deadline, but GetUserProfileContext takes the caller's context and adds at most
// 10 s, so the call also ends when the caller gives up; GetUserProfile is the task's signature.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

func GetUserProfile(baseURL, userID string) (map[string]any, error) {
	return GetUserProfileContext(context.Background(), baseURL, userID)
}

func GetUserProfileContext(parent context.Context, baseURL, userID string) (map[string]any, error) {
	ctx, cancel := context.WithTimeout(parent, 10*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, strings.TrimRight(baseURL, "/")+"/v1/users/"+userID, nil)
	if err != nil {
		return nil, err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("status %d", resp.StatusCode)
	}
	var m map[string]any
	return m, json.Unmarshal(b, &m)
}
