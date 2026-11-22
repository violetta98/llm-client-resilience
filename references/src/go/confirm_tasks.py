# Task bodies of the Go references for the CONFIRMATORY tasks R6, W5, B5, H4
# (tasks/CONFIRM_TASKS.md). Loaded by references/build_confirm.py into the namespace of
# tasks.py; same prelude and budgets as the benchmark references.

IMPORTS["R6"] = ["net/url"]
BODIES["R6"] = '''
func GetStockLevels(baseURL, productID string) (map[string]any, error) {
	r, err := refCall(refDeadline(9500*time.Millisecond), refReq{Method: "GET", URL: baseURL + "/v1/products/" + url.PathEscape(productID) + "/stock", Idempotent: true})
	if err != nil {
		return nil, fmt.Errorf("stock: %w", err)
	}
	if r.Status != 200 {
		return nil, fmt.Errorf("stock: HTTP %d", r.Status)
	}
	var out map[string]any
	return out, r.JSON(&out)
}
'''

IMPORTS["W5"] = ['crand "crypto/rand"', "encoding/hex"]
BODIES["W5"] = '''
func refNewKey() string {
	b := make([]byte, 16)
	crand.Read(b)
	return hex.EncodeToString(b)
}

func CreateTicket(baseURL, customerID, subject, message string) (map[string]any, error) {
	key := refNewKey() // one key per ticket: every retry reuses it
	body, _ := json.Marshal(map[string]string{"customer_id": customerID, "subject": subject, "message": message})
	hdr := func(int) http.Header {
		k := key
		if refMutant == "UNSAFE_POST_RETRY" {
			k = refNewKey()
		}
		return http.Header{"Content-Type": {"application/json"}, "Idempotency-Key": {k}}
	}
	r, err := refCall(refDeadline(9500*time.Millisecond), refReq{Method: "POST", URL: baseURL + "/v1/tickets", Body: body, Header: hdr, Idempotent: true})
	if err != nil {
		return nil, fmt.Errorf("ticket: %w", err)
	}
	if r.Status != 201 {
		return nil, fmt.Errorf("ticket: HTTP %d: %s", r.Status, r.Body)
	}
	var out map[string]any
	return out, r.JSON(&out)
}
'''

IMPORTS["B5"] = ["net/url"]
BODIES["B5"] = '''
func FetchShipmentUpdates(baseURL, carrierID, since string) ([]map[string]any, error) {
	u := baseURL + "/v1/carriers/" + url.PathEscape(carrierID) + "/shipment-updates?" + url.Values{"since": {since}}.Encode()
	r, err := refCall(refDeadline(28*time.Second), refReq{Method: "GET", URL: u, Idempotent: true})
	if err != nil {
		return nil, fmt.Errorf("shipment updates: %w", err)
	}
	if r.Status != 200 {
		return nil, fmt.Errorf("shipment updates: HTTP %d", r.Status)
	}
	var out struct {
		Updates []map[string]any `json:"updates"`
	}
	if err := r.JSON(&out); err != nil {
		return nil, err
	}
	if out.Updates == nil {
		out.Updates = []map[string]any{}
	}
	return out.Updates, nil
}
'''

IMPORTS["H4"] = ["net/url"]
BODIES["H4"] = '''
func refDefaultPreferences() map[string]any {
	return map[string]any{"email": true, "sms": false, "push": false}
}

// GetNotificationPreferences returns the documented default on any failure.
func GetNotificationPreferences(preferencesURL, userID string) map[string]any {
	u := preferencesURL + "/v1/users/" + url.PathEscape(userID) + "/notification-preferences"
	r, err := refCall(refDeadline(1800*time.Millisecond), refReq{Method: "GET", URL: u, Idempotent: true})
	if err != nil || r.Status != 200 {
		return refDefaultPreferences()
	}
	var p struct {
		Email *bool `json:"email"`
		SMS   *bool `json:"sms"`
		Push  *bool `json:"push"`
	}
	if r.JSON(&p) != nil || p.Email == nil || p.SMS == nil || p.Push == nil {
		return refDefaultPreferences()
	}
	return map[string]any{"email": *p.Email, "sms": *p.SMS, "push": *p.Push}
}
'''
