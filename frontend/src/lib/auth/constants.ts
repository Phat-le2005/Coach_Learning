export const AUTH_COOKIES = {
  access: "edums_access",
  refresh: "edums_refresh",
  session: "edums_session",
  csrf: "edums_csrf",
} as const;

export const DEFAULT_REFRESH_MAX_AGE_SECONDS = 60 * 60 * 24 * 7;
export const SESSION_VERSION = 1 as const;
