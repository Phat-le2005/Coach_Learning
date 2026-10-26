"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SESSION_VERSION = exports.DEFAULT_REFRESH_MAX_AGE_SECONDS = exports.AUTH_COOKIES = void 0;
exports.AUTH_COOKIES = {
    access: "edums_access",
    refresh: "edums_refresh",
    session: "edums_session",
    csrf: "edums_csrf",
};
exports.DEFAULT_REFRESH_MAX_AGE_SECONDS = 60 * 60 * 24 * 7;
exports.SESSION_VERSION = 1;
