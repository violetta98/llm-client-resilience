// Baseline: net/http, all defaults (POST on a reused keep-alive connection, S8 variant, D42).
// http.Get/http.Post use the package-level http.DefaultClient (DefaultTransport
// keeps idle keep-alive connections), which is net/http's shared-client idiom.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

func SendSms(baseURL, to, body string) (string, error) {
	if g, err := http.Get(baseURL + "/v1/messages"); err == nil { // warm the pool; 405 ignored
		io.Copy(io.Discard, g.Body) // drain + close so the connection returns idle
		g.Body.Close()
	}
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
