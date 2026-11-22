// Advice check (D52): go-retryablehttp with RetryMax = 0 for a non-idempotent POST without a key.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"strings"

	retryablehttp "github.com/hashicorp/go-retryablehttp"
)

func SendSms(baseURL, to, body string) (string, error) {
	c := retryablehttp.NewClient()
	c.Logger = nil
	c.RetryMax = 0
	payload, _ := json.Marshal(map[string]string{"to": to, "body": body})
	req, err := retryablehttp.NewRequest("POST", strings.TrimRight(baseURL, "/")+"/v1/messages", bytes.NewReader(payload))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != 202 {
		return "", fmt.Errorf("status %d", resp.StatusCode)
	}
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		return "", err
	}
	id, _ := m["id"].(string)
	return id, nil
}
