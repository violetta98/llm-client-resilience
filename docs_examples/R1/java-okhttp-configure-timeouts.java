// Documentation example (OkHttp recipe ConfigureTimeouts.java): connectTimeout 5 s, writeTimeout 5 s, readTimeout 5 s,
// callTimeout 10 s, placed in the minimal R1 function of the D61 check.
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

public class UserProfileClient {
    static final OkHttpClient client = new OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .writeTimeout(5, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .callTimeout(10, TimeUnit.SECONDS)
        .build();

    public static class ProfileException extends Exception {
        public ProfileException(String m, Throwable c) { super(m, c); }
    }

    public static Map<String, Object> getUserProfile(String baseUrl, String userId) throws ProfileException {
        Request request = new Request.Builder().url(baseUrl.replaceAll("/$", "") + "/v1/users/" + userId).build();
        try (Response response = client.newCall(request).execute()) {
            String body = response.body().string();
            if (response.code() != 200) throw new ProfileException("status " + response.code(), null);
            return new ObjectMapper().readValue(body, new TypeReference<Map<String, Object>>() {});
        } catch (ProfileException e) {
            throw e;
        } catch (Exception e) {
            throw new ProfileException(e.toString(), e);
        }
    }
}
