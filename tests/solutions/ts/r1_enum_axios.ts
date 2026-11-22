// Non-erasable TS syntax (enum) + axios: must transpile and resolve.
import axios from "axios";
import got from "got";
import ky from "ky";
import pRetry from "p-retry";
enum Kind { A = "a" }
export async function getUserProfile(baseUrl: string, userId: string) {
  void got; void ky; void pRetry; void Kind.A;
  const r = await axios.get(`${baseUrl}/v1/users/${userId}`);
  return r.data;
}
