// Advice check (D52): AbortSignal.timeout passed to fetch and kept armed while the body is read.
export class ProfileError extends Error {}

export async function getUserProfile(baseUrl: string, userId: string): Promise<Record<string, unknown>> {
  const signal = AbortSignal.timeout(10_000);
  try {
    const res = await fetch(`${baseUrl.replace(/\/$/, "")}/v1/users/${encodeURIComponent(userId)}`, { signal });
    if (res.status !== 200) {
      await res.body?.cancel(); // release the connection
      throw new ProfileError(`status ${res.status}`);
    }
    return (await res.json()) as Record<string, unknown>;
  } catch (e) {
    if (e instanceof ProfileError) throw e;
    throw new ProfileError(String(e));
  }
}
