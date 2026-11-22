// Baseline: fetch (undici, built into Node.js), all defaults (GET).
export async function getUserProfile(baseUrl: string, userId: string): Promise<Record<string, unknown>> {
  const r = await fetch(`${baseUrl}/v1/users/${userId}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return await r.json();
}
