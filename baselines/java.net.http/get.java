// Baseline: java.net.http.HttpClient, all defaults (GET).
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;

public class UserProfileClient {
    @SuppressWarnings("unchecked")
    public static Map<String, Object> getUserProfile(String baseUrl, String userId) throws Exception {
        HttpResponse<String> r = HttpClient.newHttpClient().send(HttpRequest.newBuilder(URI.create(baseUrl + "/v1/users/" + userId)).build(), HttpResponse.BodyHandlers.ofString());
        if (r.statusCode() >= 400) throw new RuntimeException("HTTP " + r.statusCode());
        return new ObjectMapper().readValue(r.body(), Map.class);
    }
}
