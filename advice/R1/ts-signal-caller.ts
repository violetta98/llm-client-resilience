// Advice check (D56): as ts-signal-through-body, but the caller can pass its own AbortSignal, which is combined with the
// 10 s deadline (AbortSignal.any, Node.js 20.3+); both stay armed while the body is read.
export class ProfileError extends Error {}

export async function getUserProfile(baseUrl: string, userId: string, opts: { signal?: AbortSignal } = {}): Promise<Record<string, unknown>> {
  const deadline = AbortSignal.timeout(10_000);
  const signal = opts.signal ? AbortSignal.any([opts.signal, deadline]) : deadline;
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
