// Baseline: go-retryablehttp, all defaults (POST on a reused keep-alive connection, S8 variant, D42).
package main

import (
	"encoding/json"
	"fmt"
	"io"

	"github.com/hashicorp/go-retryablehttp"
)

var client = retryablehttp.NewClient() // shared client (pooled transport), created once

func SendSms(baseURL, to, body string) (string, error) {
	if g, err := client.Get(baseURL + "/v1/messages"); err == nil { // warm the pool; 405 ignored
		io.Copy(io.Discard, g.Body) // drain + close so the connection returns idle
		g.Body.Close()
	}
	b, _ := json.Marshal(map[string]string{"to": to, "body": body})
	resp, err := client.Post(baseURL+"/v1/messages", "application/json", b)
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
