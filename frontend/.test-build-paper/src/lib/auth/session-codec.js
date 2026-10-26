"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.signSession = signSession;
exports.verifySession = verifySession;
const contracts_1 = require("../api/contracts");
const constants_1 = require("./constants");
const encoder = new TextEncoder();
const decoder = new TextDecoder();
function base64UrlEncode(bytes) {
    let binary = "";
    bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
    return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/u, "");
}
function base64UrlDecode(value) {
    const base64 = value.replaceAll("-", "+").replaceAll("_", "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
    const binary = atob(base64);
    return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}
async function hmac(secret, message) {
    const key = await crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    return new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(message)));
}
function timingSafeEqual(left, right) {
    if (left.length !== right.length)
        return false;
    let result = 0;
    for (let index = 0; index < left.length; index += 1)
        result |= left[index] ^ right[index];
    return result === 0;
}
function parsePayload(value) {
    if (typeof value !== "object" || value === null)
        return null;
    const source = value;
    if (source.v !== constants_1.SESSION_VERSION || typeof source.userId !== "string" || typeof source.email !== "string" || typeof source.fullName !== "string" || typeof source.role !== "string" || !contracts_1.ROLES.includes(source.role) || typeof source.expiresAt !== "number")
        return null;
    return source;
}
async function signSession(payload, secret) {
    if (secret.length < 32)
        throw new Error("AUTH_SESSION_SECRET must contain at least 32 characters.");
    const encodedPayload = base64UrlEncode(encoder.encode(JSON.stringify(payload)));
    const signature = base64UrlEncode(await hmac(secret, encodedPayload));
    return `${encodedPayload}.${signature}`;
}
async function verifySession(token, secret, now = Date.now()) {
    if (!token || secret.length < 32)
        return null;
    const [encodedPayload, encodedSignature, extra] = token.split(".");
    if (!encodedPayload || !encodedSignature || extra !== undefined)
        return null;
    try {
        const expected = await hmac(secret, encodedPayload);
        const actual = base64UrlDecode(encodedSignature);
        // Reject alternate, non-canonical Base64URL spellings of the same bytes.
        // Without this check, changing only unused trailing bits can leave the HMAC
        // bytes unchanged while the serialized cookie string has been tampered with.
        if (base64UrlEncode(actual) !== encodedSignature)
            return null;
        if (!timingSafeEqual(expected, actual))
            return null;
        const payload = parsePayload(JSON.parse(decoder.decode(base64UrlDecode(encodedPayload))));
        return payload && payload.expiresAt > now ? payload : null;
    }
    catch (_a) {
        return null;
    }
}
