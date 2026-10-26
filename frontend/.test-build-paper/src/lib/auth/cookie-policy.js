"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.authCookiePolicy = authCookiePolicy;
const constants_1 = require("./constants");
function authCookiePolicy(environment = {}) {
    var _a;
    const secure = environment.nodeEnv === "production" || environment.secureOverride === "true";
    const parsedRefreshAge = Number((_a = environment.refreshMaxAge) !== null && _a !== void 0 ? _a : constants_1.DEFAULT_REFRESH_MAX_AGE_SECONDS);
    const refreshMaxAge = Number.isInteger(parsedRefreshAge) && parsedRefreshAge > 0 ? parsedRefreshAge : constants_1.DEFAULT_REFRESH_MAX_AGE_SECONDS;
    return {
        base: { httpOnly: true, secure, sameSite: "lax", path: "/" },
        csrf: { httpOnly: false, secure, sameSite: "strict", path: "/" },
        refreshMaxAge,
    };
}
