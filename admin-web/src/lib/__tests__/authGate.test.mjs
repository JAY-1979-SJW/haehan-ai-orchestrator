// 실행: node --test admin-web/src/lib/__tests__/authGate.test.mjs  (Node 22.6+ 타입 제거 실행)
import test from "node:test";
import assert from "node:assert/strict";
import { isApiRequestPath, unauthenticatedAction } from "../authGate.ts";

test("API 경로 판별", () => {
  assert.equal(isApiRequestPath("/api/proxy/api/v1/users/me"), true);
  assert.equal(isApiRequestPath("/api"), true);
  assert.equal(isApiRequestPath("/apiary"), false);
  assert.equal(isApiRequestPath("/mypage"), false);
});

test("로그인 안 된 /api 요청은 HTML 이동이 아니라 401 JSON", () => {
  for (const desktop of [true, false]) {
    const a = unauthenticatedAction("/api/proxy/api/v1/users/me", desktop);
    assert.equal(a.kind, "json401");
    assert.equal(typeof a.body.detail, "string");
  }
});

test("로그인 안 된 화면 요청은 데스크톱 /setup, 웹 /login 으로 이동", () => {
  assert.deepEqual(unauthenticatedAction("/mypage", true), { kind: "redirect", to: "/setup" });
  assert.deepEqual(unauthenticatedAction("/mypage", false), { kind: "redirect", to: "/login" });
});
