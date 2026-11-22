// Anti-pattern check (D52): AbortController timer cleared right after await fetch(), before the body is read.
export class ProfileError extends Error {}

export async function getUserProfile(baseUrl: string, userId: string): Promise<Record<string, unknown>> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 10_000);
  let res: Response;
  try {
    res = await fetch(`${baseUrl.replace(/\/$/, "")}/v1/users/${encodeURIComponent(userId)}`, { signal: ctrl.signal });
  } catch (e) {
    throw new ProfileError(String(e));
  } finally {
    clearTimeout(timer);
  }
  if (res.status !== 200) throw new ProfileError(`status ${res.status}`);
  return (await res.json()) as Record<string, unknown>;
}
