// Advice check (D52): OkHttp callTimeout bounds the whole call and cancels it.
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.Map;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

public class UserProfileClient {
    static final OkHttpClient CLIENT = new OkHttpClient.Builder()
            .connectTimeout(Duration.ofSeconds(2)).readTimeout(Duration.ofSeconds(5)).callTimeout(Duration.ofSeconds(10)).build();

    public static class ProfileException extends Exception {
        public ProfileException(String m, Throwable c) { super(m, c); }
    }

    public static Map<String, Object> getUserProfile(String baseUrl, String userId) throws ProfileException {
        Request req = new Request.Builder().url(baseUrl.replaceAll("/$", "") + "/v1/users/" + userId).build();
        try (Response r = CLIENT.newCall(req).execute()) {
            String body = r.body().string();
            if (r.code() != 200) throw new ProfileException("status " + r.code(), null);
            return new ObjectMapper().readValue(body, new TypeReference<Map<String, Object>>() {});
        } catch (ProfileException e) {
            throw e;
        } catch (Exception e) {
            throw new ProfileException(e.toString(), e);
        }
    }
}
