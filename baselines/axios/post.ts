// Baseline: axios, all defaults (POST).
import axios from "axios";
export async function sendSms(baseUrl: string, to: string, body: string): Promise<string> {
  return (await axios.post(`${baseUrl}/v1/messages`, { to, body })).data.id;
}
