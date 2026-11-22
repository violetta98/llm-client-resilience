// Advice check (D52, revised D56): sendAsync(ofString) awaited with Future.get(timeout); cancel(true) on expiry and on
// interruption of the calling thread.
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class UserProfileClient {
    static final HttpClient CLIENT = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();

    public static class ProfileException extends Exception {
        public ProfileException(String m, Throwable c) { super(m, c); }
    }

    public static Map<String, Object> getUserProfile(String baseUrl, String userId) throws ProfileException {
        HttpRequest req = HttpRequest.newBuilder(URI.create(baseUrl.replaceAll("/$", "") + "/v1/users/" + userId)).GET().build();
        CompletableFuture<HttpResponse<String>> f = CLIENT.sendAsync(req, HttpResponse.BodyHandlers.ofString());
        try {
            HttpResponse<String> r = f.get(10, TimeUnit.SECONDS);
            if (r.statusCode() != 200) throw new ProfileException("status " + r.statusCode(), null);
            return new ObjectMapper().readValue(r.body(), new TypeReference<Map<String, Object>>() {});
        } catch (TimeoutException e) {
            f.cancel(true);
            throw new ProfileException("deadline exceeded", e);
        } catch (InterruptedException e) {  // the caller gave up: cancel the exchange and keep the interrupt (D56)
            f.cancel(true);
            Thread.currentThread().interrupt();
            throw new ProfileException("interrupted", e);
        } catch (ProfileException e) {
            throw e;
        } catch (Exception e) {
            throw new ProfileException(e.toString(), e);
        }
    }
}
