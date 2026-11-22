// Baseline: fetch (undici, built into Node.js), all defaults (POST on a reused keep-alive connection, S8 variant, D42).
// fetch has no client object: every call goes through undici's global dispatcher
// (a keep-alive pool per origin), so the GET's connection is reused by the POST.
export async function sendSms(baseUrl: string, to: string, body: string): Promise<string> {
  await (await fetch(`${baseUrl}/v1/messages`)).arrayBuffer(); // warm the pool; 405 ignored, body read so the connection is idle
  const r = await fetch(`${baseUrl}/v1/messages`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ to, body }) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()).id;
}
