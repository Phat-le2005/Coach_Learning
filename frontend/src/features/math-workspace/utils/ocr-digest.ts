import { sha256 } from "js-sha256";

/** Content identity only; native and HTTP LAN paths must produce identical keys. */
export async function sha256Hex(value: string | ArrayBuffer | Uint8Array): Promise<string> {
  const bytes = typeof value === "string" ? new TextEncoder().encode(value)
    : value instanceof Uint8Array ? Uint8Array.from(value) : new Uint8Array(value);
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) return sha256(bytes);
  return [...new Uint8Array(await subtle.digest("SHA-256", bytes))].map(b => b.toString(16).padStart(2, "0")).join("");
}
