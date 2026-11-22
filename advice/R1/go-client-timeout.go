// Advice check (D52): http.Client.Timeout covers the body.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

var client = &http.Client{Timeout: 10 * time.Second}

func GetUserProfile(baseURL, userID string) (map[string]any, error) {
	resp, err := client.Get(strings.TrimRight(baseURL, "/") + "/v1/users/" + userID)
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
