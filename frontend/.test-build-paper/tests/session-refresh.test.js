"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const session_refresh_js_1 = require("../src/lib/api/session-refresh.js");
const expired = () => Response.json({ error: { code: "INVALID_TOKEN", message: "Invalid or expired token." } }, { status: 401 });
(0, node_test_1.default)("expired Math Workspace access token refreshes and retries the original request once", async () => {
    let calls = 0;
    let refreshes = 0;
    const body = JSON.stringify({ page_index: 0, stroke_ids: ["stroke-id"] });
    const fetcher = (0, session_refresh_js_1.createSessionRefreshingFetcher)(async (_input, init) => {
        calls += 1;
        strict_1.default.equal(init === null || init === void 0 ? void 0 : init.method, "POST");
        strict_1.default.equal(init === null || init === void 0 ? void 0 : init.body, body);
        return calls === 1 ? expired() : Response.json({ latex: "x^2" });
    }, async () => { refreshes += 1; });
    const response = await fetcher("http://localhost/api/v2/math-solutions/attempts/id/ocr/recognize", { method: "POST", body });
    strict_1.default.equal(response.status, 200);
    strict_1.default.equal(calls, 2);
    strict_1.default.equal(refreshes, 1);
});
(0, node_test_1.default)("concurrent expired requests share one rotating refresh token", async () => {
    let calls = 0;
    let refreshes = 0;
    const fetcher = (0, session_refresh_js_1.createSessionRefreshingFetcher)(async () => {
        calls += 1;
        return calls <= 2 ? expired() : Response.json({ ok: true });
    }, async () => {
        refreshes += 1;
        await new Promise((resolve) => setTimeout(resolve, 5));
    });
    const responses = await Promise.all([fetcher("http://localhost/one"), fetcher("http://localhost/two")]);
    strict_1.default.deepEqual(responses.map((response) => response.status), [200, 200]);
    strict_1.default.equal(refreshes, 1);
    strict_1.default.equal(calls, 4);
});
(0, node_test_1.default)("failed refresh keeps the original 401 and does not retry the mutation", async () => {
    let calls = 0;
    const fetcher = (0, session_refresh_js_1.createSessionRefreshingFetcher)(async () => { calls += 1; return expired(); }, async () => { throw new Error("Refresh expired"); });
    const response = await fetcher("http://localhost/ocr", { method: "POST" });
    strict_1.default.equal(response.status, 401);
    strict_1.default.equal((await response.json()).error.code, "INVALID_TOKEN");
    strict_1.default.equal(calls, 1);
});
(0, node_test_1.default)("other 401 errors and successful responses do not rotate the refresh token", async () => {
    let refreshes = 0;
    const refresh = async () => { refreshes += 1; };
    const forbidden = (0, session_refresh_js_1.createSessionRefreshingFetcher)(async () => Response.json({ error: { code: "FORBIDDEN" } }, { status: 401 }), refresh);
    const success = (0, session_refresh_js_1.createSessionRefreshingFetcher)(async () => Response.json({ ok: true }), refresh);
    strict_1.default.equal((await forbidden("http://localhost/ocr")).status, 401);
    strict_1.default.equal((await success("http://localhost/ocr")).status, 200);
    strict_1.default.equal(refreshes, 0);
});
(0, node_test_1.default)("a second 401 after refresh is returned without another refresh loop", async () => {
    let refreshes = 0;
    let calls = 0;
    const fetcher = (0, session_refresh_js_1.createSessionRefreshingFetcher)(async () => { calls += 1; return expired(); }, async () => { refreshes += 1; });
    strict_1.default.equal((await fetcher("http://localhost/ocr")).status, 401);
    strict_1.default.equal(refreshes, 1);
    strict_1.default.equal(calls, 2);
});
(0, node_test_1.default)("serialized tabs recheck the renewed cookie and rotate refresh only once", async () => {
    let current = false;
    let refreshes = 0;
    let last = Promise.resolve();
    const withLock = async (task) => {
        const previous = last;
        let release = () => { };
        last = new Promise((resolve) => { release = resolve; });
        await previous;
        try {
            await task();
        }
        finally {
            release();
        }
    };
    const check = async () => current;
    const refresh = async () => { refreshes += 1; current = true; };
    await Promise.all([
        (0, session_refresh_js_1.refreshSessionWithCurrentCheck)(check, refresh, withLock),
        (0, session_refresh_js_1.refreshSessionWithCurrentCheck)(check, refresh, withLock),
    ]);
    strict_1.default.equal(refreshes, 1);
});
(0, node_test_1.default)("independent clients in one tab share a single refresh request", async () => {
    let refreshes = 0;
    const refresh = (0, session_refresh_js_1.createSingleFlight)(async () => {
        refreshes += 1;
        await new Promise((resolve) => setTimeout(resolve, 5));
    });
    await Promise.all([refresh(), refresh()]);
    strict_1.default.equal(refreshes, 1);
    await refresh();
    strict_1.default.equal(refreshes, 2);
});
