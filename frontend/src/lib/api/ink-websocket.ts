import { getBackendBaseUrl } from "./client";

export function inkWebSocketUrl(path: string, origin: string): string {
  const configured = process.env.MATH_INK_WS_ORIGIN?.trim();
  const endpoint = new URL(configured || getBackendBaseUrl());
  if (!["http:", "https:", "ws:", "wss:"].includes(endpoint.protocol) || endpoint.username || endpoint.password
      || endpoint.search || endpoint.hash || (configured && endpoint.pathname !== "/")) throw new Error("LIVE_CONFIG_INVALID");
  if (!configured && process.env.NODE_ENV !== "production" && ["127.0.0.1", "localhost"].includes(endpoint.hostname)) {
    endpoint.hostname = new URL(origin).hostname;
  }
  endpoint.protocol = ["https:", "wss:"].includes(endpoint.protocol) ? "wss:" : "ws:";
  if ((process.env.NODE_ENV === "production" || origin.startsWith("https:")) && (!configured || endpoint.protocol !== "wss:")) throw new Error("LIVE_WSS_REQUIRED");
  endpoint.pathname = path; endpoint.search = "";
  return endpoint.toString();
}
