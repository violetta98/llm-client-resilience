// D56: does the caller's AbortSignal end ts-signal-caller before its own 10 s deadline? Local server that reads the
// request and never answers; the caller aborts after 1 s.
//   docker run --rm --network none -v "$PWD/advice:/adv:ro" --entrypoint node lcr-run-node:dev /adv/caller_check/check_caller.mjs
import http from "node:http";
const srv = http.createServer(() => {}).listen(0, "127.0.0.1");
await new Promise((r) => srv.on("listening", r));
const base = `http://127.0.0.1:${srv.address().port}`;
const { getUserProfile } = await import("/adv/R1/ts-signal-caller.ts");
const t0 = Date.now();
try {
  await getUserProfile(base, "u-1", { signal: AbortSignal.timeout(1000) });
  console.log(`ts-signal-caller, caller aborts after 1 s: returned a result after ${(Date.now() - t0) / 1000} s`);
} catch (e) {
  console.log(`ts-signal-caller, caller aborts after 1 s: ${e.constructor.name} after ${((Date.now() - t0) / 1000).toFixed(1)} s`);
}
process.exit(0);
