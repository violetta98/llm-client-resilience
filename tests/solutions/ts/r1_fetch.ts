// Harness test solution (NOT a reference): built-in fetch with defaults.
interface UserProfile { id: string; name: string; email: string; created_at: string }

export async function getUserProfile(baseUrl: string, userId: string): Promise<UserProfile> {
  const r = await fetch(`${baseUrl}/v1/users/${userId}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()) as UserProfile;
}
