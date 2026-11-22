// Documentation example (got, documentation/6-timeout.md): timeout: { lookup: 100, connect: 50, secureConnect: 50,
// socket: 1000, send: 10000, response: 1000 }, placed in the minimal R1 function of the D61 check.
import got from "got";

export class ProfileError extends Error {}

export async function getUserProfile(baseUrl: string, userId: string): Promise<Record<string, unknown>> {
  const url = `${baseUrl.replace(/\/$/, "")}/v1/users/${userId}`;
  try {
    const res = await got(url, {
      timeout: {
        lookup: 100,
        connect: 50,
        secureConnect: 50,
        socket: 1000,
        send: 10000,
        response: 1000,
      },
      throwHttpErrors: false,
    });
    if (res.statusCode !== 200) throw new ProfileError(`status ${res.statusCode}`);
    return JSON.parse(res.body) as Record<string, unknown>;
  } catch (err) {
    if (err instanceof ProfileError) throw err;
    throw new ProfileError(String(err));
  }
}
