// Harness test solution (NOT a reference): net/http with defaults.
package solution

import (
	"encoding/json"
	"fmt"
	"net/http"
)

func GetUserProfile(baseURL, userID string) (map[string]any, error) {
	resp, err := http.Get(baseURL + "/v1/users/" + userID)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("status %d", resp.StatusCode)
	}
	var out map[string]any
	return out, json.NewDecoder(resp.Body).Decode(&out)
}

func main() { fmt.Println(GetUserProfile("x", "y")) }
