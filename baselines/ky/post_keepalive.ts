// Baseline: ky, all defaults (POST on a reused keep-alive connection, S8 variant, D42).
// ky runs on fetch, i.e. undici's global dispatcher (a keep-alive pool per origin).
import ky from "ky";
const client = ky.create({}); // shared instance, created once
export async function sendSms(baseUrl: string, to: string, body: string): Promise<string> {
  await client.get(`${baseUrl}/v1/messages`, { throwHttpErrors: false }).arrayBuffer(); // warm the pool; 405 ignored, body read
  const r: any = await client.post(`${baseUrl}/v1/messages`, { json: { to, body } }).json();
  return r.id;
}
