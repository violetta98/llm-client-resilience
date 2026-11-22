// Baseline: net/http, all defaults (POST).
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
)

func SendSms(baseURL, to, body string) (string, error) {
	b, _ := json.Marshal(map[string]string{"to": to, "body": body})
	resp, err := http.Post(baseURL+"/v1/messages", "application/json", bytes.NewReader(b))
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
