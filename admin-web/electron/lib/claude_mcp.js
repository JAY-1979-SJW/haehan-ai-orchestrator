/**
 * lib/claude_mcp.js — 사용자 PC 의 Claude(데스크톱·Code)에 이 앱의 MCP 서버(haehan-mcp.exe)를 연결한다.
 * L10 Local PC App 계층. 파일·프로세스 IO 만 담당하고 업무 로직은 없다.
 *
 * 설계 요점
 *  - 포터블(electron-builder portable) 타깃은 실행마다 TEMP 아래 폴더로 리소스를 풀기 때문에
 *    process.resourcesPath 안의 exe 경로를 Claude 설정에 적으면 앱 종료 뒤 경로가 사라질 수 있다(M6).
 *    그래서 번들 폴더를 userData\mcp\<빌드>\ 로 복사하고 **그 고정 경로**를 등록한다.
 *  - claude_desktop_config.json 은 백업(.bak-<시각>) 후 tmp+rename 으로만 쓰고, 다른 MCP 항목·설정은 보존한다(M1).
 *    파싱에 실패하면 덮어쓰지 않는다.
 *  - Claude Code 는 사용자 설정 파일을 직접 고치지 않고 공식 CLI(`claude mcp ...`)로 등록한다(M2).
 *  - 등록 env 로 앱 주소(HAEHAN_FASTAPI_URL)와 데이터 폴더를 넘긴다(M3).
 *
 * 모든 함수는 경로·실행기를 인자로 받아 임시 폴더로 시험할 수 있다(electron 을 import 하지 않는다).
 */
const fs = require("fs");
const fsp = require("fs/promises");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const SERVER_NAME = "haehan-orchestrator";
const EXE_NAME = "haehan-mcp.exe";
const KEEP_VERSIONS = 2;
const KEEP_BACKUPS = 5;

// ── 번들 복사 (M6) ───────────────────────────────────────────────────────────

const BUILD_VERSION_RE = /^\d{8}-[0-9a-f]{7}$/;

/**
 * 빌드 정보(resources/build-info.json)에서 빌드 버전(yyyymmdd-sha7)을 읽는다. 없거나 형식이 다르면 null.
 * `version` 필드가 있으면 그것을, 없으면 git_sha·build_time 으로 만든다.
 */
function readBuildVersion(resourcesPath) {
  try {
    const info = JSON.parse(fs.readFileSync(path.join(resourcesPath, "build-info.json"), "utf-8").replace(/^﻿/, ""));
    if (typeof info.version === "string" && BUILD_VERSION_RE.test(info.version)) return info.version;
    const sha = String(info.git_sha || "").slice(0, 7).toLowerCase();
    const day = String(info.build_time || "").replace(/\D/g, "").slice(0, 8);
    const derived = `${day}-${sha}`;
    return BUILD_VERSION_RE.test(derived) ? derived : null;
  } catch {
    return null;
  }
}

/**
 * 빌드 식별자(고정 경로 폴더 이름). build-info 의 빌드 버전(yyyymmdd-sha7)이 있으면 그것을 쓰고,
 * 없으면 앱 버전 + exe 크기(같은 버전을 다시 빌드해 exe 가 바뀌어도 새 폴더로 복사되게 한다).
 */
function buildId(srcDir, version, buildVersion = null) {
  if (buildVersion && BUILD_VERSION_RE.test(buildVersion)) return buildVersion;
  let size = 0;
  try { size = fs.statSync(path.join(srcDir, EXE_NAME)).size; } catch { /* 없으면 0 — 호출부가 mcp_exe_missing 처리 */ }
  return `${String(version).replace(/[^0-9A-Za-z._-]/g, "_")}-${size}`;
}

async function pathExists(p) {
  try { await fsp.access(p); return true; } catch { return false; }
}

/**
 * srcDir(번들 haehan-mcp 폴더)을 <userDataDir>\mcp\<빌드>\ 로 복사하고 고정 exe 경로를 돌려준다.
 * 이미 있으면 건너뛴다. 복사는 임시 폴더에 한 뒤 rename 으로 확정해(원자적) 중간에 끊겨도 반쯤 복사된 폴더가 남지 않는다.
 * 예전 빌드 폴더는 최근 KEEP_VERSIONS 개만 남긴다.
 */
