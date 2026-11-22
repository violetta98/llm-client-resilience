// Baseline: go-retryablehttp, all defaults (POST).
package main

import (
	"encoding/json"
	"fmt"

	"github.com/hashicorp/go-retryablehttp"
)

func SendSms(baseURL, to, body string) (string, error) {
	b, _ := json.Marshal(map[string]string{"to": to, "body": body})
	resp, err := retryablehttp.Post(baseURL+"/v1/messages", "application/json", b)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return "", fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	var out struct{ ID string `json:"id"` }
	return out.ID, json.NewDecoder(resp.Body).Decode(&out)
}
