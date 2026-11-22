// Documentation example (ky, readme, Usage): await ky.<method>(url).json() with the default options,
// placed in the minimal R1 function of the D61 check.
import ky from "ky";

export class ProfileError extends Error {}

export async function getUserProfile(baseUrl: string, userId: string): Promise<Record<string, unknown>> {
  const url = `${baseUrl.replace(/\/$/, "")}/v1/users/${userId}`;
  try {
    return await ky.get(url).json<Record<string, unknown>>();
  } catch (err) {
    throw new ProfileError(String(err));
  }
}
