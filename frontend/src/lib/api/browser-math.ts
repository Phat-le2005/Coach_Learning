import { getCsrfToken } from "@/lib/auth/browser";

import { createApiClient } from "./client";

/** Browser calls same-origin Next routes; bearer tokens never enter the client bundle. */
export function createBrowserMathApiClient() {
  return createApiClient({
    baseUrl: typeof window === "undefined" ? "http://localhost" : window.location.origin,
    fetcher: async (input, init) => {
      const headers = new Headers(init?.headers);
      headers.delete("Authorization");
      if (init?.method && init.method !== "GET") {
        headers.set("X-CSRF-Token", await getCsrfToken());
      }
      return fetch(input, { ...init, headers, credentials: "same-origin" });
    },
  });
}
