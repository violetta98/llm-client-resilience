// Baseline: net/http, all defaults (GET).
package main

import (
	"encoding/json"
	"fmt"
	"net/http"
)

func GetUserProfile(baseURL, userID string) (map[string]any, error) {
	resp, err := http.Get(baseURL + "/v1/users/" + userID)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	var out map[string]any
	return out, json.NewDecoder(resp.Body).Decode(&out)
}
