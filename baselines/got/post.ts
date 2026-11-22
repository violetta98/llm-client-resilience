// Baseline: got, all defaults (POST).
import got from "got";
export async function sendSms(baseUrl: string, to: string, body: string): Promise<string> {
  const r: any = await got.post(`${baseUrl}/v1/messages`, { json: { to, body } }).json();
  return r.id;
}
