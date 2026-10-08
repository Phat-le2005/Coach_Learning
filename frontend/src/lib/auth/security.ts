export function generateCsrfToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function constantTimeEqual(left: string | null | undefined, right: string | null | undefined): boolean {
  if (!left || !right || left.length !== right.length) return false;
  let result = 0;
  for (let index = 0; index < left.length; index += 1) result |= left.charCodeAt(index) ^ right.charCodeAt(index);
  return result === 0;
}

export function isTrustedMutationOrigin(origin: string | null, expectedOrigin: string, fetchSite: string | null): boolean {
  if (fetchSite === "cross-site") return false;
  if (!origin) return false;
  try { return new URL(origin).origin === new URL(expectedOrigin).origin; }
  catch { return false; }
}
