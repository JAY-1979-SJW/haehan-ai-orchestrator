const test = require("node:test");
const assert = require("node:assert");
const { newInstanceId, classifyHealth } = require("../lib/instance_guard");

test("newInstanceId: 매번 다른 32자 hex", () => {
  const a = newInstanceId();
  assert.match(a, /^[0-9a-f]{32}$/);
  assert.notStrictEqual(a, newInstanceId());
});

test("classifyHealth: 응답 없음/비정상은 down", () => {
  assert.strictEqual(classifyHealth(null, "x"), "down");
  assert.strictEqual(classifyHealth({ ok: false, body: "" }, "x"), "down");
});

test("classifyHealth: 내 ID 와 같을 때만 own", () => {
  assert.strictEqual(classifyHealth({ ok: true, body: JSON.stringify({ instance_id: "abc" }) }, "abc"), "own");
});

test("classifyHealth: 다른 ID·ID 없음(옛 서버)·JSON 아님은 foreign — 재사용 금지", () => {
  assert.strictEqual(classifyHealth({ ok: true, body: JSON.stringify({ instance_id: "zzz" }) }, "abc"), "foreign");
  assert.strictEqual(classifyHealth({ ok: true, body: JSON.stringify({ status: "ok" }) }, "abc"), "foreign");
  assert.strictEqual(classifyHealth({ ok: true, body: JSON.stringify({ instance_id: null }) }, "abc"), "foreign");
  assert.strictEqual(classifyHealth({ ok: true, body: "<html>" }, "abc"), "foreign");
});
