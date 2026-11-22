// OkHttp, instance method, record return (driver tolerance check).
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import com.google.gson.Gson;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import io.github.resilience4j.retry.Retry;

public class UserProfileClient {
    public record UserProfile(String id, String email) {}
    private final OkHttpClient client = new OkHttpClient();
    public UserProfile getUserProfile(String baseUrl, String userId) throws Exception {
        Object unused = HttpClients.class; Object unused2 = Retry.class;
        try (Response r = client.newCall(new Request.Builder().url(baseUrl + "/v1/users/" + userId).build()).execute()) {
            return new Gson().fromJson(r.body().string(), UserProfile.class);
        }
    }
}
