// Node.js driver (TypeScript solutions, transpiled by prepare.mjs).
// Same protocol and result schema (result/1) as runner/python/driver.py:
//   @@LCR <nonce> READY|START|END|RESULT|EXIT ...   on fd 1 (solution output -> stderr)
// Timestamps: process.hrtime.bigint() = CLOCK_MONOTONIC (libuv uv_hrtime).
import fs from "node:fs";
import os from "node:os";
import util from "node:util";
import { createHash } from "node:crypto";

const PLAN = JSON.parse(fs.readFileSync(process.env.LCR_PLAN || "/plan/plan.json", "utf8"));
const MAX_VALUE = 64 * 1024;
const SYSCTLS = ["net/ipv4/tcp_syn_retries", "net/ipv4/tcp_synack_retries", "net/ipv4/tcp_retries1",
  "net/ipv4/tcp_retries2", "net/ipv4/tcp_keepalive_time", "net/ipv4/tcp_keepalive_intvl",
  "net/ipv4/tcp_keepalive_probes", "net/ipv4/tcp_fin_timeout", "net/ipv4/ip_local_port_range",
  "net/ipv4/tcp_tw_reuse", "net/core/somaxconn"];

const mono = () => process.hrtime.bigint();
const MARKER_FD = 1;
// Solution output goes to stderr; stdout carries only markers (fs.writeSync on fd 1).
process.stdout.write = process.stderr.write.bind(process.stderr);

// BigInt-safe JSON (monotonic ns may exceed 2^53 on long-running hosts).
function toJSON(v) {
  return JSON.stringify(v, (_k, x) => (typeof x === "bigint" ? `__BIG__${x}` : x)).replace(/"__BIG__(\d+)"/g, "$1");
}
function emit(kind, payload) {
  fs.writeSync(MARKER_FD, `@@LCR ${PLAN.nonce} ${kind} ${payload}\n`);
}

const res = {
  schema: "result/1", lang: "typescript",
  runtime: { node: process.version, v8: process.versions.v8, undici: process.versions.undici },
  function: PLAN.function, mode: PLAN.mode, limit_s: PLAN.limit_s, env: environment(),
  import: null, warmup: null, calls: [], t_ready: null, t_start: null, t_end: null, status: null, events: [],
};
let finished = false;

function finish(status, exitAfterS = 0) {
  if (finished) return;
  finished = true;
  res.status = status;
  res.files = inspectFiles(PLAN.inspect_paths || []);
  emit("RESULT", toJSON(res));
  const exit = () => { emit("EXIT", mono()); process.exit(0); };
  if (exitAfterS > 0) setTimeout(exit, exitAfterS * 1000); else exit();
}

// Background failures of the solution must not kill the driver (Node's
// default for unhandled rejections) during the late-request window.
for (const ev of ["unhandledRejection", "uncaughtException"]) {
  process.on(ev, (e) => {
    const rec = { t: mono(), event: ev, error: describe(e) };
    if (finished) emit("EVENT", toJSON(rec)); // after RESULT: still recorded (stdout_markers.txt)
    else if (res.events.length < 100) res.events.push(rec);
    process.stderr.write(`[driver] ${ev}: ${util.inspect(e)}\n`);
  });
}

function describe(e, depth = 0) {
  if (e === null || typeof e !== "object") return { type: typeof e, message: String(e) };
  const d = {
    type: e.constructor ? e.constructor.name : "Object",
    name: e.name, message: String(e.message ?? "").slice(0, 4000),
    stack: String(e.stack ?? "").slice(-8000),
  };
  for (const k of ["code", "errno", "syscall", "status", "statusCode"]) if (e[k] !== undefined) d[k] = e[k];
  if (e.response && typeof e.response === "object" && e.response.status !== undefined) d.response_status = e.response.status;
  const next = e.cause;
  if (next !== undefined && depth < 5) { d.chain = describe(next, depth + 1); delete d.chain.stack; }
  if (Array.isArray(e.errors) && depth < 5) d.errors = e.errors.slice(0, 5).map((x) => { const y = describe(x, depth + 1); delete y.stack; return y; });
  return d;
}

function encodeValue(v) {
  let s, enc = "json";
  try { s = JSON.stringify(v); if (s === undefined) throw new Error("undefined"); }
  catch { s = util.inspect(v, { depth: 4 }); enc = "repr"; }
  const out = { enc, type: v === null ? "null" : (v?.constructor?.name ?? typeof v), len: s.length };
  if (s.length > MAX_VALUE) { out.data = s.slice(0, MAX_VALUE); out.truncated = true; } else out.data = s;
  return out;
}

