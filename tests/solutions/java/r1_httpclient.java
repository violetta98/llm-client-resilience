// Harness test solution (NOT a reference): java.net.http.HttpClient with defaults.
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;

public class UserProfileClient {
    private static final HttpClient CLIENT = HttpClient.newHttpClient();
    private static final ObjectMapper MAPPER = new ObjectMapper();

    @SuppressWarnings("unchecked")
    public static Map<String, Object> getUserProfile(String baseUrl, String userId) throws Exception {
        HttpRequest req = HttpRequest.newBuilder(URI.create(baseUrl + "/v1/users/" + userId)).GET().build();
        HttpResponse<String> resp = CLIENT.send(req, HttpResponse.BodyHandlers.ofString());
        if (resp.statusCode() != 200) throw new RuntimeException("HTTP " + resp.statusCode());
        return MAPPER.readValue(resp.body(), Map.class);
    }
}
