// Baseline: OkHttp, all defaults (POST).
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

public class SmsClient {
    public static String sendSms(String baseUrl, String to, String body) throws Exception {
        String json = new ObjectMapper().writeValueAsString(Map.of("to", to, "body", body));
        Request req = new Request.Builder().url(baseUrl + "/v1/messages").post(RequestBody.create(json, MediaType.get("application/json"))).build();
        try (Response r = new OkHttpClient().newCall(req).execute()) {
            if (!r.isSuccessful()) throw new RuntimeException("HTTP " + r.code());
            return (String) new ObjectMapper().readValue(r.body().string(), Map.class).get("id");
        }
    }
}
