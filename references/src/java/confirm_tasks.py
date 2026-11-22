# Task bodies of the Java references for the CONFIRMATORY tasks R6, W5, B5, H4
# (tasks/CONFIRM_TASKS.md). Loaded by references/build_confirm.py into the namespace of
# tasks.py (exc(), IMPORTS, assemble() come from there); same prelude and budgets.

BODIES["R6"] = exc("Stock") + '''
    public static Map<String, Object> getStockLevels(String baseUrl, String productId) throws StockException {
        try {
            Resp r = get(deadlineIn(9500), baseUrl + "/v1/products/" + enc(productId) + "/stock", Map.of());
            if (r.status() != 200) throw new StockException("HTTP " + r.status());
            return r.map();
        } catch (GiveUp | IOException | InterruptedException e) {
            throw new StockException(String.valueOf(e), e);
        }
    }
'''

BODIES["W5"] = exc("Ticket") + '''
    public static Map<String, Object> createTicket(String baseUrl, String customerId, String subject, String message) throws TicketException {
        String key = UUID.randomUUID().toString(); // one key per ticket: every retry reuses it
        try {
            String body = JSON.writeValueAsString(Map.of("customer_id", customerId, "subject", subject, "message", message));
            Resp r = call(deadlineIn(9500), true, a -> HttpRequest.newBuilder(URI.create(baseUrl + "/v1/tickets"))
                    .header("Content-Type", "application/json")
                    .header("Idempotency-Key", MUTANT.equals("UNSAFE_POST_RETRY") ? UUID.randomUUID().toString() : key)
                    .POST(HttpRequest.BodyPublishers.ofString(body)),
                HttpResponse.BodyHandlers.ofByteArray());
            if (r.status() != 201) throw new TicketException("HTTP " + r.status() + ": " + r.text());
            return r.map();
        } catch (GiveUp | IOException | InterruptedException e) {
            throw new TicketException(String.valueOf(e), e);
        }
    }
'''

BODIES["B5"] = exc("ShipmentUpdates") + '''
    @SuppressWarnings("unchecked")
    public static List<Map<String, Object>> fetchShipmentUpdates(String baseUrl, String carrierId, String since) throws ShipmentUpdatesException {
        try {
            Resp r = get(deadlineIn(28000), baseUrl + "/v1/carriers/" + enc(carrierId) + "/shipment-updates?since=" + enc(since), Map.of());
            if (r.status() != 200) throw new ShipmentUpdatesException("HTTP " + r.status());
            return (List<Map<String, Object>>) r.map().get("updates");
        } catch (GiveUp | IOException | InterruptedException e) {
            throw new ShipmentUpdatesException(String.valueOf(e), e);
        }
    }
'''

BODIES["H4"] = '''
    static Map<String, Object> defaultPreferences() {
        Map<String, Object> d = new java.util.LinkedHashMap<>();
        d.put("email", true);
        d.put("sms", false);
        d.put("push", false);
        return d;
    }

    /** Returns the documented default on any failure. */
    public static Map<String, Object> getNotificationPreferences(String preferencesUrl, String userId) {
        try {
            Resp r = get(deadlineIn(1800), preferencesUrl + "/v1/users/" + enc(userId) + "/notification-preferences", Map.of());
            if (r.status() != 200) return defaultPreferences();
            Map<String, Object> p = r.map();
            Map<String, Object> out = new java.util.LinkedHashMap<>();
            for (String k : List.of("email", "sms", "push")) {
                if (!(p.get(k) instanceof Boolean b)) return defaultPreferences();
                out.put(k, b);
            }
            return out;
        } catch (Exception e) {
            return defaultPreferences();
        }
    }
'''
