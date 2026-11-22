// Baseline: resty v2, all defaults (POST on a reused keep-alive connection, S8 variant, D42).
package main

import (
	"fmt"

	"github.com/go-resty/resty/v2"
)

var client = resty.New() // shared client (pooled transport), created once

func SendSms(baseURL, to, body string) (string, error) {
	client.R().Get(baseURL + "/v1/messages") // warm the pool; 405 ignored, resty reads the body fully
	var out struct{ ID string `json:"id"` }
	resp, err := client.R().SetBody(map[string]string{"to": to, "body": body}).SetResult(&out).Post(baseURL + "/v1/messages")
	if err != nil {
		return "", err
	}
	if resp.IsError() {
		return "", fmt.Errorf("HTTP %d", resp.StatusCode())
	}
	return out.ID, nil
}
