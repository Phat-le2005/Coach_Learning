import type { Role } from "../api/contracts";

export const ROLE_HOME: Record<Role, string> = {
  STUDENT: "/student",
  TEACHER: "/teacher",
  PARENT: "/parent",
  ADMIN: "/admin",
};

const PROTECTED_PREFIXES: ReadonlyArray<readonly [string, Role]> = [
  ["/student", "STUDENT"],
  ["/teacher", "TEACHER"],
  ["/parent", "PARENT"],
  ["/admin", "ADMIN"],
];

export function requiredRoleForPath(pathname: string): Role | null {
  const routePath = pathname.split(/[?#]/u, 1)[0];
  // Mobile upload endpoint is secured via HMAC QR tokens, not session cookies
  if (routePath.includes("/mobile-upload")) return null;
  return PROTECTED_PREFIXES.find(([prefix]) => routePath === prefix || routePath.startsWith(`${prefix}/`))?.[1] ?? null;
}

export function canAccessPath(role: Role, pathname: string): boolean {
  const required = requiredRoleForPath(pathname);
  return required === null || required === role;
}

export function safeReturnPath(value: string | null): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\") || /[\u0000-\u001f\u007f]/u.test(value)) return null;
  return value;
}

export function isSharedAuthenticatedPath(pathname: string): boolean {
  const route = pathname.split(/[?#]/u, 1)[0];
  // Research pages still require the development flag and session in proxy/page.
  return route === "/account" || route === "/ocr-v2-lab" || route.startsWith("/ocr-v2-lab/") || route === "/ocr-diagnostics";
}

export function postLoginPath(role: Role, requestedPath?: string | null): string {
  const safe = safeReturnPath(requestedPath ?? null);
  if (safe && isSharedAuthenticatedPath(safe)) return safe;
  return safe && requiredRoleForPath(safe) === role && canAccessPath(role, safe) ? safe : ROLE_HOME[role];
}
