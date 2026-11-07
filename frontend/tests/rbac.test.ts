import assert from "node:assert/strict";
import test from "node:test";

import { canAccessPath, isSharedAuthenticatedPath, postLoginPath, requiredRoleForPath, safeReturnPath, ROLE_HOME } from "../src/lib/auth/rbac";

test("protected dashboard prefixes map to their exact roles", () => {
  assert.equal(requiredRoleForPath("/student"), "STUDENT");
  assert.equal(requiredRoleForPath("/teacher/classes"), "TEACHER");
  assert.equal(requiredRoleForPath("/parent"), "PARENT");
  assert.equal(requiredRoleForPath("/admin/users"), "ADMIN");
  assert.equal(requiredRoleForPath("/student/attempts/123e4567-e89b-12d3-a456-426614174000/mobile-upload"), null);
});

test("RBAC denies cross-role dashboard access", () => {
  assert.equal(canAccessPath("STUDENT", "/student"), true);
  assert.equal(canAccessPath("STUDENT", "/teacher"), false);
  assert.equal(canAccessPath("ADMIN", "/admin/users"), true);
});

test("post-login redirect cannot cross role or leave the app", () => {
  assert.equal(postLoginPath("STUDENT", "/student?tab=review"), "/student?tab=review");
  assert.equal(postLoginPath("STUDENT", "/admin"), "/student");
  assert.equal(postLoginPath("TEACHER", "https://evil.example"), "/teacher");
  assert.equal(postLoginPath("STUDENT", "/login"), "/student");
  assert.equal(postLoginPath("STUDENT", "/account"), "/account");
  assert.equal(postLoginPath("STUDENT", "/ocr-v2-lab/evaluation"), "/ocr-v2-lab/evaluation");
  assert.equal(postLoginPath("STUDENT", "/api/ocr-v2-lab"), "/student");
  assert.equal(postLoginPath("ADMIN", "/account?from=menu"), "/account?from=menu");
  assert.equal(isSharedAuthenticatedPath("/account/security"), false);
  assert.equal(safeReturnPath("//evil.example"), null);
  assert.equal(safeReturnPath("/student\nmalformed"), null);
});

test("ROLE_HOME maps every canonical role to its dedicated dashboard", () => {
  assert.equal(ROLE_HOME.STUDENT, "/student");
  assert.equal(ROLE_HOME.TEACHER, "/teacher");
  assert.equal(ROLE_HOME.PARENT, "/parent");
  assert.equal(ROLE_HOME.ADMIN, "/admin");
});
