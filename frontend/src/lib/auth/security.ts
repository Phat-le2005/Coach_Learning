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
  try {
    const originUrl = new URL(origin);
    const expectedUrl = new URL(expectedOrigin);
    if (originUrl.origin === expectedUrl.origin) return true;

    const isLoopback = (host: string) => host === "localhost" || host === "127.0.0.1";
    if (isLoopback(originUrl.hostname) && isLoopback(expectedUrl.hostname)) {
      const originPort = originUrl.port || (originUrl.protocol === "https:" ? "443" : "80");
      const expectedPort = expectedUrl.port || (expectedUrl.protocol === "https:" ? "443" : "80");
      return originPort === expectedPort && originUrl.protocol === expectedUrl.protocol;
    }
    return false;
  } catch {
    return false;
  }
}
