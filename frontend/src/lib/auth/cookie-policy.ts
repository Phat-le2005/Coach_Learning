import { DEFAULT_REFRESH_MAX_AGE_SECONDS } from "./constants";

export interface CookiePolicyEnvironment { nodeEnv?: string; secureOverride?: string; refreshMaxAge?: string }

export function authCookiePolicy(environment: CookiePolicyEnvironment = {}) {
  const secure = environment.nodeEnv === "production" || environment.secureOverride === "true";
  const parsedRefreshAge = Number(environment.refreshMaxAge ?? DEFAULT_REFRESH_MAX_AGE_SECONDS);
  const refreshMaxAge = Number.isInteger(parsedRefreshAge) && parsedRefreshAge > 0 ? parsedRefreshAge : DEFAULT_REFRESH_MAX_AGE_SECONDS;
  return {
    base: { httpOnly: true, secure, sameSite: "lax" as const, path: "/" },
    csrf: { httpOnly: false, secure, sameSite: "strict" as const, path: "/" },
    refreshMaxAge,
  };
}
