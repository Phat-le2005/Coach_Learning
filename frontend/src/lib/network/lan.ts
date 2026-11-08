import { networkInterfaces } from "node:os";

type Interfaces = Record<string, { address: string; family: string | number; internal: boolean }[] | undefined>;

export function isLanIPv4(address: string): boolean {
  const parts = address.split(".");
  if (parts.length !== 4 || parts.some(p => !/^\d{1,3}$/.test(p) || Number(p) > 255 || String(Number(p)) !== p)) return false;
  const [a, b] = parts.map(Number);
  return a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
}

export function lanAddresses(interfaces: Interfaces = networkInterfaces()): string[] {
  const rows = Object.entries(interfaces).flatMap(([name, addresses]) =>
    /^(?:lo|veth|br-|virbr|docker|tun|tap|wg)|loopback|vethernet|wsl|docker|virtual|vmware|vbox|tailscale|tunnel|vpn/i.test(name) ? [] :
      (addresses ?? []).filter(a => !a.internal && (a.family === "IPv4" || a.family === 4) && isLanIPv4(a.address))
        .map(a => ({ address: a.address, priority: /wi-?fi|wl/i.test(name) ? 0 : /ethernet|en\d|eth\d|eno\d|enp\d|ens\d/i.test(name) ? 1 : 2 })));
  return [...new Set(rows.sort((a, b) => a.priority - b.priority || a.address.localeCompare(b.address)).map(a => a.address))];
}

export function lanEnabled(): boolean {
  return process.env.NODE_ENV !== "production" && process.env.COACH_LAN_MODE === "1";
}

function frontendPort(): string {
  const port = process.env.COACH_LAN_FRONTEND_PORT || "3000";
  if (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535) throw new Error("LAN_PORT_INVALID");
  return String(Number(port));
}

export function runtimeFrontendOrigins(): string[] {
  if (!lanEnabled()) return [];
  return ["localhost", "127.0.0.1", ...lanAddresses()].map(host => `http://${host}:${frontendPort()}`);
}

export function lanConnectionInfo() {
  const addresses = lanEnabled() ? lanAddresses() : [];
  const origins = addresses.map(host => `http://${host}:${frontendPort()}`);
  return { enabled: lanEnabled(), origin: origins[0] ?? null, origins,
    generation: origins.join("|"), status: !lanEnabled() ? "DISABLED" : origins.length ? "AVAILABLE" : "NO_LAN_ADDRESS" };
}

export function pairingOrigin(browserOrigin: string | null): string {
  if (lanEnabled()) {
    const info = lanConnectionInfo();
    // Prefer an already-reachable interface when the owner opened a LAN URL.
    if (browserOrigin && info.origins.includes(browserOrigin)) return browserOrigin;
    if (!info.origin) throw new Error("LAN_ADDRESS_UNAVAILABLE");
    return info.origin;
  }
  return new URL(process.env.NEXT_PUBLIC_APP_URL?.trim() || browserOrigin || "").origin;
}
