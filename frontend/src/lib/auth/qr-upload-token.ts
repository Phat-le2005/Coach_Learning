export function getSessionSecret(): string {
  const secret = process.env.AUTH_SESSION_SECRET;
  if (!secret || secret.length < 32) {
    throw new Error(
      "AUTH_SESSION_SECRET must contain at least 32 characters.",
    );
  }
  return secret;
}

export interface QRUploadTokenPayload {
  v: 1;
  type: "qr_upload";
  attemptId: string;
  studentId: string;
  accessToken: string;
  expiresAt: number;
}

const encoder = new TextEncoder();
const decoder = new TextDecoder();

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/u, "");
}

function base64UrlDecode(value: string): Uint8Array {
  const base64 = value
    .replaceAll("-", "+")
    .replaceAll("_", "/")
    .padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(base64);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

async function hmac(secret: string, message: string): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return new Uint8Array(
    await crypto.subtle.sign("HMAC", key, encoder.encode(message)),
  );
}

function timingSafeEqual(left: Uint8Array, right: Uint8Array): boolean {
  if (left.length !== right.length) return false;
  let result = 0;
  for (let i = 0; i < left.length; i += 1) {
    result |= left[i] ^ right[i];
  }
  return result === 0;
}

export async function signQRUploadToken(
  params: {
    attemptId: string;
    studentId: string;
    accessToken: string;
    expiresInMinutes?: number;
  },
  secret = getSessionSecret(),
): Promise<{ token: string; expiresAt: number }> {
  if (secret.length < 32) {
    throw new Error("AUTH_SESSION_SECRET must contain at least 32 characters.");
  }
  const expiresInMinutes = params.expiresInMinutes ?? 20;
  const expiresAt = Date.now() + expiresInMinutes * 60 * 1000;

  const payload: QRUploadTokenPayload = {
    v: 1,
    type: "qr_upload",
    attemptId: params.attemptId,
    studentId: params.studentId,
    accessToken: params.accessToken,
    expiresAt,
  };

  const encodedPayload = base64UrlEncode(
    encoder.encode(JSON.stringify(payload)),
  );
  const signature = base64UrlEncode(await hmac(secret, encodedPayload));
  return {
    token: `${encodedPayload}.${signature}`,
    expiresAt,
  };
}

export async function verifyQRUploadToken(
  token: string | undefined,
  secret = getSessionSecret(),
  now = Date.now(),
): Promise<QRUploadTokenPayload | null> {
  if (!token || secret.length < 32) return null;
  const [encodedPayload, encodedSignature, extra] = token.split(".");
  if (!encodedPayload || !encodedSignature || extra !== undefined) return null;

  try {
    const expected = await hmac(secret, encodedPayload);
    const actual = base64UrlDecode(encodedSignature);
    if (!timingSafeEqual(expected, actual)) return null;

    const parsed = JSON.parse(
      decoder.decode(base64UrlDecode(encodedPayload)),
    ) as QRUploadTokenPayload;
    if (
      parsed.v !== 1 ||
      parsed.type !== "qr_upload" ||
      typeof parsed.attemptId !== "string" ||
      typeof parsed.studentId !== "string" ||
      typeof parsed.accessToken !== "string" ||
      typeof parsed.expiresAt !== "number" ||
      parsed.expiresAt <= now
    ) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}
