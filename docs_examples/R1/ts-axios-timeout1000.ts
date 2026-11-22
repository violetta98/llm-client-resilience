// Documentation example (axios, Request Config): timeout: 1000, placed in the minimal R1 function of the D61 check.
import axios from "axios";

export class ProfileError extends Error {}

export async function getUserProfile(baseUrl: string, userId: string): Promise<Record<string, unknown>> {
  const url = `${baseUrl.replace(/\/$/, "")}/v1/users/${userId}`;
  try {
    const res = await axios.get(url, { timeout: 1000, validateStatus: () => true });
    if (res.status !== 200) throw new ProfileError(`status ${res.status}`);
    return res.data as Record<string, unknown>;
  } catch (err) {
    if (err instanceof ProfileError) throw err;
    throw new ProfileError(String(err));
  }
}
