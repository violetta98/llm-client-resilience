// Baseline: got, all defaults (POST on a reused keep-alive connection, S8 variant, D42).
// The instance uses Node's https.globalAgent (keepAlive: true by default since Node 19).
import got from "got";
const client = got.extend({}); // shared instance, created once
export async function sendSms(baseUrl: string, to: string, body: string): Promise<string> {
  await client.get(`${baseUrl}/v1/messages`, { throwHttpErrors: false }); // warm the pool; 405 ignored, body read
  const r: any = await client.post(`${baseUrl}/v1/messages`, { json: { to, body } }).json();
  return r.id;
}
