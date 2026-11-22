// Baseline: Apache HttpClient 5 (classic API), all defaults (GET).
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.apache.hc.client5.http.classic.methods.HttpGet;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.core5.http.io.entity.EntityUtils;

public class UserProfileClient {
    @SuppressWarnings("unchecked")
    public static Map<String, Object> getUserProfile(String baseUrl, String userId) throws Exception {
        try (CloseableHttpClient client = HttpClients.createDefault()) {
            String body = client.execute(new HttpGet(baseUrl + "/v1/users/" + userId), r -> {
                if (r.getCode() >= 400) throw new RuntimeException("HTTP " + r.getCode());
                return EntityUtils.toString(r.getEntity());
            });
            return new ObjectMapper().readValue(body, Map.class);
        }
    }
}
