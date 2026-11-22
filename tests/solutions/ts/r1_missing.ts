import { request } from "undici";
export async function getUserProfile(baseUrl: string, userId: string) { return (await request(baseUrl)).body.json(); }
