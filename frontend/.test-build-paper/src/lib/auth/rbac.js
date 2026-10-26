"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ROLE_HOME = void 0;
exports.requiredRoleForPath = requiredRoleForPath;
exports.canAccessPath = canAccessPath;
exports.safeReturnPath = safeReturnPath;
exports.isSharedAuthenticatedPath = isSharedAuthenticatedPath;
exports.postLoginPath = postLoginPath;
exports.ROLE_HOME = {
    STUDENT: "/student",
    TEACHER: "/teacher",
    PARENT: "/parent",
    ADMIN: "/admin",
};
const PROTECTED_PREFIXES = [
    ["/student", "STUDENT"],
    ["/teacher", "TEACHER"],
    ["/parent", "PARENT"],
    ["/admin", "ADMIN"],
];
function requiredRoleForPath(pathname) {
    var _a, _b;
    const routePath = pathname.split(/[?#]/u, 1)[0];
    return (_b = (_a = PROTECTED_PREFIXES.find(([prefix]) => routePath === prefix || routePath.startsWith(`${prefix}/`))) === null || _a === void 0 ? void 0 : _a[1]) !== null && _b !== void 0 ? _b : null;
}
function canAccessPath(role, pathname) {
    const required = requiredRoleForPath(pathname);
    return required === null || required === role;
}
function safeReturnPath(value) {
    if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\") || /[\u0000-\u001f\u007f]/u.test(value))
        return null;
    return value;
}
function isSharedAuthenticatedPath(pathname) {
    return pathname.split(/[?#]/u, 1)[0] === "/account";
}
function postLoginPath(role, requestedPath) {
    const safe = safeReturnPath(requestedPath !== null && requestedPath !== void 0 ? requestedPath : null);
    if (safe && isSharedAuthenticatedPath(safe))
        return safe;
    return safe && requiredRoleForPath(safe) === role && canAccessPath(role, safe) ? safe : exports.ROLE_HOME[role];
}
