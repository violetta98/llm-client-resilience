// Baseline: axios, all defaults (POST on a reused keep-alive connection, S8 variant, D42).
// The instance uses Node's https.globalAgent (keepAlive: true by default since Node 19).
import axios from "axios";
const client = axios.create(); // shared instance, created once
export async function sendSms(baseUrl: string, to: string, body: string): Promise<string> {
  await client.get(`${baseUrl}/v1/messages`, { validateStatus: () => true }); // warm the pool; 405 ignored, body read
  return (await client.post(`${baseUrl}/v1/messages`, { to, body })).data.id;
}
