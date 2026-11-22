package lcr;

// Java driver. Same protocol and result schema (result/1) as
// runner/python/driver.py. System.nanoTime() is CLOCK_MONOTONIC on Linux.

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.lang.management.ManagementFactory;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.stream.Stream;

public final class Driver {
    static final ObjectMapper M = new ObjectMapper().disable(SerializationFeature.FAIL_ON_EMPTY_BEANS);
    static final int MAX_VALUE = 64 * 1024;
    static final String[] SYSCTLS = {"net/ipv4/tcp_syn_retries", "net/ipv4/tcp_synack_retries", "net/ipv4/tcp_retries1",
        "net/ipv4/tcp_retries2", "net/ipv4/tcp_keepalive_time", "net/ipv4/tcp_keepalive_intvl",
        "net/ipv4/tcp_keepalive_probes", "net/ipv4/tcp_fin_timeout", "net/ipv4/ip_local_port_range",
        "net/ipv4/tcp_tw_reuse", "net/core/somaxconn"};

    static PrintStream markers;
    static String nonce;
    static final ObjectNode res = M.createObjectNode();
    static volatile boolean finished = false;
    static final Object lock = new Object();

    static long mono() { return System.nanoTime(); }

    static void emit(String kind, String payload) {
        synchronized (lock) {
            markers.print("@@LCR " + nonce + " " + kind + " " + payload + "\n");
            markers.flush();
        }
    }

    static void finish(String status, double exitAfterS) {
        String json;
        synchronized (lock) {
            if (finished) return;
            finished = true;
            res.put("status", status);
            res.set("files", inspectFiles());
            try { json = M.writeValueAsString(res); }
            catch (Exception e) { json = "{\"schema\":\"result/1\",\"status\":\"bad_result_json\"}"; }
        }
        emit("RESULT", json);
        if (exitAfterS > 0) {
            try { Thread.sleep((long) (exitAfterS * 1000)); } catch (InterruptedException ignored) { }
        }
        emit("EXIT", Long.toString(mono()));
        Runtime.getRuntime().halt(0);
    }

    static ObjectNode describe(Throwable e, int depth) {
        ObjectNode d = M.createObjectNode();
        d.put("type", e.getClass().getName());
        ArrayNode mro = d.putArray("mro");
        for (Class<?> c = e.getClass().getSuperclass(); c != null && c != Object.class; c = c.getSuperclass()) mro.add(c.getName());
        String msg = String.valueOf(e.getMessage());
        d.put("message", msg.length() > 4000 ? msg.substring(0, 4000) : msg);
        if (depth == 0) {
            StringWriter sw = new StringWriter();
            e.printStackTrace(new PrintWriter(sw));
            String st = sw.toString();
            d.put("stack", st.length() > 8000 ? st.substring(0, 8000) : st);
        }
        Throwable c = e.getCause();
        if (c != null && c != e && depth < 5) d.set("chain", describe(c, depth + 1));
        return d;
    }

    static ObjectNode encode(Object v) {
        ObjectNode out = M.createObjectNode();
        String s;
        String enc = "json";
        try { s = M.writeValueAsString(v); }
        catch (Exception e) { s = String.valueOf(v); enc = "repr"; }
        out.put("enc", enc);
        out.put("type", v == null ? "null" : v.getClass().getName());
        out.put("len", s.length());
        if (s.length() > MAX_VALUE) { out.put("data", s.substring(0, MAX_VALUE)); out.put("truncated", true); }
        else out.put("data", s);
        return out;
    }

    /** Finds the target method by name and arity in the prepared solution classes. */
    static Method findTarget(Path classes, String name, int arity) throws Exception {
        List<Method> cands = new ArrayList<>();
        List<String> seen = new ArrayList<>();
        try (Stream<Path> w = Files.walk(classes)) {
            for (Path p : (Iterable<Path>) w::iterator) {
                String rel = classes.relativize(p).toString();
                if (!rel.endsWith(".class")) continue;
                String cn = rel.substring(0, rel.length() - 6).replace('/', '.');
                seen.add(cn);
                Class<?> c;
                try { c = Class.forName(cn, false, Driver.class.getClassLoader()); }
                catch (Throwable t) { continue; }
                for (Method m : c.getDeclaredMethods()) {
                    if (m.getName().equals(name) && m.getParameterCount() == arity && !m.isSynthetic()) cands.add(m);
                }
            }
        }
        if (cands.isEmpty()) throw new NoSuchMethodException("lcr: no method " + name + " with " + arity + " parameters in " + seen);
        cands.sort((a, b) -> score(b) - score(a));
        Method m = cands.get(0);
        m.setAccessible(true);
        return m;
    }

