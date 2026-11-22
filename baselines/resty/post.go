// Baseline: resty v2, all defaults (POST).
package main

import (
	"fmt"

	"github.com/go-resty/resty/v2"
)

func SendSms(baseURL, to, body string) (string, error) {
	var out struct{ ID string `json:"id"` }
	resp, err := resty.New().R().SetBody(map[string]string{"to": to, "body": body}).SetResult(&out).Post(baseURL + "/v1/messages")
	if err != nil {
		return "", err
	}
	if resp.IsError() {
		return "", fmt.Errorf("HTTP %d", resp.StatusCode())
	}
	return out.ID, nil
}
