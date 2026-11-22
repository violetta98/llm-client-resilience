// Baseline: OkHttp, all defaults (POST on a reused keep-alive connection, S8 variant, D42).
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

public class SmsClient {
    private static final OkHttpClient CLIENT = new OkHttpClient(); // shared client (connection pool), created once

    public static String sendSms(String baseUrl, String to, String body) throws Exception {
        try (Response g = CLIENT.newCall(new Request.Builder().url(baseUrl + "/v1/messages").build()).execute()) {
            g.body().string(); // warm the pool; 405 ignored, body read so the connection returns idle
        }
        String json = new ObjectMapper().writeValueAsString(Map.of("to", to, "body", body));
        Request req = new Request.Builder().url(baseUrl + "/v1/messages").post(RequestBody.create(json, MediaType.get("application/json"))).build();
        try (Response r = CLIENT.newCall(req).execute()) {
            if (!r.isSuccessful()) throw new RuntimeException("HTTP " + r.code());
            return (String) new ObjectMapper().readValue(r.body().string(), Map.class).get("id");
        }
    }
}
