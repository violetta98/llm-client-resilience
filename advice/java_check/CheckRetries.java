// Round 11: library retry behavior that the mock cannot show (one address, no long Retry-After). Local raw-socket
// server on 0.0.0.0 inside a container without network; OkHttp 5.5.0 and Apache HttpClient 5.6.5 from the run image.
//   docker run --rm --network none -v "$PWD/advice:/adv:ro" --entrypoint java lcr-run-java:dev \
//     -cp "/opt/lcr-java/lib/*" /adv/java_check/CheckRetries.java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import org.apache.hc.client5.http.classic.methods.HttpPost;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.core5.http.ContentType;
import org.apache.hc.core5.http.io.entity.StringEntity;
import org.apache.hc.core5.util.Timeout;

public class CheckRetries {
    // mode: "drop" = read the request, close without a response; "408" = 408 then 200; "503ra30" = 503 Retry-After: 30
    // then 200; "silent" = read the request, send nothing for 20 s
    static volatile String mode = "drop";
    static final AtomicInteger requests = new AtomicInteger();

    static String readRequest(InputStream in) throws IOException {
        ByteArrayOutputStream head = new ByteArrayOutputStream();
        int b, state = 0;
        while (state < 4 && (b = in.read()) != -1) {
            head.write(b);
            state = (b == '\r' && (state == 0 || state == 2)) || (b == '\n' && (state == 1 || state == 3)) ? state + 1 : 0;
        }
        String h = head.toString(StandardCharsets.ISO_8859_1);
        int len = 0;
        for (String line : h.split("\r\n"))
            if (line.toLowerCase().startsWith("content-length:")) len = Integer.parseInt(line.substring(15).trim());
        in.readNBytes(len);
        return h;
    }

    static void serve(Socket s) {
        try (s) {
            InputStream in = s.getInputStream();
            OutputStream out = s.getOutputStream();
            while (true) {
                String h = readRequest(in);
                if (h.isEmpty()) return;
                int n = requests.incrementAndGet();
                switch (mode) {
                    case "drop" -> { return; }
                    case "silent" -> { Thread.sleep(20000); return; }
                    case "408" -> out.write((n == 1 ? "HTTP/1.1 408 Request Timeout\r\nContent-Length: 0\r\n\r\n"
                            : "HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}").getBytes(StandardCharsets.ISO_8859_1));
                    case "503ra30" -> out.write((n == 1 ? "HTTP/1.1 503 Service Unavailable\r\nRetry-After: 30\r\nContent-Length: 0\r\n\r\n"
                            : "HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}").getBytes(StandardCharsets.ISO_8859_1));
                    default -> { return; }
                }
                out.flush();
            }
        } catch (Exception ignored) {
        }
    }

    static String timed(Callable<String> c, long limitS) {
        ExecutorService ex = Executors.newSingleThreadExecutor(r -> { Thread t = new Thread(r); t.setDaemon(true); return t; });
        long t0 = System.nanoTime();
        Future<String> f = ex.submit(c);
        String res;
        try {
            res = f.get(limitS, TimeUnit.SECONDS);
        } catch (TimeoutException e) {
            res = "no return within " + limitS + " s";
        } catch (ExecutionException e) {
            res = "error " + e.getCause().getClass().getSimpleName();
        } catch (InterruptedException e) {
            res = "interrupted";
        }
        return String.format("%s after %.1f s", res, (System.nanoTime() - t0) / 1e9);
    }

    static void report(String name, String outcome) {
        System.out.printf("%s: %s; requests received %d%n", name, outcome, requests.get());
    }

