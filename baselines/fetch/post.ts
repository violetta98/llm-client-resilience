// Baseline: fetch (undici, built into Node.js), all defaults (POST).
export async function sendSms(baseUrl: string, to: string, body: string): Promise<string> {
  const r = await fetch(`${baseUrl}/v1/messages`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ to, body }) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()).id;
}
