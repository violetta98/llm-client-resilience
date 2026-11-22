// Documentation example (Apache HttpClient 5 example ClientConfiguration.java): ConnectionConfig with
// setConnectTimeout(Timeout.ofSeconds(30)) and setSocketTimeout(Timeout.ofSeconds(30)) on a pooling connection
// manager; placed in the minimal R1 function of the D61 check.
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.apache.hc.client5.http.classic.methods.HttpGet;
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.core5.http.io.entity.EntityUtils;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;

public class UserProfileClient {
    static final CloseableHttpClient CLIENT;
    static {
        PoolingHttpClientConnectionManager connManager = new PoolingHttpClientConnectionManager();
        connManager.setDefaultConnectionConfig(ConnectionConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(30))
                .setSocketTimeout(Timeout.ofSeconds(30))
                .setValidateAfterInactivity(TimeValue.ofSeconds(10))
                .setTimeToLive(TimeValue.ofHours(1))
                .build());
        CLIENT = HttpClients.custom().setConnectionManager(connManager).build();
    }

    public static class ProfileException extends Exception {
        public ProfileException(String m, Throwable c) { super(m, c); }
    }

    public static Map<String, Object> getUserProfile(String baseUrl, String userId) throws ProfileException {
        HttpGet get = new HttpGet(baseUrl.replaceAll("/$", "") + "/v1/users/" + userId);
        try {
            return CLIENT.execute(get, r -> {
                String body = EntityUtils.toString(r.getEntity());
                if (r.getCode() != 200) throw new java.io.IOException("status " + r.getCode());
                return new ObjectMapper().readValue(body, new TypeReference<Map<String, Object>>() {});
            });
        } catch (Exception e) {
            throw new ProfileException(e.toString(), e);
        }
    }
}
