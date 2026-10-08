import type { Role } from "../api/contracts";
import { ROLES } from "../api/contracts";
import { SESSION_VERSION } from "./constants";

export interface SessionPayload {
  v: typeof SESSION_VERSION;
  userId: string;
  email: string;
  fullName: string;
  role: Role;
  expiresAt: number;
}

const encoder = new TextEncoder();
const decoder = new TextDecoder();

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/u, "");
}

function base64UrlDecode(value: string): Uint8Array {
  const base64 = value.replaceAll("-", "+").replaceAll("_", "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(base64);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

async function hmac(secret: string, message: string): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(message)));
}

function timingSafeEqual(left: Uint8Array, right: Uint8Array): boolean {
  if (left.length !== right.length) return false;
  let result = 0;
  for (let index = 0; index < left.length; index += 1) result |= left[index] ^ right[index];
  return result === 0;
}

function parsePayload(value: unknown): SessionPayload | null {
  if (typeof value !== "object" || value === null) return null;
  const source = value as Record<string, unknown>;
  if (source.v !== SESSION_VERSION || typeof source.userId !== "string" || typeof source.email !== "string" || typeof source.fullName !== "string" || typeof source.role !== "string" || !ROLES.includes(source.role as Role) || typeof source.expiresAt !== "number") return null;
  return source as unknown as SessionPayload;
}

export async function signSession(payload: SessionPayload, secret: string): Promise<string> {
  if (secret.length < 32) throw new Error("AUTH_SESSION_SECRET must contain at least 32 characters.");
  const encodedPayload = base64UrlEncode(encoder.encode(JSON.stringify(payload)));
  const signature = base64UrlEncode(await hmac(secret, encodedPayload));
  return `${encodedPayload}.${signature}`;
}

export async function verifySession(token: string | undefined, secret: string, now = Date.now()): Promise<SessionPayload | null> {
  if (!token || secret.length < 32) return null;
  const [encodedPayload, encodedSignature, extra] = token.split(".");
  if (!encodedPayload || !encodedSignature || extra !== undefined) return null;
  try {
    const expected = await hmac(secret, encodedPayload);
    const actual = base64UrlDecode(encodedSignature);
    if (!timingSafeEqual(expected, actual)) return null;
    const payload = parsePayload(JSON.parse(decoder.decode(base64UrlDecode(encodedPayload))) as unknown);
    return payload && payload.expiresAt > now ? payload : null;
  } catch {
    return null;
  }
}
