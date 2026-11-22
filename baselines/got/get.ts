// Baseline: got, all defaults (GET).
import got from "got";
export async function getUserProfile(baseUrl: string, userId: string): Promise<Record<string, unknown>> {
  return await got(`${baseUrl}/v1/users/${userId}`).json();
}
