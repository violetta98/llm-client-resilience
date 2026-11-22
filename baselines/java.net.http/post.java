// Baseline: java.net.http.HttpClient, all defaults (POST).
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;

public class SmsClient {
    public static String sendSms(String baseUrl, String to, String body) throws Exception {
        String json = new ObjectMapper().writeValueAsString(Map.of("to", to, "body", body));
        HttpResponse<String> r = HttpClient.newHttpClient().send(HttpRequest.newBuilder(URI.create(baseUrl + "/v1/messages"))
            .header("Content-Type", "application/json").POST(HttpRequest.BodyPublishers.ofString(json)).build(), HttpResponse.BodyHandlers.ofString());
        if (r.statusCode() >= 400) throw new RuntimeException("HTTP " + r.statusCode());
        return (String) new ObjectMapper().readValue(r.body(), Map.class).get("id");
    }
}
