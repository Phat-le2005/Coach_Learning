import { getCsrfToken, refreshBrowserSession } from "@/lib/auth/browser";

import { createApiClient } from "./client";
import { createSessionRefreshingFetcher } from "./session-refresh";

/** Browser calls same-origin Next routes; bearer tokens never enter the client bundle. */
export function createBrowserMathApiClient() {
  const browserFetcher: typeof fetch = async (input, init) => {
    const headers = new Headers(init?.headers);
    headers.delete("Authorization");
    headers.set("X-EduMS-BFF", "1");
    if (init?.method && init.method !== "GET") {
      headers.set("X-CSRF-Token", await getCsrfToken());
    }
    return fetch(input, { ...init, headers, credentials: "same-origin" });
  };
  return createApiClient({
    baseUrl: typeof window === "undefined" ? "http://localhost" : window.location.origin,
    fetcher: createSessionRefreshingFetcher(browserFetcher, refreshBrowserSession),
  });
}