    public static void main(String[] args) throws Exception {
        ServerSocket ss = new ServerSocket(0, 50, InetAddress.getByName("0.0.0.0"));
        int port = ss.getLocalPort();
        Thread acc = new Thread(() -> {
            while (true) {
                try {
                    Socket s = ss.accept();
                    Thread t = new Thread(() -> serve(s));
                    t.setDaemon(true);
                    t.start();
                } catch (IOException e) {
                    return;
                }
            }
        });
        acc.setDaemon(true);
        acc.start();
        String url = "http://svc.test:" + port + "/v1/messages";
        MediaType json = MediaType.get("application/json");

        // OkHttp: a POST sent on a fresh connection, server closes without a response; one vs two addresses
        for (int nAddr : new int[]{1, 2}) {
            mode = "drop";
            requests.set(0);
            List<InetAddress> addrs = nAddr == 1 ? List.of(InetAddress.getByName("127.0.0.1"))
                    : List.of(InetAddress.getByName("127.0.0.1"), InetAddress.getByName("127.0.0.2"));
            OkHttpClient c = new OkHttpClient.Builder().dns(h -> addrs).build();
            String out = timed(() -> {
                try (var r = c.newCall(new Request.Builder().url(url).post(RequestBody.create("{}".getBytes(), json)).build()).execute()) {
                    return "status " + r.code();
                }
            }, 30);
            report("OkHttp 5.5.0 default, POST, fresh connection, server closes after the request, " + nAddr + " address(es)", out);
            OkHttpClient c2 = c.newBuilder().retryOnConnectionFailure(false).build();
            requests.set(0);
            out = timed(() -> {
                try (var r = c2.newCall(new Request.Builder().url(url).post(RequestBody.create("{}".getBytes(), json)).build()).execute()) {
                    return "status " + r.code();
                }
            }, 30);
            report("OkHttp 5.5.0 retryOnConnectionFailure(false), same, " + nAddr + " address(es)", out);
        }
        // OkHttp: 408 to a POST
        mode = "408";
        requests.set(0);
        OkHttpClient c1 = new OkHttpClient.Builder().dns(h -> List.of(InetAddress.getByName("127.0.0.1"))).build();
        report("OkHttp 5.5.0 default, POST answered 408 then 200", timed(() -> {
            try (var r = c1.newCall(new Request.Builder().url(url).post(RequestBody.create("{}".getBytes(), json)).build()).execute()) {
                return "status " + r.code();
            }
        }, 30));
        requests.set(0);
        OkHttpClient c1b = c1.newBuilder().retryOnConnectionFailure(false).build();
        report("OkHttp 5.5.0 retryOnConnectionFailure(false), POST answered 408 then 200", timed(() -> {
            try (var r = c1b.newCall(new Request.Builder().url(url).post(RequestBody.create("{}".getBytes(), json)).build()).execute()) {
                return "status " + r.code();
            }
        }, 30));

        // Apache HttpClient 5: POST answered 503 with Retry-After: 30
        String aurl = "http://127.0.0.1:" + port + "/v1/messages";
        for (String variant : new String[]{"default", "cancel after 3 s", "disableAutomaticRetries + cancel after 3 s"}) {
            mode = "503ra30";
            requests.set(0);
            var b = HttpClients.custom().setDefaultRequestConfig(RequestConfig.custom()
                    .setResponseTimeout(Timeout.ofSeconds(5)).build());
            if (variant.startsWith("disable")) b.disableAutomaticRetries();
            CloseableHttpClient c = b.build();
            HttpPost post = new HttpPost(aurl);
            post.setEntity(new StringEntity("{}", ContentType.APPLICATION_JSON));
            ScheduledExecutorService sch = Executors.newSingleThreadScheduledExecutor();
            if (variant.contains("cancel")) sch.schedule(() -> post.cancel(), 3, TimeUnit.SECONDS);
            report("Apache HttpClient 5.6.5 " + variant + ", POST answered 503 Retry-After: 30 then 200",
                    timed(() -> c.execute(post, r -> "status " + r.getCode()), 45));
            sch.shutdownNow();
        }
        // Apache HttpClient 5: response timeout (1 s) on a POST and a GET, no response at all
        for (String m : new String[]{"POST", "GET"}) {
            mode = "silent";
            requests.set(0);
            CloseableHttpClient c = HttpClients.custom().setDefaultRequestConfig(RequestConfig.custom()
                    .setResponseTimeout(Timeout.ofSeconds(1)).build()).build();
            var req = m.equals("POST") ? new HttpPost(aurl) : new org.apache.hc.client5.http.classic.methods.HttpGet(aurl);
            if (req instanceof HttpPost p) p.setEntity(new StringEntity("{}", ContentType.APPLICATION_JSON));
            report("Apache HttpClient 5.6.5 default, " + m + ", no response (response timeout 1 s)",
                    timed(() -> c.execute(req, r -> "status " + r.getCode()), 30));
        }
        System.exit(0);
    }
}
