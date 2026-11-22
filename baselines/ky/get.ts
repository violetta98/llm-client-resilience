// Baseline: ky, all defaults (GET).
import ky from "ky";
export async function getUserProfile(baseUrl: string, userId: string): Promise<Record<string, unknown>> {
  return await ky.get(`${baseUrl}/v1/users/${userId}`).json();
}
