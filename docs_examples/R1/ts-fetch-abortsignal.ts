// Documentation example (MDN, AbortSignal.timeout()): fetch(url, { signal: AbortSignal.timeout(5000) }) with the
// body read in the same try block, placed in the minimal R1 function of the D61 check.
export class ProfileError extends Error {}

export async function getUserProfile(baseUrl: string, userId: string): Promise<Record<string, unknown>> {
  const url = `${baseUrl.replace(/\/$/, "")}/v1/users/${userId}`;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (res.status !== 200) throw new ProfileError(`status ${res.status}`);
    return (await res.json()) as Record<string, unknown>;
  } catch (err) {
    if (err instanceof ProfileError) throw err;
    throw new ProfileError(String(err));
  }
}