async function installMcpBundle({ srcDir, userDataDir, version, buildVersion = null, keep = KEEP_VERSIONS }) {
  const srcExe = path.join(srcDir, EXE_NAME);
  if (!(await pathExists(srcExe))) return { ok: false, error: "mcp_exe_missing", hint: srcExe };

  const root = path.join(userDataDir, "mcp");
  const id = buildId(srcDir, version, buildVersion);
  const dest = path.join(root, id);
  const destExe = path.join(dest, EXE_NAME);
  let copied = false;

  await fsp.mkdir(root, { recursive: true });
  if (!(await pathExists(destExe))) {
    const tmp = path.join(root, `.tmp-${id}-${process.pid}-${Date.now()}`);
    try {
      await fsp.cp(srcDir, tmp, { recursive: true });
      try {
        await fsp.rename(tmp, dest);
        copied = true;
      } catch (e) {
        // 다른 프로세스가 먼저 확정했으면 그 결과를 쓴다
        if (!(await pathExists(destExe))) throw e;
      }
    } catch (e) {
      return { ok: false, error: "mcp_copy_failed", hint: String(e && e.message ? e.message : e) };
    } finally {
      await fsp.rm(tmp, { recursive: true, force: true }).catch(() => {});
    }
  }
  await pruneOldBuilds(root, id, keep);
  return { ok: true, exePath: destExe, buildId: id, copied };
}

async function pruneOldBuilds(root, currentId, keep) {
  let entries = [];
  try { entries = await fsp.readdir(root, { withFileTypes: true }); } catch { return; }
  const builds = [];
  for (const ent of entries) {
    if (!ent.isDirectory()) continue;
    const full = path.join(root, ent.name);
    if (ent.name.startsWith(".tmp-")) {
      // 오래된(1시간 이상) 중단 잔재만 정리 — 다른 프로세스가 복사 중일 수 있다
      const st = await fsp.stat(full).catch(() => null);
      if (st && Date.now() - st.mtimeMs > 3600 * 1000) await fsp.rm(full, { recursive: true, force: true }).catch(() => {});
      continue;
    }
    const st = await fsp.stat(full).catch(() => null);
    if (st) builds.push({ name: ent.name, full, mtime: st.mtimeMs });
  }
  builds.sort((a, b) => (b.name === currentId) - (a.name === currentId) || b.mtime - a.mtime);
  for (const old of builds.slice(Math.max(1, keep))) {
    await fsp.rm(old.full, { recursive: true, force: true }).catch(() => {});
  }
}

// ── Claude Desktop (M1) ──────────────────────────────────────────────────────

function claudeDesktopConfigPath(appDataDir) {
  return path.join(appDataDir, "Claude", "claude_desktop_config.json");
}

