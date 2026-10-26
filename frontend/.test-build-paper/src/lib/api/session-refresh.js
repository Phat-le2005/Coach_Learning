"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createSessionRefreshingFetcher = createSessionRefreshingFetcher;
exports.refreshSessionWithCurrentCheck = refreshSessionWithCurrentCheck;
exports.createSingleFlight = createSingleFlight;
/** Retry a same-origin API request once after the server reports an expired access token. */
function createSessionRefreshingFetcher(fetcher, refreshSession) {
    let refreshInFlight = null;
    return async (input, init) => {
        const response = await fetcher(input, init);
        if (response.status !== 401)
            return response;
        let code;
        try {
            const body = await response.clone().json();
            if (typeof body === "object" && body !== null && "error" in body) {
                const error = body.error;
                if (typeof error === "object" && error !== null && "code" in error) {
                    code = error.code;
                }
            }
        }
        catch (_a) {
            return response;
        }
        if (code !== "INVALID_TOKEN" && code !== "SESSION_EXPIRED")
            return response;
        if (!refreshInFlight) {
            const pending = Promise.resolve().then(refreshSession).then(() => true, () => false);
            refreshInFlight = pending;
            void pending.finally(() => {
                if (refreshInFlight === pending)
                    refreshInFlight = null;
            });
        }
        if (!(await refreshInFlight))
            return response;
        return fetcher(input, init);
    };
}
/** Recheck the HttpOnly-cookie session under a cross-tab lock before rotating refresh. */
async function refreshSessionWithCurrentCheck(isCurrent, refresh, withLock) {
    const task = async () => {
        try {
            if (await isCurrent())
                return;
        }
        catch (_a) {
            // A failed session probe still allows the refresh endpoint to decide.
        }
        await refresh();
    };
    if (withLock)
        await withLock(task);
    else
        await task();
}
/** Share one in-flight refresh across independently mounted clients in a tab. */
function createSingleFlight(task) {
    let inFlight = null;
    return () => {
        if (inFlight)
            return inFlight;
        const pending = Promise.resolve().then(task);
        inFlight = pending;
        const clear = () => { if (inFlight === pending)
            inFlight = null; };
        void pending.then(clear, clear);
        return pending;
    };
}
