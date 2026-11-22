// Baseline: java.net.http.HttpClient, all defaults (POST on a reused keep-alive connection, S8 variant, D42).
// Default version is HTTP_2; the mock offers only http/1.1 via ALPN, so the client pools HTTP/1.1 connections.
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;

public class SmsClient {
    private static final HttpClient CLIENT = HttpClient.newHttpClient(); // shared client (connection pool), created once

    public static String sendSms(String baseUrl, String to, String body) throws Exception {
        // warm the pool; 405 ignored, body read fully so the connection returns idle
        CLIENT.send(HttpRequest.newBuilder(URI.create(baseUrl + "/v1/messages")).GET().build(), HttpResponse.BodyHandlers.discarding());
        String json = new ObjectMapper().writeValueAsString(Map.of("to", to, "body", body));
        HttpResponse<String> r = CLIENT.send(HttpRequest.newBuilder(URI.create(baseUrl + "/v1/messages"))
            .header("Content-Type", "application/json").POST(HttpRequest.BodyPublishers.ofString(json)).build(), HttpResponse.BodyHandlers.ofString());
        if (r.statusCode() >= 400) throw new RuntimeException("HTTP " + r.statusCode());
        return (String) new ObjectMapper().readValue(r.body(), Map.class).get("id");
    }
}
