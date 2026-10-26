"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.generateCsrfToken = generateCsrfToken;
exports.constantTimeEqual = constantTimeEqual;
exports.isTrustedMutationOrigin = isTrustedMutationOrigin;
function generateCsrfToken() {
    const bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}
function constantTimeEqual(left, right) {
    if (!left || !right || left.length !== right.length)
        return false;
    let result = 0;
    for (let index = 0; index < left.length; index += 1)
        result |= left.charCodeAt(index) ^ right.charCodeAt(index);
    return result === 0;
}
function isTrustedMutationOrigin(origin, expectedOrigin, fetchSite) {
    if (fetchSite === "cross-site")
        return false;
    if (!origin)
        return false;
    try {
        const originUrl = new URL(origin);
        const expectedUrl = new URL(expectedOrigin);
        if (originUrl.origin === expectedUrl.origin)
            return true;
        const isLoopback = (host) => host === "localhost" || host === "127.0.0.1";
        if (isLoopback(originUrl.hostname) && isLoopback(expectedUrl.hostname)) {
            const originPort = originUrl.port || (originUrl.protocol === "https:" ? "443" : "80");
            const expectedPort = expectedUrl.port || (expectedUrl.protocol === "https:" ? "443" : "80");
            return originPort === expectedPort && originUrl.protocol === expectedUrl.protocol;
        }
        return false;
    }
    catch (_a) {
        return false;
    }
}