    static int score(Method m) {
        int s = 0;
        if (Modifier.isStatic(m.getModifiers())) s += 2;
        if (Modifier.isPublic(m.getModifiers())) s += 1;
        if (!m.getDeclaringClass().getName().contains("$")) s += 4;
        return s;
    }

    static Object invoke(Method m, JsonNode args) throws Throwable {
        Object[] a = new Object[m.getParameterCount()];
        for (int i = 0; i < a.length; i++) {
            a[i] = M.convertValue(args.get(i), M.getTypeFactory().constructType(m.getGenericParameterTypes()[i]));
        }
        Object target = null;
        if (!Modifier.isStatic(m.getModifiers())) {
            var ctor = m.getDeclaringClass().getDeclaredConstructor();
            ctor.setAccessible(true);
            target = ctor.newInstance();
        }
        Object r;
        try { r = m.invoke(target, a); }
        catch (InvocationTargetException e) { throw e.getCause(); }
        if (r instanceof CompletionStage<?> cs) r = cs.toCompletableFuture();
        if (r instanceof Future<?> f) {
            try { r = f.get(); }
            catch (java.util.concurrent.ExecutionException e) { throw e.getCause() != null ? e.getCause() : e; }
        }
        return r;
    }

    static ObjectNode runOne(Method m, JsonNode args, int index, long tStart) {
        ObjectNode c = M.createObjectNode();
        c.put("index", index);
        c.put("t_start", tStart);
        try {
            Object v = invoke(m, args);
            long t = mono();
            c.put("status", "returned"); c.put("t_end", t); c.put("duration_s", (t - tStart) / 1e9);
            c.set("value", encode(v));
        } catch (Throwable e) {
            long t = mono();
            c.put("status", "raised"); c.put("t_end", t); c.put("duration_s", (t - tStart) / 1e9);
            c.set("error", describe(e, 0));
        }
        return c;
    }

    static JsonNode planNode;

