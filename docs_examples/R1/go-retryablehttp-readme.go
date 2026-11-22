// Documentation example (go-retryablehttp README): retryClient := retryablehttp.NewClient(); retryClient.RetryMax = 10;
// standardClient := retryClient.StandardClient(); placed in the minimal R1 function of the D61 check.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"strings"

	"github.com/hashicorp/go-retryablehttp"
)

var retryClient = func() *retryablehttp.Client {
	c := retryablehttp.NewClient()
	c.RetryMax = 10
	return c
}()
var standardClient = retryClient.StandardClient() // *http.Client

func GetUserProfile(baseURL, userID string) (map[string]any, error) {
	resp, err := standardClient.Get(strings.TrimRight(baseURL, "/") + "/v1/users/" + userID)
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
