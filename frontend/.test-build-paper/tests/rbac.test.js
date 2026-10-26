"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const rbac_1 = require("../src/lib/auth/rbac");
(0, node_test_1.default)("protected dashboard prefixes map to their exact roles", () => {
    strict_1.default.equal((0, rbac_1.requiredRoleForPath)("/student"), "STUDENT");
    strict_1.default.equal((0, rbac_1.requiredRoleForPath)("/teacher/classes"), "TEACHER");
    strict_1.default.equal((0, rbac_1.requiredRoleForPath)("/parent"), "PARENT");
    strict_1.default.equal((0, rbac_1.requiredRoleForPath)("/admin/users"), "ADMIN");
});
(0, node_test_1.default)("RBAC denies cross-role dashboard access", () => {
    strict_1.default.equal((0, rbac_1.canAccessPath)("STUDENT", "/student"), true);
    strict_1.default.equal((0, rbac_1.canAccessPath)("STUDENT", "/teacher"), false);
    strict_1.default.equal((0, rbac_1.canAccessPath)("ADMIN", "/admin/users"), true);
});
(0, node_test_1.default)("post-login redirect cannot cross role or leave the app", () => {
    strict_1.default.equal((0, rbac_1.postLoginPath)("STUDENT", "/student?tab=review"), "/student?tab=review");
    strict_1.default.equal((0, rbac_1.postLoginPath)("STUDENT", "/admin"), "/student");
    strict_1.default.equal((0, rbac_1.postLoginPath)("TEACHER", "https://evil.example"), "/teacher");
    strict_1.default.equal((0, rbac_1.postLoginPath)("STUDENT", "/login"), "/student");
    strict_1.default.equal((0, rbac_1.postLoginPath)("STUDENT", "/account"), "/account");
    strict_1.default.equal((0, rbac_1.postLoginPath)("ADMIN", "/account?from=menu"), "/account?from=menu");
    strict_1.default.equal((0, rbac_1.isSharedAuthenticatedPath)("/account/security"), false);
    strict_1.default.equal((0, rbac_1.safeReturnPath)("//evil.example"), null);
    strict_1.default.equal((0, rbac_1.safeReturnPath)("/student\nmalformed"), null);
});
(0, node_test_1.default)("ROLE_HOME maps every canonical role to its dedicated dashboard", () => {
    strict_1.default.equal(rbac_1.ROLE_HOME.STUDENT, "/student");
    strict_1.default.equal(rbac_1.ROLE_HOME.TEACHER, "/teacher");
    strict_1.default.equal(rbac_1.ROLE_HOME.PARENT, "/parent");
    strict_1.default.equal(rbac_1.ROLE_HOME.ADMIN, "/admin");
});