    static ArrayNode inspectFiles() {
        ArrayNode a = M.createArrayNode();
        if (planNode == null || !planNode.has("inspect_paths")) return a;
        for (JsonNode pn : planNode.get("inspect_paths")) {
            ObjectNode d = a.addObject();
            Path p = Path.of(pn.asText());
            d.put("path", pn.asText());
            d.put("exists", Files.isRegularFile(p));
            if (Files.isRegularFile(p)) {
                try {
                    byte[] b = Files.readAllBytes(p);
                    d.put("size", b.length);
                    d.put("sha256", java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(b)));
                } catch (Exception e) { d.put("error", e.toString()); }
            }
        }
        return a;
    }

    static ObjectNode env() {
        ObjectNode e = M.createObjectNode();
        ObjectNode sc = e.putObject("sysctl");
        for (String p : SYSCTLS) {
            String k = p.replace('/', '.');
            try { sc.put(k, Files.readString(Path.of("/proc/sys/" + p)).trim()); }
            catch (Exception x) { sc.put(k, "unreadable: " + x); }
        }
        try { e.put("kernel", Files.readString(Path.of("/proc/sys/kernel/osrelease")).trim()); } catch (Exception ignored) { }
        e.put("cpus", Runtime.getRuntime().availableProcessors());
        e.put("max_memory", Runtime.getRuntime().maxMemory());
        e.putPOJO("jvm_args", ManagementFactory.getRuntimeMXBean().getInputArguments());
        return e;
    }

    static Thread watchdog(double limitS, long t0, Runnable onTimeout) {
        Thread t = new Thread(() -> {
            long deadline = t0 + (long) (limitS * 1e9);
            while (true) {
                long rem = deadline - mono();
                if (rem <= 0) { onTimeout.run(); return; }
                try { Thread.sleep(Math.max(1, rem / 1_000_000)); } catch (InterruptedException ie) { return; }
            }
        }, "lcr-watchdog");
        t.setDaemon(true);
        t.start();
        return t;
    }

    public static void main(String[] argv) throws Exception {
        String planPath = System.getenv().getOrDefault("LCR_PLAN", "/plan/plan.json");
        JsonNode plan = M.readTree(Files.readString(Path.of(planPath)));
        planNode = plan;
        nonce = plan.get("nonce").asText();
        markers = new PrintStream(new FileOutputStream(FileDescriptor.out), true, StandardCharsets.UTF_8);
        System.setOut(System.err); // solution output -> stderr

        res.put("schema", "result/1");
        res.put("lang", "java");
        ObjectNode rt = res.putObject("runtime");
        rt.put("java", Runtime.version().toString());
        rt.put("vm", System.getProperty("java.vm.name") + " " + System.getProperty("java.vm.version"));
        res.put("function", plan.get("function").asText());
        res.put("mode", plan.get("mode").asText());
        double limitS = plan.get("limit_s").asDouble();
        res.put("limit_s", limitS);
        res.set("env", env());
        res.putNull("t_ready"); res.putNull("t_start"); res.putNull("t_end");

        // --- import (load classes, find target) ---------------------------------
        JsonNode calls = plan.get("calls");
        int arity = calls.get(0).get("args").size();
        Method m;
        long ti = mono();
        ObjectNode imp = res.putObject("import");
        imp.put("t", ti);
        try {
            m = findTarget(Path.of(plan.get("solution").asText()), plan.get("function").asText(), arity);
            imp.put("ok", true);
            imp.put("method", m.toGenericString());
            imp.put("duration_s", (mono() - ti) / 1e9);
        } catch (Throwable e) {
            imp.put("ok", false);
            imp.set("error", describe(e, 0));
            finish("import_error", 0);
            return;
        }

        // --- warm-up ------------------------------------------------------------
        long wt0 = mono();
        Thread wd = watchdog(plan.path("warmup_limit_s").asDouble(60), wt0, () -> finish("warmup_no_return", 0));
        ObjectNode w = runOne(m, plan.get("warmup_args"), 0, wt0);
        wd.interrupt();
        synchronized (lock) { res.set("warmup", w); }

        // --- measured call(s) ---------------------------------------------------
        long tr = mono();
        synchronized (lock) { res.put("t_ready", tr); }
        emit("READY", Long.toString(tr));
        long ts = mono();
        synchronized (lock) { res.put("t_start", ts); }
        emit("START", Long.toString(ts));
        int n = calls.size();
        ObjectNode[] out = new ObjectNode[n];
        long[] starts = new long[n];
        Thread wdm = watchdog(limitS, ts, () -> {
            synchronized (lock) {
                ArrayNode a = res.putArray("calls");
                for (int i = 0; i < n; i++) {
                    if (out[i] != null) { a.add(out[i]); continue; }
                    ObjectNode c = M.createObjectNode();
                    c.put("index", i); c.put("status", "no_return");
                    c.put("t_start", starts[i] != 0 ? starts[i] : ts); c.putNull("t_end");
                    a.add(c);
                }
            }
            finish("no_return", 0);
        });
        if (n == 1) {
            starts[0] = ts;
            out[0] = runOne(m, calls.get(0).get("args"), 0, ts);
        } else {
            CountDownLatch gate = new CountDownLatch(1);
            Thread[] th = new Thread[n];
            for (int i = 0; i < n; i++) {
                final int k = i;
                th[i] = new Thread(() -> {
                    try { gate.await(); } catch (InterruptedException ignored) { }
                    long st = mono();
                    starts[k] = st;
                    out[k] = runOne(m, calls.get(k).get("args"), k, st);
                }, "lcr-call-" + i);
                th[i].setDaemon(true);
                th[i].start();
            }
            gate.countDown();
            for (Thread t : th) t.join();
        }
        if (finished) { Thread.sleep(Long.MAX_VALUE); }
        wdm.interrupt();
        long te = mono();
        boolean allRet = true, allRaised = true;
        synchronized (lock) {
            ArrayNode a = res.putArray("calls");
            for (ObjectNode c : out) {
                a.add(c);
                allRet &= "returned".equals(c.get("status").asText());
                allRaised &= "raised".equals(c.get("status").asText());
            }
            res.put("t_end", te);
        }
        emit("END", Long.toString(te));
        double linger = plan.path("linger_s").asDouble(5);
        double observe = plan.path("observe_s").asDouble(0) - (mono() - ts) / 1e9;
        linger = Math.max(linger, observe);
        synchronized (lock) { res.put("linger_s", linger); }
        finish(allRet ? "returned" : allRaised ? "raised" : "mixed", linger);
    }
}
