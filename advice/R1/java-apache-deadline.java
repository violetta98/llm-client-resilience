// Advice check (D56): Apache HttpClient 5 classic with automatic retries disabled, so that nothing inside execute()
// waits out a Retry-After; a scheduled task cancels the request at the deadline, and cancelled timer tasks are removed
// from the queue at once (setRemoveOnCancelPolicy).
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import org.apache.hc.client5.http.classic.methods.HttpGet;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.core5.http.io.entity.EntityUtils;
import org.apache.hc.core5.util.Timeout;

public class UserProfileClient {
    static final CloseableHttpClient CLIENT = HttpClients.custom().disableAutomaticRetries()
            .setDefaultRequestConfig(RequestConfig.custom()
                    .setConnectTimeout(Timeout.ofSeconds(2)).setResponseTimeout(Timeout.ofSeconds(5)).build()).build();
    static final ScheduledThreadPoolExecutor TIMER = new ScheduledThreadPoolExecutor(1, r -> {
        Thread t = new Thread(r); t.setDaemon(true); return t; });
    static { TIMER.setRemoveOnCancelPolicy(true); }

    public static class ProfileException extends Exception {
        public ProfileException(String m, Throwable c) { super(m, c); }
    }

    public static Map<String, Object> getUserProfile(String baseUrl, String userId) throws ProfileException {
        HttpGet get = new HttpGet(baseUrl.replaceAll("/$", "") + "/v1/users/" + userId);
        ScheduledFuture<?> cancel = TIMER.schedule(() -> { get.cancel(); }, 10, TimeUnit.SECONDS);
        try {
            return CLIENT.execute(get, r -> {
                String body = EntityUtils.toString(r.getEntity());
                if (r.getCode() != 200) throw new java.io.IOException("status " + r.getCode());
                return new ObjectMapper().readValue(body, new TypeReference<Map<String, Object>>() {});
            });
        } catch (Exception e) {
            throw new ProfileException(e.toString(), e);
        } finally {
            cancel.cancel(false);
        }
    }
}
