# Task bodies of the Go references for the PILOT tasks P1-P3 (outside the
# benchmark). Loaded by references/build.py --pilot into the namespace of tasks.py.

IMPORTS["P1"] = ["net/url"]
BODIES["P1"] = '''
func GetExchangeRate(baseURL, baseCurrency, quoteCurrency string) (map[string]any, error) {
	u := baseURL + "/v1/rates/" + url.PathEscape(baseCurrency) + "/" + url.PathEscape(quoteCurrency)
	r, err := refCall(refDeadline(9500*time.Millisecond), refReq{Method: "GET", URL: u, Idempotent: true})
	if err != nil {
		return nil, fmt.Errorf("rate: %w", err)
	}
	if r.Status != 200 {
		return nil, fmt.Errorf("rate: HTTP %d", r.Status)
	}
	var out map[string]any
	return out, r.JSON(&out)
}
'''

IMPORTS["P2"] = ["net/url"]
BODIES["P2"] = '''
// AddTicketComment: no idempotency support, so the POST is retried only when
// it certainly was not processed (dial failure, 429, 503).
func AddTicketComment(baseURL, ticketID, text string) (string, error) {
	b, _ := json.Marshal(map[string]string{"text": text})
	hdr := func(int) http.Header { return http.Header{"Content-Type": {"application/json"}} }
	u := baseURL + "/v1/tickets/" + url.PathEscape(ticketID) + "/comments"
	r, err := refCall(refDeadline(9500*time.Millisecond), refReq{Method: "POST", URL: u, Body: b, Header: hdr, Idempotent: false})
	if err != nil {
		return "", fmt.Errorf("comment: %w", err)
	}
	if r.Status != 201 {
		return "", fmt.Errorf("comment: HTTP %d", r.Status)
	}
	var out struct {
		ID string `json:"id"`
	}
	return out.ID, r.JSON(&out)
}
'''

IMPORTS["P3"] = ["net/url"]
BODIES["P3"] = '''
// EstimateDeliveryDays returns 5 (the documented default) on any failure.
func EstimateDeliveryDays(shippingURL, postalCode string) int {
	u := shippingURL + "/v1/estimates?" + url.Values{"postal_code": {postalCode}}.Encode()
	r, err := refCall(refDeadline(1800*time.Millisecond), refReq{Method: "GET", URL: u, Idempotent: true})
	if err != nil || r.Status != 200 {
		return 5
	}
	var e struct {
		Days *int `json:"days"`
	}
	if r.JSON(&e) != nil || e.Days == nil {
		return 5
	}
	return *e.Days
}
'''
