// Prepare step for TypeScript solutions (runs once per solution, in a
// container without network): transpile TS -> ESM JavaScript with esbuild
// (no type checking, like tsx/ts-node --transpile-only), and detect imports of
// packages that are not installed (missing_dependency).
//
// Input:  /src/solution.ts     Output: /out/solution.mjs, /out/prepare.json
import fs from "node:fs";
import { builtinModules } from "node:module";
import { createRequire } from "node:module";

const require = createRequire("/opt/lcr-tools/");
const esbuild = require("esbuild");

const src = fs.readFileSync("/src/solution.ts", "utf8");
const out = { schema: "prepare/1", lang: "typescript", tool: `esbuild ${esbuild.version}`, node: process.version };
const t0 = process.hrtime.bigint();

function finish(category, extra = {}) {
  Object.assign(out, { category, duration_s: Number(process.hrtime.bigint() - t0) / 1e9 }, extra);
  fs.writeFileSync("/out/prepare.json", JSON.stringify(out, null, 1));
  process.exit(0);
}

let js;
try {
  const r = esbuild.transformSync(src, { loader: "ts", format: "esm", target: "node26", sourcefile: "solution.ts" });
  js = r.code;
  out.warnings = r.warnings.map((w) => w.text);
} catch (e) {
  finish("compile_error", { errors: (e.errors || []).map((x) => `${x.location ? x.location.line + ":" + x.location.column + " " : ""}${x.text}`), message: String(e.message).slice(0, 4000) });
}

// Resolve every import against /node_modules (the offered libraries only).
const builtins = new Set([...builtinModules, ...builtinModules.map((m) => "node:" + m)]);
let missing = [];
try {
  await esbuild.build({
    stdin: { contents: js, resolveDir: "/", sourcefile: "solution.mjs", loader: "js" },
    bundle: true, write: false, platform: "node", format: "esm", logLevel: "silent",
    external: [...builtins], nodePaths: ["/node_modules"], absWorkingDir: "/",
  });
} catch (e) {
  for (const x of e.errors || []) {
    const m = /Could not resolve "([^"]+)"/.exec(x.text);
    if (m) missing.push(m[1]);
  }
  if (!missing.length) {
    finish("compile_error", { errors: (e.errors || []).map((x) => x.text), stage: "resolve" });
  }
}
fs.writeFileSync("/out/solution.mjs", js);
if (missing.length) finish("missing_dependency", { missing: [...new Set(missing)] });
finish("ok");
