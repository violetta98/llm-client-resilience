// Baseline: ky, all defaults (POST).
import ky from "ky";
export async function sendSms(baseUrl: string, to: string, body: string): Promise<string> {
  const r: any = await ky.post(`${baseUrl}/v1/messages`, { json: { to, body } }).json();
  return r.id;
}
