"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ApiContractError = void 0;
exports.record = record;
exports.string = string;
exports.nonEmptyString = nonEmptyString;
exports.number = number;
exports.integer = integer;
exports.boolean = boolean;
exports.array = array;
exports.nullable = nullable;
exports.optional = optional;
exports.oneOf = oneOf;
class ApiContractError extends Error {
    constructor(message, path = "response") {
        super(`${message} (${path})`);
        this.path = path;
        this.name = "ApiContractError";
    }
}
exports.ApiContractError = ApiContractError;
function record(value, path) {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
        throw new ApiContractError("Expected an object", path);
    }
    return value;
}
function string(value, path) {
    if (typeof value !== "string")
        throw new ApiContractError("Expected a string", path);
    return value;
}
function nonEmptyString(value, path) {
    const result = string(value, path);
    if (!result.trim())
        throw new ApiContractError("Expected a non-empty string", path);
    return result;
}
function number(value, path) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
        throw new ApiContractError("Expected a finite number", path);
    }
    return value;
}
function integer(value, path) {
    const result = number(value, path);
    if (!Number.isInteger(result))
        throw new ApiContractError("Expected an integer", path);
    return result;
}
function boolean(value, path) {
    if (typeof value !== "boolean")
        throw new ApiContractError("Expected a boolean", path);
    return value;
}
function array(value, path, parse) {
    if (!Array.isArray(value))
        throw new ApiContractError("Expected an array", path);
    return value.map((item, index) => parse(item, `${path}[${index}]`));
}
function nullable(value, path, parse) {
    return value === null ? null : parse(value, path);
}
function optional(value, path, parse) {
    return value === undefined ? undefined : parse(value, path);
}
function oneOf(value, path, values) {
    const parsed = string(value, path);
    if (!values.includes(parsed))
        throw new ApiContractError(`Expected one of: ${values.join(", ")}`, path);
    return parsed;
}