function stamp(d = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function detectIndent(raw) {
  const m = raw.match(/^([ \t]+)"/m);
  return m ? m[1] : "  ";
}

/** 임시 파일에 쓴 뒤 rename — 쓰는 도중 끊겨도 원본이 깨지지 않는다. */
function writeAtomic(filePath, text) {
  const tmp = `${filePath}.tmp-${process.pid}-${Date.now()}`;
  try {
    fs.writeFileSync(tmp, text, "utf-8");
    fs.renameSync(tmp, filePath);
  } catch (e) {
    try { fs.rmSync(tmp, { force: true }); } catch { /* 무시 */ }
    throw e;
  }
}

function backupFile(cfgPath, now) {
  const bak = `${cfgPath}.bak-${stamp(now)}`;
  fs.copyFileSync(cfgPath, bak);
  // 백업은 최근 KEEP_BACKUPS 개만 남긴다
  try {
    const dir = path.dirname(cfgPath);
    const base = path.basename(cfgPath) + ".bak-";
    const baks = fs.readdirSync(dir).filter((f) => f.startsWith(base)).sort();
    for (const f of baks.slice(0, Math.max(0, baks.length - KEEP_BACKUPS))) fs.rmSync(path.join(dir, f), { force: true });
  } catch { /* 정리 실패는 무시 */ }
  return bak;
}

function readDesktopConfig(cfgPath) {
  if (!fs.existsSync(cfgPath)) return { ok: false, error: "claude_desktop_not_found", hint: "Claude Desktop을 먼저 설치·실행하세요" };
  let raw;
  try {
    raw = fs.readFileSync(cfgPath, "utf-8").replace(/^﻿/, "");
  } catch (e) {
    return { ok: false, error: "config_read_failed", hint: String(e) };
  }
  if (!raw.trim()) return { ok: true, cfg: {}, indent: "  ", raw };
  try {
    const cfg = JSON.parse(raw);
    if (cfg === null || typeof cfg !== "object" || Array.isArray(cfg)) throw new Error("최상위가 객체가 아닙니다");
    return { ok: true, cfg, indent: detectIndent(raw), raw };
  } catch (e) {
    // 덮어쓰지 않는다 — 사용자의 설정 파일을 망가뜨리지 않기 위해 안내만 한다
    return { ok: false, error: "config_parse_failed", hint: `claude_desktop_config.json 을 읽을 수 없어 건드리지 않았습니다: ${e.message}` };
  }
}

/** Claude Desktop 설정에 haehan-orchestrator 항목을 등록·갱신한다. 같은 내용이면 쓰지 않는다. */
function registerClaudeDesktop({ cfgPath, exePath, env, now = new Date() }) {
  const read = readDesktopConfig(cfgPath);
  if (!read.ok) return read;
  const { cfg, indent } = read;
  const entry = { command: exePath, args: [], env: { ...env } };
  const servers = cfg.mcpServers && typeof cfg.mcpServers === "object" && !Array.isArray(cfg.mcpServers) ? cfg.mcpServers : {};
  if (JSON.stringify(servers[SERVER_NAME]) === JSON.stringify(entry)) {
    return { ok: true, changed: false, hint: "이미 연결되어 있습니다" };
  }
  const bak = fs.existsSync(cfgPath) && read.raw.trim() ? backupFile(cfgPath, now) : null;
  cfg.mcpServers = { ...servers, [SERVER_NAME]: entry };
  try {
    writeAtomic(cfgPath, JSON.stringify(cfg, null, indent) + "\n");
  } catch (e) {
    return { ok: false, error: "config_write_failed", hint: String(e) };
  }
  return { ok: true, changed: true, backup: bak, hint: "Claude Desktop을 재시작하면 적용됩니다" };
}

function unregisterClaudeDesktop({ cfgPath, now = new Date() }) {
  const read = readDesktopConfig(cfgPath);
  if (!read.ok) return read;
  const { cfg, indent } = read;
  if (!cfg.mcpServers || !(SERVER_NAME in cfg.mcpServers)) return { ok: true, changed: false, hint: "연결되어 있지 않습니다" };
  const bak = backupFile(cfgPath, now);
  const next = { ...cfg.mcpServers };
  delete next[SERVER_NAME];
  cfg.mcpServers = next;
  try {
    writeAtomic(cfgPath, JSON.stringify(cfg, null, indent) + "\n");
  } catch (e) {
    return { ok: false, error: "config_write_failed", hint: String(e) };
  }
  return { ok: true, changed: true, backup: bak, hint: "Claude Desktop을 재시작하면 적용됩니다" };
}

function desktopStatus({ cfgPath, exePath }) {
  const read = readDesktopConfig(cfgPath);
  if (!read.ok) return { installed: read.error !== "claude_desktop_not_found", connected: false, error: read.error };
  const e = read.cfg.mcpServers && read.cfg.mcpServers[SERVER_NAME];
  return { installed: true, connected: !!e, current: !!e && (!exePath || e.command === exePath) };
}

// ── Claude Code (M2) — 공식 CLI 로 등록 ─────────────────────────────────────

/** 실행 파일 위치 탐색(Windows: where, 그 밖: which). 없으면 null. */
function findClaudeCli({ run = spawnSync, platform = process.platform } = {}) {
  const finder = platform === "win32" ? "where" : "which";
  const r = run(finder, ["claude"], { encoding: "utf-8", windowsHide: true });
  if (!r || r.status !== 0 || !r.stdout) return null;
  const lines = String(r.stdout).split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  // Windows 는 확장자 있는 항목(.exe/.cmd)을 우선한다
  return lines.find((l) => /\.(exe|cmd|bat)$/i.test(l)) || lines[0] || null;
}

function runClaude(cli, args, { run = spawnSync, platform = process.platform } = {}) {
  const needsShell = platform === "win32" && /\.(cmd|bat)$/i.test(cli);
  if (!needsShell) return run(cli, args, { encoding: "utf-8", windowsHide: true, timeout: 60000 });
  // .cmd 는 셸 경유가 필요하다 — 모든 인자를 큰따옴표로 감싸고 내부 큰따옴표는 \" 로 이스케이프한다
  const q = (s) => `"${String(s).replace(/"/g, '\\"')}"`;
  return run(`${q(cli)} ${args.map(q).join(" ")}`, { encoding: "utf-8", windowsHide: true, timeout: 60000, shell: true });
}

/** Claude Code 사용자 범위 등록 정보를 읽어 둔다(~/.claude.json 의 mcpServers — 읽기 전용). 없으면 null. */
function readExistingClaudeCodeEntry(claudeJsonPath) {
  try {
    const raw = JSON.parse(fs.readFileSync(claudeJsonPath, "utf-8").replace(/^﻿/, ""));
    const entry = raw && raw.mcpServers && raw.mcpServers[SERVER_NAME];
    return entry && typeof entry === "object" ? entry : null;
  } catch {
    return null;
  }
}

/**
 * Claude Code 에 사용자 범위로 등록한다. 같은 이름이 이미 있으면 지우고 새 경로로 다시 등록한다.
 * 지운 뒤 add 가 실패하면 미리 읽어 둔 이전 등록으로 되돌린다(기존 연결이 사라진 채 남지 않게).
 * 되돌리기까지 실패하면 수동 복구 명령을 안내한다. claude CLI 가 없으면 건너뛰고 안내만 한다.
 */
function registerClaudeCode({
  exePath, env, run = spawnSync, platform = process.platform, cli = undefined,
  claudeJsonPath = path.join(os.homedir(), ".claude.json"),
}) {
  const bin = cli === undefined ? findClaudeCli({ run, platform }) : cli;
  if (!bin) return { ok: false, skipped: true, error: "claude_cli_not_found", hint: "Claude Code(claude 명령)를 찾지 못해 건너뜁니다. 설치 후 'Claude 연결'을 다시 실행하세요" };
  const opts = { run, platform };
  const existing = runClaude(bin, ["mcp", "get", SERVER_NAME], opts);
  const existed = !!existing && existing.status === 0;
  const previous = existed ? readExistingClaudeCodeEntry(claudeJsonPath) : null;
  const addArgs = (obj) => ["mcp", "add-json", "--scope", "user", SERVER_NAME, JSON.stringify(obj)];
  if (existed) runClaude(bin, ["mcp", "remove", SERVER_NAME, "--scope", "user"], opts);
  const added = runClaude(bin, addArgs({ type: "stdio", command: exePath, args: [], env: { ...env } }), opts);
  if (added && added.status === 0) {
    return { ok: true, changed: true, updated: existed, hint: "새 Claude Code 세션부터 적용됩니다" };
  }
  const why = String((added && (added.stderr || added.stdout)) || "claude mcp add-json 실패").slice(0, 300);
  if (!existed) return { ok: false, error: "claude_mcp_add_failed", hint: why };
  // 갱신 중 실패 — 이전 등록으로 복원한다
  if (previous) {
    const restored = runClaude(bin, addArgs(previous), opts);
    if (restored && restored.status === 0) {
      return { ok: false, restored: true, error: "claude_mcp_add_failed", hint: `Claude Code 연결을 갱신하지 못해 이전 등록으로 되돌렸습니다: ${why}` };
    }
  }
  const manual = previous ? `claude mcp add-json --scope user ${SERVER_NAME} '${JSON.stringify(previous)}'` : `'Claude 연결'을 다시 실행하거나 claude mcp add-json --scope user ${SERVER_NAME} '<json>'`;
  return {
    ok: false,
    restored: false,
    error: "claude_mcp_restore_failed",
    hint: `Claude Code 연결 갱신에 실패했고 이전 등록도 복원하지 못했습니다(${why}). 다음으로 직접 복구하세요: ${manual}`,
  };
}

function unregisterClaudeCode({ run = spawnSync, platform = process.platform, cli = undefined }) {
  const bin = cli === undefined ? findClaudeCli({ run, platform }) : cli;
  if (!bin) return { ok: true, skipped: true, hint: "claude 명령이 없어 건너뜁니다" };
  const opts = { run, platform };
  const existing = runClaude(bin, ["mcp", "get", SERVER_NAME], opts);
  if (!existing || existing.status !== 0) return { ok: true, changed: false, hint: "연결되어 있지 않습니다" };
  const r = runClaude(bin, ["mcp", "remove", SERVER_NAME, "--scope", "user"], opts);
  return r && r.status === 0 ? { ok: true, changed: true } : { ok: false, error: "claude_mcp_remove_failed", hint: String((r && r.stderr) || "").slice(0, 300) };
}

function codeStatus({ run = spawnSync, platform = process.platform, cli = undefined } = {}) {
  const bin = cli === undefined ? findClaudeCli({ run, platform }) : cli;
  if (!bin) return { installed: false, connected: false };
  const r = runClaude(bin, ["mcp", "get", SERVER_NAME], { run, platform });
  return { installed: true, connected: !!r && r.status === 0 };
}

// ── 한 번에 연결/해제/상태 (앱이 쓰는 진입점) ────────────────────────────────

/** 등록에 넘기는 env: 앱 주소(M3)와 데이터 폴더. */
function mcpEnv({ fastapiUrl, userDataDir }) {
  return { HAEHAN_FASTAPI_URL: fastapiUrl, HAEHAN_DATA_DIR: path.join(userDataDir, "data") };
}

async function connectClaude(ctx) {
  const { srcDir, userDataDir, version, buildVersion = null, appDataDir, fastapiUrl, hooks = {} } = ctx;
  const installed = await installMcpBundle({ srcDir, userDataDir, version, buildVersion });
  if (!installed.ok) return { ok: false, error: installed.error, hint: installed.hint, desktop: null, code: null };
  const env = mcpEnv({ fastapiUrl, userDataDir });
  const desktop = registerClaudeDesktop({ cfgPath: claudeDesktopConfigPath(appDataDir), exePath: installed.exePath, env });
  const code = registerClaudeCode({ exePath: installed.exePath, env, ...hooks });
  // 한쪽이라도 연결되면 성공으로 본다(Claude Desktop 만 있거나 Claude Code 만 있는 PC)
  const ok = desktop.ok || code.ok;
  const hints = [desktop.ok ? desktop.hint : null, code.ok ? code.hint : null].filter(Boolean);
  return {
    ok,
    error: ok ? undefined : desktop.error || code.error,
    hint: ok ? hints.join(" / ") : [desktop.hint, code.hint].filter(Boolean).join(" / "),
    buildId: installed.buildId,
    exePath: installed.exePath,
    desktop,
    code,
  };
}

function disconnectClaude(ctx) {
  const { appDataDir, hooks = {} } = ctx;
  const desktop = unregisterClaudeDesktop({ cfgPath: claudeDesktopConfigPath(appDataDir) });
  const code = unregisterClaudeCode({ ...hooks });
  const failed = [desktop, code].find((r) => !r.ok && r.error !== "claude_desktop_not_found");
  return { ok: !failed, error: failed && failed.error, hint: failed && failed.hint, desktop, code };
}

function claudeStatus(ctx) {
  const { appDataDir, exePath, hooks = {} } = ctx;
  return {
    desktop: desktopStatus({ cfgPath: claudeDesktopConfigPath(appDataDir), exePath }),
    code: codeStatus({ ...hooks }),
  };
}

module.exports = {
  SERVER_NAME,
  EXE_NAME,
  readBuildVersion,
  buildId,
  installMcpBundle,
  claudeDesktopConfigPath,
  registerClaudeDesktop,
  unregisterClaudeDesktop,
  desktopStatus,
  findClaudeCli,
  registerClaudeCode,
  unregisterClaudeCode,
  codeStatus,
  mcpEnv,
  connectClaude,
  disconnectClaude,
  claudeStatus,
};
