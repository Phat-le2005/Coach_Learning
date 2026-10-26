"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.mathWorkspaceProxyPath = mathWorkspaceProxyPath;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** Restrict the browser BFF to the exact Math Workspace operations it needs. */
function mathWorkspaceProxyPath(parts, method) {
    var _a, _b, _c;
    if (!UUID.test((_a = parts[0]) !== null && _a !== void 0 ? _a : ""))
        return null;
    const tail = parts.slice(1).join("/");
    const allowed = (method === "GET" && ["", "problem", "ink"].includes(tail)) ||
        (method === "GET" && /^ink\/pages\/(?:[0-9]|[12][0-9])$/.test(tail)) ||
        (method === "PUT" && /^ink\/pages\/(?:[0-9]|[12][0-9])$/.test(tail)) ||
        (method === "POST" && ["ocr/recognize", "steps", "submit"].includes(tail)) ||
        (method === "PATCH" && parts.length === 3 && parts[1] === "steps" && UUID.test((_b = parts[2]) !== null && _b !== void 0 ? _b : "")) ||
        (method === "POST" && parts.length === 4 && parts[1] === "steps"
            && UUID.test((_c = parts[2]) !== null && _c !== void 0 ? _c : "") && parts[3] === "delete");
    return allowed ? `/api/v2/math-solutions/attempts/${parts.join("/")}` : null;
}
