// Baseline: go-retryablehttp, all defaults (GET; package-level default client).
package main

import (
	"encoding/json"
	"fmt"

	"github.com/hashicorp/go-retryablehttp"
)

func GetUserProfile(baseURL, userID string) (map[string]any, error) {
	resp, err := retryablehttp.Get(baseURL + "/v1/users/" + userID)
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
