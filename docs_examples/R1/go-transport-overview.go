// Documentation example (net/http package overview): tr := &http.Transport{MaxIdleConns: 10, IdleConnTimeout:
// 30 * time.Second, DisableCompression: true}; client := &http.Client{Transport: tr}; placed in the minimal R1 function.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

var tr = &http.Transport{
	MaxIdleConns:       10,
	IdleConnTimeout:    30 * time.Second,
	DisableCompression: true,
}
var client = &http.Client{Transport: tr}

func GetUserProfile(baseURL, userID string) (map[string]any, error) {
	resp, err := client.Get(strings.TrimRight(baseURL, "/") + "/v1/users/" + userID)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("status %d", resp.StatusCode)
	}
	var m map[string]any
	return m, json.Unmarshal(b, &m)
}
