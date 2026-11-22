// Baseline: axios, all defaults (GET).
import axios from "axios";
export async function getUserProfile(baseUrl: string, userId: string): Promise<Record<string, unknown>> {
  return (await axios.get(`${baseUrl}/v1/users/${userId}`)).data;
}
