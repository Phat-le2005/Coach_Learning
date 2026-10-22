import assert from "node:assert/strict";
import test from "node:test";

import { createSessionRefreshingFetcher, createSingleFlight, refreshSessionWithCurrentCheck } from "../src/lib/api/session-refresh.js";

const expired = () => Response.json({ error: { code: "INVALID_TOKEN", message: "Invalid or expired token." } }, { status: 401 });

test("expired Math Workspace access token refreshes and retries the original request once", async () => {
  let calls = 0;
  let refreshes = 0;
  const body = JSON.stringify({ page_index: 0, stroke_ids: ["stroke-id"] });
  const fetcher = createSessionRefreshingFetcher(
    async (_input, init) => {
      calls += 1;
      assert.equal(init?.method, "POST");
      assert.equal(init?.body, body);
      return calls === 1 ? expired() : Response.json({ latex: "x^2" });
    },
    async () => { refreshes += 1; },
  );

  const response = await fetcher("http://localhost/api/v2/math-solutions/attempts/id/ocr/recognize", { method: "POST", body });
  assert.equal(response.status, 200);
  assert.equal(calls, 2);
  assert.equal(refreshes, 1);
});

test("concurrent expired requests share one rotating refresh token", async () => {
  let calls = 0;
  let refreshes = 0;
  const fetcher = createSessionRefreshingFetcher(
    async () => {
      calls += 1;
      return calls <= 2 ? expired() : Response.json({ ok: true });
    },
    async () => {
      refreshes += 1;
      await new Promise((resolve) => setTimeout(resolve, 5));
    },
  );

  const responses = await Promise.all([fetcher("http://localhost/one"), fetcher("http://localhost/two")]);
  assert.deepEqual(responses.map((response) => response.status), [200, 200]);
  assert.equal(refreshes, 1);
  assert.equal(calls, 4);
});

test("failed refresh keeps the original 401 and does not retry the mutation", async () => {
  let calls = 0;
  const fetcher = createSessionRefreshingFetcher(
    async () => { calls += 1; return expired(); },
    async () => { throw new Error("Refresh expired"); },
  );
  const response = await fetcher("http://localhost/ocr", { method: "POST" });
  assert.equal(response.status, 401);
  assert.equal((await response.json()).error.code, "INVALID_TOKEN");
  assert.equal(calls, 1);
});

test("other 401 errors and successful responses do not rotate the refresh token", async () => {
  let refreshes = 0;
  const refresh = async () => { refreshes += 1; };
  const forbidden = createSessionRefreshingFetcher(
    async () => Response.json({ error: { code: "FORBIDDEN" } }, { status: 401 }), refresh,
  );
  const success = createSessionRefreshingFetcher(async () => Response.json({ ok: true }), refresh);
  assert.equal((await forbidden("http://localhost/ocr")).status, 401);
  assert.equal((await success("http://localhost/ocr")).status, 200);
  assert.equal(refreshes, 0);
});

test("a second 401 after refresh is returned without another refresh loop", async () => {
  let refreshes = 0;
  let calls = 0;
  const fetcher = createSessionRefreshingFetcher(
    async () => { calls += 1; return expired(); },
    async () => { refreshes += 1; },
  );
  assert.equal((await fetcher("http://localhost/ocr")).status, 401);
  assert.equal(refreshes, 1);
  assert.equal(calls, 2);
});

test("serialized tabs recheck the renewed cookie and rotate refresh only once", async () => {
  let current = false;
  let refreshes = 0;
  let last: Promise<void> = Promise.resolve();
  const withLock = async (task: () => Promise<void>) => {
    const previous = last;
    let release: () => void = () => {};
    last = new Promise<void>((resolve) => { release = resolve; });
    await previous;
    try { await task(); }
    finally { release(); }
  };
  const check = async () => current;
  const refresh = async () => { refreshes += 1; current = true; };
  await Promise.all([
    refreshSessionWithCurrentCheck(check, refresh, withLock),
    refreshSessionWithCurrentCheck(check, refresh, withLock),
  ]);
  assert.equal(refreshes, 1);
});

test("independent clients in one tab share a single refresh request", async () => {
  let refreshes = 0;
  const refresh = createSingleFlight(async () => {
    refreshes += 1;
    await new Promise((resolve) => setTimeout(resolve, 5));
  });
  await Promise.all([refresh(), refresh()]);
  assert.equal(refreshes, 1);
  await refresh();
  assert.equal(refreshes, 2);
});
