// Anti-pattern check (D52): Apache HttpClient 5 with its default retry strategy sends the SMS POST.
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.apache.hc.client5.http.classic.methods.HttpPost;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.core5.http.ContentType;
import org.apache.hc.core5.http.io.entity.EntityUtils;
import org.apache.hc.core5.http.io.entity.StringEntity;

public class SmsClient {
    static final CloseableHttpClient CLIENT = HttpClients.custom().build();

    public static class SmsException extends Exception {
        public SmsException(String m, Throwable c) { super(m, c); }
    }

    public static String sendSms(String baseUrl, String to, String body) throws SmsException {
        HttpPost post = new HttpPost(baseUrl.replaceAll("/$", "") + "/v1/messages");
        try {
            post.setEntity(new StringEntity(new ObjectMapper().writeValueAsString(Map.of("to", to, "body", body)), ContentType.APPLICATION_JSON));
            return CLIENT.execute(post, r -> {
                String s = EntityUtils.toString(r.getEntity());
                if (r.getCode() != 202) throw new java.io.IOException("status " + r.getCode());
                Map<String, Object> m = new ObjectMapper().readValue(s, new TypeReference<Map<String, Object>>() {});
                return String.valueOf(m.get("id"));
            });
        } catch (Exception e) {
            throw new SmsException(e.toString(), e);
        }
    }
}
