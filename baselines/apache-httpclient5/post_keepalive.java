// Baseline: Apache HttpClient 5 (classic API), all defaults (POST on a reused keep-alive connection, S8 variant, D42).
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.apache.hc.client5.http.classic.methods.HttpGet;
import org.apache.hc.client5.http.classic.methods.HttpPost;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.core5.http.ContentType;
import org.apache.hc.core5.http.io.entity.EntityUtils;
import org.apache.hc.core5.http.io.entity.StringEntity;

public class SmsClient {
    private static final CloseableHttpClient CLIENT = HttpClients.createDefault(); // shared client (connection pool), created once

    public static String sendSms(String baseUrl, String to, String body) throws Exception {
        // warm the pool; 405 ignored, entity consumed so the connection returns idle
        CLIENT.execute(new HttpGet(baseUrl + "/v1/messages"), r -> { EntityUtils.consume(r.getEntity()); return null; });
        HttpPost post = new HttpPost(baseUrl + "/v1/messages");
        post.setEntity(new StringEntity(new ObjectMapper().writeValueAsString(Map.of("to", to, "body", body)), ContentType.APPLICATION_JSON));
        String res = CLIENT.execute(post, r -> {
            if (r.getCode() >= 400) throw new RuntimeException("HTTP " + r.getCode());
            return EntityUtils.toString(r.getEntity());
        });
        return (String) new ObjectMapper().readValue(res, Map.class).get("id");
    }
}
