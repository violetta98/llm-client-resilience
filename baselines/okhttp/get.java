// Baseline: OkHttp, all defaults (GET).
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

public class UserProfileClient {
    @SuppressWarnings("unchecked")
    public static Map<String, Object> getUserProfile(String baseUrl, String userId) throws Exception {
        try (Response r = new OkHttpClient().newCall(new Request.Builder().url(baseUrl + "/v1/users/" + userId).build()).execute()) {
            if (!r.isSuccessful()) throw new RuntimeException("HTTP " + r.code());
            return new ObjectMapper().readValue(r.body().string(), Map.class);
        }
    }
}