function inspectFiles(paths) {
  return paths.map((p) => {
    try {
      const st = fs.statSync(p);
      if (!st.isFile()) return { path: p, exists: false };
      const h = createHash("sha256").update(fs.readFileSync(p)).digest("hex");
      return { path: p, exists: true, size: st.size, sha256: h };
    } catch { return { path: p, exists: false }; }
  });
}

function environment() {
  const sc = {};
  for (const p of SYSCTLS) {
    try { sc[p.replaceAll("/", ".")] = fs.readFileSync("/proc/sys/" + p, "utf8").trim(); }
    catch (e) { sc[p.replaceAll("/", ".")] = "unreadable: " + e.message; }
  }
  return { sysctl: sc, kernel: os.release(), uname: `${os.type()} ${os.hostname()} ${os.release()} ${os.version()} ${os.machine()}`,
    cpus: os.availableParallelism(), uid: process.getuid(), hostname: os.hostname() };
}

async function runOne(fn, args, index, tStart) {
  tStart = tStart ?? mono();
  try {
    const v = await fn(...args);
    const tEnd = mono();
    return { index, status: "returned", t_start: tStart, t_end: tEnd, duration_s: Number(tEnd - tStart) / 1e9, value: encodeValue(v) };
  } catch (e) {
    const tEnd = mono();
    return { index, status: "raised", t_start: tStart, t_end: tEnd, duration_s: Number(tEnd - tStart) / 1e9, error: describe(e) };
  }
}

// Watchdog: a referenced timer, so the process cannot exit early just because
// a never-settling promise left the event loop without handles.
function watchdog(limitS, t0, onTimeout) {
  const ms = Math.max(0, limitS * 1000 - Number(mono() - t0) / 1e6);
  return setTimeout(onTimeout, ms);
}

// --- import -----------------------------------------------------------------
let fn;
{
  const t0 = mono();
  try {
    const mod = await import(PLAN.solution);
    const name = PLAN.function;
    let how = "named";
    fn = mod[name];
    if (typeof fn !== "function" && mod.default && typeof mod.default[name] === "function") { fn = mod.default[name].bind(mod.default); how = "default.member"; }
    if (typeof fn !== "function" && typeof mod.default === "function") { fn = mod.default; how = "default"; }
    if (typeof fn !== "function") throw new TypeError(`export ${name} not found (exports: ${Object.keys(mod).join(", ")})`);
    res.import = { ok: true, t: t0, duration_s: Number(mono() - t0) / 1e9, export: how };
  } catch (e) {
    res.import = { ok: false, t: t0, error: describe(e) };
    finish("import_error");
  }
}

if (!finished) {
  // --- warm-up (separate normal ports; not measured) ---------------------------
  const wt0 = mono();
  const wd = watchdog(PLAN.warmup_limit_s ?? 60, wt0, () => finish("warmup_no_return"));
  res.warmup = await runOne(fn, PLAN.warmup_args, 0, wt0);
  clearTimeout(wd);
}

if (!finished) {
  // --- measured call(s) --------------------------------------------------------
  res.t_ready = mono();
  emit("READY", res.t_ready);
  res.t_start = mono();
  emit("START", res.t_start);
  const calls = new Array(PLAN.calls.length).fill(null);
  res.calls = calls;
  const wd = watchdog(PLAN.limit_s, res.t_start, () => {
    calls.forEach((c, i) => { if (!c || !c.status) calls[i] = { index: i, status: "no_return", t_start: c?.t_start ?? res.t_start, t_end: null }; });
    res.t_end = null;
    finish("no_return");
  });
  const ps = PLAN.calls.map((c, i) => {
    const t = mono();
    calls[i] = { index: i, t_start: t };
    return runOne(fn, c.args, i, t).then((r) => { if (!finished) calls[i] = r; });
  });
  await Promise.all(ps);
  if (!finished) {
    clearTimeout(wd);
    res.t_end = mono();
    emit("END", res.t_end);
    const st = new Set(calls.map((c) => c.status));
    const status = st.size === 1 && st.has("returned") ? "returned" : st.size === 1 && st.has("raised") ? "raised" : "mixed";
    const linger = PLAN.linger_s ?? 5;
    const observe = (PLAN.observe_s ?? 0) - Number(mono() - res.t_start) / 1e9;
    res.linger_s = Math.max(linger, observe);
    finish(status, res.linger_s);
  }
}
