/**
 * lib/claude_mcp.js 단위 시험 (node:test). 모든 경로는 임시 폴더 — 실제 Claude 설정은 건드리지 않는다.
 * 실행: node --test admin-web/electron/tests/claude_mcp.test.js   (pytest 래퍼: tests/test_desktop_claude_mcp.py)
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const m = require("../lib/claude_mcp");

function tmp() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "haehan-mcp-test-"));
}

function makeBundle(dir, size = 10) {
  fs.mkdirSync(path.join(dir, "_internal"), { recursive: true });
  fs.writeFileSync(path.join(dir, m.EXE_NAME), Buffer.alloc(size, 1));
  fs.writeFileSync(path.join(dir, "_internal", "lib.dll"), "dll");
  return dir;
}

const NO_CLAUDE_JSON = path.join(os.tmpdir(), "haehan-no-such-claude.json"); // 실제 ~/.claude.json 을 읽지 않게 한다
const ENV = { HAEHAN_FASTAPI_URL: "http://127.0.0.1:8401", HAEHAN_DATA_DIR: "C:\\u\\data" };

function writeCfg(dir, obj, indent = 2) {
  const p = path.join(dir, "Claude", "claude_desktop_config.json");
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, typeof obj === "string" ? obj : JSON.stringify(obj, null, indent));
  return p;
}

// ── M6 고정 경로 복사 ──────────────────────────────────────────────────────

test("번들을 userData\\mcp\\<빌드>\\ 로 복사하고 고정 exe 경로를 돌려준다", async () => {
  const root = tmp();
  const src = makeBundle(path.join(root, "res", "mcp", "haehan-mcp"));
  const userData = path.join(root, "userData");
  const r = await m.installMcpBundle({ srcDir: src, userDataDir: userData, version: "1.2.3" });
  assert.equal(r.ok, true);
  assert.equal(r.copied, true);
  assert.ok(r.exePath.startsWith(path.join(userData, "mcp")));
  assert.ok(fs.existsSync(r.exePath));
  assert.ok(fs.existsSync(path.join(path.dirname(r.exePath), "_internal", "lib.dll")), "하위 폴더도 복사");
  assert.ok(!r.exePath.startsWith(src), "리소스(임시 폴더) 경로를 등록하면 안 된다");
});

test("이미 복사돼 있으면 건너뛰고 임시 폴더 잔재가 없다", async () => {
  const root = tmp();
  const src = makeBundle(path.join(root, "src"));
  const userData = path.join(root, "ud");
  const a = await m.installMcpBundle({ srcDir: src, userDataDir: userData, version: "1.0.0" });
  const b = await m.installMcpBundle({ srcDir: src, userDataDir: userData, version: "1.0.0" });
  assert.equal(b.copied, false);
  assert.equal(a.exePath, b.exePath);
  assert.deepEqual(fs.readdirSync(path.join(userData, "mcp")).filter((n) => n.startsWith(".tmp-")), []);
});

test("같은 버전이라도 exe 가 바뀌면(크기 다름) 새 폴더로 복사된다", async () => {
  const root = tmp();
  const src = makeBundle(path.join(root, "src"), 10);
  const ud = path.join(root, "ud");
  const a = await m.installMcpBundle({ srcDir: src, userDataDir: ud, version: "1.0.0" });
  fs.writeFileSync(path.join(src, m.EXE_NAME), Buffer.alloc(99, 2));
  const b = await m.installMcpBundle({ srcDir: src, userDataDir: ud, version: "1.0.0" });
  assert.notEqual(a.exePath, b.exePath);
  assert.equal(b.copied, true);
});

test("예전 빌드 폴더는 최근 2개만 남긴다(현재 빌드 포함)", async () => {
  const root = tmp();
  const src = makeBundle(path.join(root, "src"));
  const ud = path.join(root, "ud");
  const kept = [];
  for (const v of ["1.0.0", "1.0.1", "1.0.2", "1.0.3"]) {
    const r = await m.installMcpBundle({ srcDir: src, userDataDir: ud, version: v });
    kept.push(path.dirname(r.exePath));
    // 폴더 mtime 이 같은 값으로 뭉치지 않게 시차를 둔다
    const t = new Date(Date.now() + kept.length * 2000);
    fs.utimesSync(path.dirname(r.exePath), t, t);
  }
  const left = fs.readdirSync(path.join(ud, "mcp"));
  assert.equal(left.length, 2);
  assert.ok(left.some((n) => n.startsWith("1.0.3-")), "현재 빌드는 반드시 남는다");
});

test("번들 exe 가 없으면 mcp_exe_missing", async () => {
  const root = tmp();
  fs.mkdirSync(path.join(root, "src"));
  const r = await m.installMcpBundle({ srcDir: path.join(root, "src"), userDataDir: path.join(root, "ud"), version: "1" });
  assert.equal(r.ok, false);
  assert.equal(r.error, "mcp_exe_missing");
});

// ── M1 claude_desktop_config.json ─────────────────────────────────────────

test("등록: 다른 MCP 항목과 설정을 보존하고, 백업을 남기고, 임시 파일이 없다", () => {
  const dir = tmp();
  const original = { theme: "dark", mcpServers: { other: { command: "x", args: ["a"] } }, extra: { n: 1 } };
  const cfgPath = writeCfg(dir, original);
  const before = fs.readFileSync(cfgPath, "utf-8");
  const r = m.registerClaudeDesktop({ cfgPath, exePath: "C:\\ud\\mcp\\b\\haehan-mcp.exe", env: ENV, now: new Date(2026, 9, 7, 12, 0, 0) });
  assert.equal(r.ok, true);
  assert.equal(r.changed, true);
  const after = JSON.parse(fs.readFileSync(cfgPath, "utf-8"));
  assert.deepEqual(after.mcpServers.other, original.mcpServers.other);
  assert.equal(after.theme, "dark");
  assert.deepEqual(after.extra, { n: 1 });
  assert.deepEqual(after.mcpServers[m.SERVER_NAME], { command: "C:\\ud\\mcp\\b\\haehan-mcp.exe", args: [], env: ENV });
  assert.equal(path.basename(r.backup), "claude_desktop_config.json.bak-20261007-120000");
  assert.equal(fs.readFileSync(r.backup, "utf-8"), before, "백업은 원본 그대로");
  assert.deepEqual(fs.readdirSync(path.dirname(cfgPath)).filter((n) => n.includes(".tmp-")), []);
});

test("등록: 같은 내용이면 쓰지도 백업하지도 않는다", () => {
  const dir = tmp();
  const cfgPath = writeCfg(dir, {});
  const args = { cfgPath, exePath: "E:\\x.exe", env: ENV };
  assert.equal(m.registerClaudeDesktop(args).changed, true);
  const mtime = fs.statSync(cfgPath).mtimeMs;
  const again = m.registerClaudeDesktop(args);
  assert.equal(again.ok, true);
  assert.equal(again.changed, false);
  assert.equal(fs.statSync(cfgPath).mtimeMs, mtime);
  assert.equal(fs.readdirSync(path.dirname(cfgPath)).filter((n) => n.includes(".bak-")).length, 1);
});

test("갱신: 경로가 바뀌면 같은 항목만 고치고 나머지는 보존한다", () => {
  const dir = tmp();
  const cfgPath = writeCfg(dir, { mcpServers: { other: { command: "o" }, [m.SERVER_NAME]: { command: "OLD-TEMP\\haehan-mcp.exe", args: [], env: {} } } });
  const r = m.registerClaudeDesktop({ cfgPath, exePath: "F:\\fixed\\haehan-mcp.exe", env: ENV, now: new Date(2026, 0, 1, 0, 0, 1) });
  assert.equal(r.changed, true);
  const cfg = JSON.parse(fs.readFileSync(cfgPath, "utf-8"));
  assert.equal(cfg.mcpServers[m.SERVER_NAME].command, "F:\\fixed\\haehan-mcp.exe");
  assert.deepEqual(cfg.mcpServers.other, { command: "o" });
});

test("파싱 실패: 덮어쓰지 않고(바이트 동일) 백업도 만들지 않고 안내한다", () => {
  const dir = tmp();
  const broken = '{ "mcpServers": { "a": ';
  const cfgPath = writeCfg(dir, broken);
  const r = m.registerClaudeDesktop({ cfgPath, exePath: "E:\\x.exe", env: ENV });
  assert.equal(r.ok, false);
  assert.equal(r.error, "config_parse_failed");
  assert.equal(fs.readFileSync(cfgPath, "utf-8"), broken);
  assert.equal(fs.readdirSync(path.dirname(cfgPath)).length, 1);
});

test("쓰기 도중 rename 이 실패해도 원본은 그대로이고 임시 파일이 남지 않는다(원자적)", () => {
  const dir = tmp();
  const cfgPath = writeCfg(dir, { keep: true });
  const before = fs.readFileSync(cfgPath, "utf-8");
  const real = fs.renameSync;
  fs.renameSync = () => { throw new Error("디스크 오류 시뮬레이션"); };
  let r;
  try {
    r = m.registerClaudeDesktop({ cfgPath, exePath: "E:\\x.exe", env: ENV });
  } finally {
    fs.renameSync = real;
  }
  assert.equal(r.ok, false);
  assert.equal(r.error, "config_write_failed");
  assert.equal(fs.readFileSync(cfgPath, "utf-8"), before);
  assert.deepEqual(fs.readdirSync(path.dirname(cfgPath)).filter((n) => n.includes(".tmp-")), []);
});

test("Claude Desktop 이 없으면 claude_desktop_not_found", () => {
  const dir = tmp();
  const r = m.registerClaudeDesktop({ cfgPath: path.join(dir, "Claude", "claude_desktop_config.json"), exePath: "E:\\x.exe", env: ENV });
  assert.equal(r.ok, false);
  assert.equal(r.error, "claude_desktop_not_found");
});

test("들여쓰기(4칸)를 유지한다", () => {
  const dir = tmp();
  const cfgPath = writeCfg(dir, { a: 1 }, 4);
  m.registerClaudeDesktop({ cfgPath, exePath: "E:\\x.exe", env: ENV });
  assert.match(fs.readFileSync(cfgPath, "utf-8"), /\n {4}"mcpServers"/);
});

test("해제: 우리 항목만 지우고 나머지는 보존, 백업을 남긴다", () => {
  const dir = tmp();
  const cfgPath = writeCfg(dir, { mcpServers: { other: { command: "o" }, [m.SERVER_NAME]: { command: "x" } }, keep: 1 });
  const r = m.unregisterClaudeDesktop({ cfgPath });
  assert.equal(r.changed, true);
  const cfg = JSON.parse(fs.readFileSync(cfgPath, "utf-8"));
  assert.deepEqual(Object.keys(cfg.mcpServers), ["other"]);
  assert.equal(cfg.keep, 1);
  assert.ok(fs.existsSync(r.backup));
  assert.equal(m.unregisterClaudeDesktop({ cfgPath }).changed, false);
});

test("백업은 최근 5개만 남긴다", () => {
  const dir = tmp();
  const cfgPath = writeCfg(dir, {});
  for (let i = 0; i < 8; i++) {
    m.registerClaudeDesktop({ cfgPath, exePath: `E:\\v${i}.exe`, env: ENV, now: new Date(2026, 0, 1, 0, 0, i) });
  }
  assert.equal(fs.readdirSync(path.dirname(cfgPath)).filter((n) => n.includes(".bak-")).length, 5);
});

// ── M2 Claude Code (공식 CLI) ─────────────────────────────────────────────

function fakeRun(script) {
  const calls = [];
  const run = (cmd, args, opts) => {
    calls.push({ cmd, args, opts });
    const out = script(cmd, args, calls.length);
    return { status: 0, stdout: "", stderr: "", ...out };
  };
  run.calls = calls;
  return run;
}

test("claude CLI 가 없으면 건너뛰고 안내만 한다", () => {
  const r = m.registerClaudeCode({ exePath: "E:\\x.exe", env: ENV, cli: null });
  assert.equal(r.ok, false);
  assert.equal(r.skipped, true);
  assert.equal(r.error, "claude_cli_not_found");
});

test("새로 등록: mcp get(없음) → add-json --scope user", () => {
  const run = fakeRun((cmd, args) => (args[1] === "get" ? { status: 1 } : { status: 0 }));
  const r = m.registerClaudeCode({ exePath: "E:\\fixed\\haehan-mcp.exe", env: ENV, run, cli: "/usr/bin/claude", platform: "linux", claudeJsonPath: NO_CLAUDE_JSON });
  assert.equal(r.ok, true);
  assert.equal(r.updated, false);
  const verbs = run.calls.map((c) => c.args.slice(0, 2).join(" "));
  assert.deepEqual(verbs, ["mcp get", "mcp add-json"]);
  const add = run.calls[1].args;
  assert.deepEqual(add.slice(0, 5), ["mcp", "add-json", "--scope", "user", m.SERVER_NAME]);
  const json = JSON.parse(add[5]);
  assert.equal(json.command, "E:\\fixed\\haehan-mcp.exe");
  assert.deepEqual(json.env, ENV);
});

test("이미 같은 이름이 있으면 지우고 새 경로로 다시 등록(갱신)", () => {
  const run = fakeRun(() => ({ status: 0 }));
  const r = m.registerClaudeCode({ exePath: "E:\\new.exe", env: ENV, run, cli: "claude", platform: "linux", claudeJsonPath: NO_CLAUDE_JSON });
  assert.equal(r.updated, true);
  assert.deepEqual(run.calls.map((c) => c.args[1]), ["get", "remove", "add-json"]);
  assert.deepEqual(run.calls[1].args, ["mcp", "remove", m.SERVER_NAME, "--scope", "user"]);
});

test("add 실패는 오류와 메시지를 돌려준다", () => {
  const run = fakeRun((cmd, args) => (args[1] === "get" ? { status: 1 } : { status: 2, stderr: "boom" }));
  const r = m.registerClaudeCode({ exePath: "E:\\x.exe", env: ENV, run, cli: "claude", platform: "linux" });
  assert.equal(r.ok, false);
  assert.equal(r.error, "claude_mcp_add_failed");
  assert.match(r.hint, /boom/);
});

test("Windows .cmd 는 셸 경유하되 모든 인자를 따옴표로 감싼다(공백 경로 안전)", () => {
  const run = fakeRun((cmd) => ({ status: 1 }));
  m.registerClaudeCode({ exePath: "C:\\Users\\A B\\Haehan AI\\mcp\\b\\haehan-mcp.exe", env: ENV, run, cli: "C:\\npm\\claude.cmd", platform: "win32" });
  const last = run.calls[run.calls.length - 1];
  assert.equal(last.args.shell, true); // 셸 형태는 run(문자열, 옵션) 이라 args 자리에 옵션이 온다
  assert.match(last.cmd, /^"C:\\npm\\claude\.cmd" "mcp" "add-json"/);
  assert.ok(last.cmd.includes("A B"));
});

test("해제: 없으면 변경 없음, 있으면 remove", () => {
  const none = fakeRun(() => ({ status: 1 }));
  assert.equal(m.unregisterClaudeCode({ run: none, cli: "claude", platform: "linux" }).changed, false);
  const some = fakeRun(() => ({ status: 0 }));
  assert.equal(m.unregisterClaudeCode({ run: some, cli: "claude", platform: "linux" }).changed, true);
  assert.equal(m.unregisterClaudeCode({ cli: null }).skipped, true);
});

test("findClaudeCli: where/which 결과에서 실행 파일을 고른다", () => {
  const run = fakeRun(() => ({ status: 0, stdout: "C:\\a\\claude\r\nC:\\a\\claude.cmd\r\n" }));
  assert.equal(m.findClaudeCli({ run, platform: "win32" }), "C:\\a\\claude.cmd");
  assert.equal(run.calls[0].cmd, "where");
  assert.equal(m.findClaudeCli({ run: fakeRun(() => ({ status: 1 })), platform: "linux" }), null);
});

// ── M3 env / 종합 ─────────────────────────────────────────────────────────

test("mcpEnv: 앱 주소와 데이터 폴더를 넘긴다", () => {
  const e = m.mcpEnv({ fastapiUrl: "http://127.0.0.1:9000", userDataDir: path.join("C:", "ud") });
  assert.equal(e.HAEHAN_FASTAPI_URL, "http://127.0.0.1:9000");
  assert.equal(e.HAEHAN_DATA_DIR, path.join("C:", "ud", "data"));
});

test("connectClaude: 고정 경로 복사 → Desktop 등록(env 포함) + Code 는 CLI 없어 건너뜀 → ok", async () => {
  const root = tmp();
  const src = makeBundle(path.join(root, "res"));
  const appData = path.join(root, "appData");
  writeCfg(appData, { mcpServers: { other: { command: "o" } } });
  const r = await m.connectClaude({
    srcDir: src, userDataDir: path.join(root, "ud"), version: "2.0.0", appDataDir: appData,
    fastapiUrl: "http://127.0.0.1:8401", hooks: { cli: null },
  });
  assert.equal(r.ok, true);
  assert.equal(r.code.skipped, true);
  const cfg = JSON.parse(fs.readFileSync(m.claudeDesktopConfigPath(appData), "utf-8"));
  const entry = cfg.mcpServers[m.SERVER_NAME];
  assert.equal(entry.command, r.exePath);
  assert.ok(entry.command.startsWith(path.join(root, "ud", "mcp")));
  assert.equal(entry.env.HAEHAN_FASTAPI_URL, "http://127.0.0.1:8401");
  assert.ok(cfg.mcpServers.other);
  // 해제
  const d = m.disconnectClaude({ appDataDir: appData, hooks: { cli: null } });
  assert.equal(d.ok, true);
  assert.deepEqual(Object.keys(JSON.parse(fs.readFileSync(m.claudeDesktopConfigPath(appData), "utf-8")).mcpServers), ["other"]);
});

test("connectClaude: 양쪽 다 설치되어 있지 않아도 앱이 죽지 않고 안내를 돌려준다", async () => {
  const root = tmp();
  const src = makeBundle(path.join(root, "res"));
  const r = await m.connectClaude({
    srcDir: src, userDataDir: path.join(root, "ud"), version: "1", appDataDir: path.join(root, "none"),
    fastapiUrl: "http://127.0.0.1:8401", hooks: { cli: null },
  });
  assert.equal(r.ok, false);
  assert.ok(r.hint);
});

// ── Claude Code 갱신 실패 시 복원 ─────────────────────────────────────────

function claudeJsonWith(entry) {
  const p = path.join(tmp(), ".claude.json");
  fs.writeFileSync(p, JSON.stringify({ numStartups: 3, mcpServers: { [m.SERVER_NAME]: entry, other: { command: "o" } } }));
  return p;
}

const PREV = { type: "stdio", command: "D:\old\haehan-mcp.exe", args: [], env: { HAEHAN_FASTAPI_URL: "http://127.0.0.1:8401" } };

test("갱신 중 add 가 실패하면 미리 읽어 둔 이전 등록으로 복원한다", () => {
  let addCalls = 0;
  const run = fakeRun((cmd, args) => {
    if (args[1] === "get") return { status: 0 };
    if (args[1] === "add-json") { addCalls += 1; return addCalls === 1 ? { status: 1, stderr: "새 등록 실패" } : { status: 0 }; }
    return { status: 0 };
  });
  const r = m.registerClaudeCode({ exePath: "E:\new.exe", env: ENV, run, cli: "claude", platform: "linux", claudeJsonPath: claudeJsonWith(PREV) });
  assert.equal(r.ok, false);
  assert.equal(r.restored, true);
  assert.match(r.hint, /이전 등록으로 되돌렸/);
  const adds = run.calls.filter((c) => c.args[1] === "add-json");
  assert.equal(adds.length, 2);
  assert.deepEqual(JSON.parse(adds[1].args[5]), PREV, "두 번째 add 는 이전 등록 내용 그대로");
  assert.equal(JSON.parse(adds[0].args[5]).command, "E:\new.exe");
});

test("add 와 복원이 모두 실패하면 수동 복구 명령을 안내한다", () => {
  const run = fakeRun((cmd, args) => (args[1] === "get" ? { status: 0 } : args[1] === "remove" ? { status: 0 } : { status: 1, stderr: "denied" }));
  const r = m.registerClaudeCode({ exePath: "E:\new.exe", env: ENV, run, cli: "claude", platform: "linux", claudeJsonPath: claudeJsonWith(PREV) });
  assert.equal(r.ok, false);
  assert.equal(r.restored, false);
  assert.equal(r.error, "claude_mcp_restore_failed");
  assert.match(r.hint, /직접 복구/);
  assert.ok(r.hint.includes("D:\old\haehan-mcp.exe"), "이전 경로가 안내에 들어 있다");
});

test("이전 등록을 읽을 수 없고 add 가 실패하면 다시 연결하라고 안내한다(조용히 사라지지 않는다)", () => {
  const run = fakeRun((cmd, args) => (args[1] === "get" || args[1] === "remove" ? { status: 0 } : { status: 1, stderr: "x" }));
  const r = m.registerClaudeCode({ exePath: "E:\new.exe", env: ENV, run, cli: "claude", platform: "linux", claudeJsonPath: NO_CLAUDE_JSON });
  assert.equal(r.ok, false);
  assert.equal(r.error, "claude_mcp_restore_failed");
  assert.match(r.hint, /Claude 연결/);
});

test("새 등록(기존 없음)이 실패해도 remove 는 부르지 않는다", () => {
  const run = fakeRun((cmd, args) => (args[1] === "get" ? { status: 1 } : { status: 1, stderr: "x" }));
  const r = m.registerClaudeCode({ exePath: "E:\new.exe", env: ENV, run, cli: "claude", platform: "linux", claudeJsonPath: NO_CLAUDE_JSON });
  assert.equal(r.error, "claude_mcp_add_failed");
  assert.ok(!run.calls.some((c) => c.args[1] === "remove"));
});

// ── 빌드 버전(build-info.json) ────────────────────────────────────────────

test("build-info.json 의 version(yyyymmdd-sha7)을 폴더 이름으로 쓴다", async () => {
  const root = tmp();
  const res = path.join(root, "resources");
  fs.mkdirSync(res);
  fs.writeFileSync(path.join(res, "build-info.json"), JSON.stringify({ version: "20261007-abc1234" }));
  const src = makeBundle(path.join(root, "src"));
  const bv = m.readBuildVersion(res);
  assert.equal(bv, "20261007-abc1234");
  const r = await m.installMcpBundle({ srcDir: src, userDataDir: path.join(root, "ud"), version: "1.0.0", buildVersion: bv });
  assert.equal(path.basename(path.dirname(r.exePath)), "20261007-abc1234");
});

test("version 이 없어도 git_sha·build_time 으로 만들고, 없거나 이상하면 null(앱버전-크기로 대체)", async () => {
  const res = tmp();
  fs.writeFileSync(path.join(res, "build-info.json"), JSON.stringify({ git_sha: "ABCDEF1234567", build_time: "2026-10-07T01:02:03Z" }));
  assert.equal(m.readBuildVersion(res), "20261007-abcdef1");
  fs.writeFileSync(path.join(res, "build-info.json"), JSON.stringify({ version: "bad", git_sha: "zz", build_time: "x" }));
  assert.equal(m.readBuildVersion(res), null);
  assert.equal(m.readBuildVersion(path.join(res, "없음")), null);
  const root = tmp();
  const src = makeBundle(path.join(root, "src"), 10);
  const r = await m.installMcpBundle({ srcDir: src, userDataDir: path.join(root, "ud"), version: "1.0.0", buildVersion: null });
  assert.equal(path.basename(path.dirname(r.exePath)), "1.0.0-10");
});
