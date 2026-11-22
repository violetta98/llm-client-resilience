// Baseline: resty v2, all defaults (GET).
package main

import (
	"fmt"

	"github.com/go-resty/resty/v2"
)

func GetUserProfile(baseURL, userID string) (map[string]any, error) {
	var out map[string]any
	resp, err := resty.New().R().SetResult(&out).Get(baseURL + "/v1/users/" + userID)
	if err != nil {
		return nil, err
	}
	if resp.IsError() {
		return nil, fmt.Errorf("HTTP %d", resp.StatusCode())
	}
	return out, nil
}
