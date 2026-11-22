package lcr;

// Prepare step for Java solutions (no network): compile with javac (JDK
// compiler API) against the offered libraries; detect missing packages.
// Input: /src/Solution.java  Output: /out/classes/, /out/prepare.json

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class Prepare {
    static final Pattern PUBLIC_TYPE = Pattern.compile("(?m)^\\s*public\\s+(?:(?:final|abstract|sealed|non-sealed|static)\\s+)*(?:class|record|interface|enum)\\s+([A-Za-z_$][A-Za-z0-9_$]*)");
    static final Pattern MISSING_PKG = Pattern.compile("package ([A-Za-z0-9_.]+) does not exist");

    public static void main(String[] a) throws Exception {
        long t0 = System.nanoTime();
        ObjectMapper m = new ObjectMapper();
        ObjectNode out = m.createObjectNode();
        out.put("schema", "prepare/1");
        out.put("lang", "java");
        out.put("tool", "javac " + Runtime.version());
        String src = Files.readString(Path.of("/src/Solution.java"), StandardCharsets.UTF_8);
        Matcher pm = PUBLIC_TYPE.matcher(src);
        String name = pm.find() ? pm.group(1) : "Solution";
        out.put("public_type", name);
        Path dir = Files.createDirectories(Path.of("/tmp/src"));
        Path file = dir.resolve(name + ".java");
        Files.writeString(file, src, StandardCharsets.UTF_8);
        Path classes = Files.createDirectories(Path.of("/out/classes"));

        List<String> cp = new ArrayList<>();
        try (var s = Files.list(Path.of("/opt/lcr-java/lib"))) { s.sorted().forEach(p -> cp.add(p.toString())); }
        JavaCompiler jc = ToolProvider.getSystemJavaCompiler();
        DiagnosticCollector<JavaFileObject> diags = new DiagnosticCollector<>();
        boolean ok;
        try (StandardJavaFileManager fm = jc.getStandardFileManager(diags, Locale.ROOT, StandardCharsets.UTF_8)) {
            List<String> opts = List.of("--release", "25", "-proc:none", "-encoding", "UTF-8", "-nowarn",
                "-cp", String.join(File.pathSeparator, cp), "-d", classes.toString());
            ok = jc.getTask(null, fm, diags, opts, null, fm.getJavaFileObjects(file.toFile())).call();
        }
        ArrayNode errs = out.putArray("errors");
        TreeSet<String> missing = new TreeSet<>();
        for (Diagnostic<? extends JavaFileObject> d : diags.getDiagnostics()) {
            if (d.getKind() != Diagnostic.Kind.ERROR) continue;
            String msg = d.getMessage(Locale.ROOT);
            errs.add(d.getLineNumber() + ":" + d.getColumnNumber() + " [" + d.getCode() + "] " + msg);
            Matcher mm = MISSING_PKG.matcher(msg);
            if (mm.find()) missing.add(mm.group(1));
        }
        String cat = ok ? "ok" : (!missing.isEmpty() ? "missing_dependency" : "compile_error");
        if (!missing.isEmpty()) { ArrayNode ms = out.putArray("missing"); missing.forEach(ms::add); }
        out.put("category", cat);
        out.put("duration_s", (System.nanoTime() - t0) / 1e9);
        Files.writeString(Path.of("/out/prepare.json"), m.writerWithDefaultPrettyPrinter().writeValueAsString(out));
    }
}
