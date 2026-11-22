// Baseline: Apache HttpClient 5 (classic API), all defaults (POST).
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.apache.hc.client5.http.classic.methods.HttpPost;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.core5.http.ContentType;
import org.apache.hc.core5.http.io.entity.EntityUtils;
import org.apache.hc.core5.http.io.entity.StringEntity;

public class SmsClient {
    public static String sendSms(String baseUrl, String to, String body) throws Exception {
        HttpPost post = new HttpPost(baseUrl + "/v1/messages");
        post.setEntity(new StringEntity(new ObjectMapper().writeValueAsString(Map.of("to", to, "body", body)), ContentType.APPLICATION_JSON));
        try (CloseableHttpClient client = HttpClients.createDefault()) {
            String res = client.execute(post, r -> {
                if (r.getCode() >= 400) throw new RuntimeException("HTTP " + r.getCode());
                return EntityUtils.toString(r.getEntity());
            });
            return (String) new ObjectMapper().readValue(res, Map.class).get("id");
        }
    }
}
