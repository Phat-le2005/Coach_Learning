"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { authenticatedMutation, BrowserAuthError, endBrowserSession } from "@/lib/auth/browser";

export function SessionHeartbeat() {
  const router = useRouter();
  useEffect(() => {
    let cancelled = false;
    let checking = false;
    async function validate() {
      if (checking) return;
      checking = true;
      try {
        const response = await fetch("/auth/me", { cache: "no-store", credentials: "same-origin" });
        if (response.status === 403) {
          await endBrowserSession();
          if (!cancelled) window.location.assign("/login?reason=expired");
          return;
        }
        if (response.status !== 401) return;
        await authenticatedMutation("/auth/refresh");
        if (!cancelled) router.refresh();
      } catch (error) {
        if (!cancelled && error instanceof BrowserAuthError && (error.status === 401 || error.status === 403)) {
          window.location.assign("/login?reason=expired");
        }
      } finally {
        checking = false;
      }
    }
    void validate();
    const onVisibility = () => { if (document.visibilityState === "visible") void validate(); };
    document.addEventListener("visibilitychange", onVisibility);
    return () => { cancelled = true; document.removeEventListener("visibilitychange", onVisibility); };
  }, [router]);
  return null;
}
