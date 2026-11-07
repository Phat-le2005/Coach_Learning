import test from "node:test";
import assert from "node:assert/strict";
import { lanAddresses, isLanIPv4, lanConnectionInfo, pairingOrigin, runtimeFrontendOrigins } from "../src/lib/network/lan";
import { inkWebSocketUrl } from "../src/lib/api/ink-websocket";
import { isTrustedFrontendMutation } from "../src/lib/auth/security";

test("LAN discovery excludes virtual/public/loopback addresses and preserves eligible interfaces", () => {
  const nic = (address: string, internal = false) => [{address, internal, family: "IPv4"}];
  assert.deepEqual(lanAddresses({"vEthernet (WSL)": nic("172.29.16.1"), "br-f3169dba7944": nic("172.19.0.1"),
    vethaf7becd: nic("172.18.0.2"), "Wi-Fi": nic("192.168.2.20"),
    Ethernet: nic("10.0.0.5"), lo: nic("127.0.0.1", true), Public: nic("8.8.8.8")}).sort(), ["10.0.0.5", "192.168.2.20"]);
  for (const address of ["172.15.1.1", "172.32.1.1", "192.168.1.999", "192.168.01.2", "169.254.1.1", "::1"]) assert.equal(isLanIPv4(address), false);
  assert.deepEqual(lanAddresses({"Wi-Fi": nic("192.168.4.5")}), ["192.168.4.5"]);
  assert.equal(lanAddresses({Ethernet: nic("10.0.0.5"), "Wi-Fi": nic("192.168.4.5")})[0], "192.168.4.5");
  assert.equal(lanAddresses({enp3s0: nic("10.0.0.5"), wlo1: nic("192.168.4.5"), "br-1234": nic("172.19.0.1")})[0], "192.168.4.5");
});

test("LAN pairing ignores stale public URL, retains localhost, and rejects foreign WebSocket origins", () => {
  const before = {...process.env};
  const env = process.env as Record<string, string | undefined>;
  try {
    env.NODE_ENV = "development";
    process.env.COACH_LAN_MODE = "1";
    process.env.COACH_LAN_FRONTEND_PORT = "3050";
    process.env.API_BASE_URL = "http://127.0.0.1:8050";
    process.env.NEXT_PUBLIC_APP_URL = "http://192.168.1.99:3050";
    process.env.MATH_INK_WS_ORIGIN = "ws://192.168.1.99:8050";
    const info = lanConnectionInfo();
    assert.ok(runtimeFrontendOrigins().includes("http://localhost:3050"));
    assert.equal(inkWebSocketUrl("/live", "http://localhost:3050"), "ws://localhost:8050/live");
    assert.throws(() => inkWebSocketUrl("/live", "http://evil.invalid:3050"), /LAN_ORIGIN_DENIED/);
    assert.throws(() => inkWebSocketUrl("/live", "http://127.0.0.1:4000"), /LAN_ORIGIN_DENIED/);
    for (const origin of info.origins) {
      assert.equal(pairingOrigin(origin), origin);
      assert.equal(new URL(inkWebSocketUrl("/live", origin)).hostname, new URL(origin).hostname);
      assert.equal(isTrustedFrontendMutation(origin, origin, "cross-site"), false);
    }
    if (info.origin) assert.equal(pairingOrigin("http://localhost:3050"), info.origin);
    else assert.throws(() => pairingOrigin("http://localhost:3050"), /LAN_ADDRESS_UNAVAILABLE/);
    env.NODE_ENV = "production";
    assert.equal(lanConnectionInfo().enabled, false);
    assert.deepEqual(runtimeFrontendOrigins(), []);
  } finally {process.env = before;}
});
