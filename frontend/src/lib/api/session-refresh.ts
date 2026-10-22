/** Retry a same-origin API request once after the server reports an expired access token. */
export function createSessionRefreshingFetcher(
  fetcher: typeof fetch,
  refreshSession: () => Promise<unknown>,
): typeof fetch {
  let refreshInFlight: Promise<boolean> | null = null;

  return async (input, init) => {
    const response = await fetcher(input, init);
    if (response.status !== 401) return response;

    let code: unknown;
    try {
      const body: unknown = await response.clone().json();
      if (typeof body === "object" && body !== null && "error" in body) {
        const error = body.error;
        if (typeof error === "object" && error !== null && "code" in error) {
          code = error.code;
        }
      }
    } catch {
      return response;
    }
    if (code !== "INVALID_TOKEN" && code !== "SESSION_EXPIRED") return response;

    if (!refreshInFlight) {
      const pending = Promise.resolve().then(refreshSession).then(
        () => true,
        () => false,
      );
      refreshInFlight = pending;
      void pending.finally(() => {
        if (refreshInFlight === pending) refreshInFlight = null;
      });
    }

    if (!(await refreshInFlight)) return response;
    return fetcher(input, init);
  };
}

/** Recheck the HttpOnly-cookie session under a cross-tab lock before rotating refresh. */
export async function refreshSessionWithCurrentCheck(
  isCurrent: () => Promise<boolean>,
  refresh: () => Promise<void>,
  withLock?: (task: () => Promise<void>) => Promise<void>,
): Promise<void> {
  const task = async (): Promise<void> => {
    try {
      if (await isCurrent()) return;
    } catch {
      // A failed session probe still allows the refresh endpoint to decide.
    }
    await refresh();
  };
  if (withLock) await withLock(task);
  else await task();
}

/** Share one in-flight refresh across independently mounted clients in a tab. */
export function createSingleFlight<T>(task: () => Promise<T>): () => Promise<T> {
  let inFlight: Promise<T> | null = null;
  return () => {
    if (inFlight) return inFlight;
    const pending = Promise.resolve().then(task);
    inFlight = pending;
    const clear = () => { if (inFlight === pending) inFlight = null; };
    void pending.then(clear, clear);
    return pending;
  };
}
