// Documentation example (java.net.http.HttpClient Javadoc, class description): HttpClient.newBuilder()
// .connectTimeout(Duration.ofSeconds(20)) and HttpRequest.newBuilder()...timeout(Duration.ofMinutes(2)), sent with
// client.send(request, BodyHandlers.ofString()); proxy and authenticator omitted; placed in the minimal R1 function.
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpClient.Redirect;
import java.net.http.HttpClient.Version;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpResponse.BodyHandlers;
import java.time.Duration;
import java.util.Map;

public class UserProfileClient {
    static final HttpClient client = HttpClient.newBuilder()
        .version(Version.HTTP_1_1)
        .followRedirects(Redirect.NORMAL)
        .connectTimeout(Duration.ofSeconds(20))
        .build();

    public static class ProfileException extends Exception {
        public ProfileException(String m, Throwable c) { super(m, c); }
    }

    public static Map<String, Object> getUserProfile(String baseUrl, String userId) throws ProfileException {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(baseUrl.replaceAll("/$", "") + "/v1/users/" + userId))
            .timeout(Duration.ofMinutes(2))
            .build();
        try {
            HttpResponse<String> response = client.send(request, BodyHandlers.ofString());
            if (response.statusCode() != 200) throw new ProfileException("status " + response.statusCode(), null);
            return new ObjectMapper().readValue(response.body(), new TypeReference<Map<String, Object>>() {});
        } catch (ProfileException e) {
            throw e;
        } catch (Exception e) {
            throw new ProfileException(e.toString(), e);
        }
    }
}
