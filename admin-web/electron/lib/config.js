/**
 * lib/config.js — 설정 로드/저장 + 소유자(개발) 모드 판정
 * L10 Local PC App 계층. 환경변수/파일 IO만 담당, 업무 로직 없음.
 */
const { app } = require("electron");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");

// 앱 이름 고정 — userData 가 %APPDATA%\Haehan AI 로 결정되도록 경로 계산 전에 강제.
// (require 순서와 무관하게 항상 동일한 config.json 을 쓰게 한다)
app.setName("Haehan AI");

// 서버 URL (webview가 띄우는 Next.js / API 베이스)
const SERVER_URL = "http://127.0.0.1:3000";

// FastAPI 서버 URL (local-agent WebSocket 연결 대상)
const FASTAPI_URL = process.env.HAEHAN_FASTAPI_URL || "http://127.0.0.1:8401";

// userData\config.json 경로를 지연 계산 (app.setName 적용 이후 호출 보장)
function configPath() {
  return path.join(app.getPath("userData"), "config.json");
}

// ── config.json 읽기/쓰기 — 읽기 실패 때 설정을 덮어쓰지 않는다 (DESKTOP_RUNTIME_AUDIT D6) ──
// 예전에는 읽기·파싱 실패를 삼키고 {} 를 돌려줘서, 일시적 읽기 오류(백신 잠금 등) 뒤 저장이 파일 전체를 덮어썼다
// (JWT_SECRET 재생성 → 전원 로그아웃 + 라이선스·사이트 설정 소실).
//   missing    : 파일 없음(최초 실행) → {}
//   ok         : 정상
//   corrupt    : 내용이 깨짐(JSON 아님) → 깨진 파일을 config.json.corrupt-<시각> 으로 보존하고 오류로 알린 뒤,
//                복구 가능한 핵심 값(비밀·로그인 토큰·라이선스·소유자 모드 등)만 건져 새 파일의 시작값으로 쓴다
//   unreadable : 읽기 자체가 실패(잠금·권한) → 짧게 재시도 후에도 실패하면 **쓰기를 거부**한다(throw)
const _SALVAGE_STRINGS = ["jwt_secret", "auth_token", "license_key"];
const _SALVAGE_BOOLS = ["owner_mode", "autoStart", "useSystemChromeProfile"];
let _configWarnings = [];

function _warnConfig(message) {
  _configWarnings.push(message);
  console.error("[config] " + message);
}

/** 앱이 사용자에게 한 번 알릴 설정 경고를 꺼낸다(꺼내면 비워진다). */
function consumeConfigWarnings() {
  const w = _configWarnings;
  _configWarnings = [];
  return w;
}

function _sleepSync(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function _salvage(raw) {
  const out = {};
  for (const k of _SALVAGE_STRINGS) {
    const m = raw.match(new RegExp('"' + k + '"\\s*:\\s*"([^"\\\\]*)"'));
    if (m && m[1]) out[k] = m[1];
  }
  for (const k of _SALVAGE_BOOLS) {
    const m = raw.match(new RegExp('"' + k + '"\\s*:\\s*(true|false)'));
    if (m) out[k] = m[1] === "true";
  }
  return out;
}

function _readConfigState() {
  const p = configPath();
  if (!fs.existsSync(p)) return { state: "missing", cfg: {} };
  let raw;
  let lastErr;
  for (let i = 0; i < 3; i++) {
    try {
      raw = fs.readFileSync(p, "utf-8");
      break;
    } catch (e) {
      lastErr = e;
      _sleepSync(80);
    }
  }
  if (raw === undefined) {
    _warnConfig(`설정 파일을 읽지 못했습니다(${lastErr && lastErr.code}) — 덮어쓰지 않습니다: ${p}`);
    return { state: "unreadable", cfg: {}, error: lastErr };
  }
  // UTF-8 BOM 제거 후 파싱 — 일부 에디터/PowerShell 이 BOM 을 붙여 JSON.parse 가 실패하던 문제 방지
  const text = raw.replace(/^﻿/, "");
  try {
    const cfg = JSON.parse(text);
    if (cfg && typeof cfg === "object" && !Array.isArray(cfg)) return { state: "ok", cfg };
    throw new Error("설정 최상위가 객체가 아님");
  } catch (e) {
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const saved = `${p}.corrupt-${stamp}`;
    try {
      fs.renameSync(p, saved); // 원본을 보존(복구·조사용) — 이후 새 파일이 만들어진다
    } catch (re) {
      _warnConfig(`깨진 설정 파일을 보존하지 못했습니다(${re.code}) — 덮어쓰지 않습니다: ${p}`);
      return { state: "unreadable", cfg: {}, error: re };
    }
    const salvaged = _salvage(text);
    _warnConfig(
      `설정 파일이 손상되어 ${path.basename(saved)} 로 보존했습니다(${e.message}). ` +
        `복구한 항목: ${Object.keys(salvaged).join(", ") || "없음"}. 나머지 설정은 다시 지정해야 할 수 있습니다.`
    );
    return { state: "corrupt", cfg: salvaged };
  }
}

function loadConfig() {
  return _readConfigState().cfg;
}

function saveConfig(cfg) {
  const p = configPath();
  // 읽기 실패 상태에서는 저장하지 않는다 — 덮어쓰면 기존 설정을 잃는다.
  const st = _readConfigState();
  if (st.state === "unreadable") {
    throw new Error("config.json 을 읽을 수 없어 저장을 중단했습니다(기존 설정 보호)");
  }
  fs.mkdirSync(path.dirname(p), { recursive: true });
  const tmp = p + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(cfg, null, 2));
  fs.renameSync(tmp, p); // 원자적 쓰기(tmp + rename)
}

function patchConfig(patch) {
  const st = _readConfigState();
  if (st.state === "unreadable") {
    throw new Error("config.json 을 읽을 수 없어 저장을 중단했습니다(기존 설정 보호)");
  }
  const next = { ...st.cfg, ...patch };
  saveConfig(next);
  return next;
}

/**
 * 소유자(개발) PC 모드 판정.
 * - config.json 의 owner_mode === true  (내 PC 고정)
 * - 또는 환경변수 HAEHAN_OWNER=1
 * 소유자 모드에서는 라이선스 게이트를 건너뛰고 바로 메인 화면으로 진입한다.
 */
function isOwnerMode(cfg = loadConfig()) {
  return cfg.owner_mode === true || process.env.HAEHAN_OWNER === "1";
}

// ── 사이트 선택·설정 (순수 로컬 저장; P1-2) ─────────────────────────────────────
// 사용자가 카탈로그에서 고른 사이트와 사이트별 비민감 설정을 config.json 에 저장한다.
// 서버로 전송하지 않는다. 자격증명/비밀번호 등 민감값은 저장 금지(아래에서 strip).

// 민감 키 — config.json 평문 저장 금지 (비밀번호/세션은 OS 자격증명·cdp_profile 등 별도)
const _SENSITIVE_KEY = /pass|pwd|secret|token|cookie|credential|otp|apikey|api_key|private/i;

function _stripSensitive(obj) {
  const out = {};
  for (const [k, v] of Object.entries(obj || {})) {
    if (_SENSITIVE_KEY.test(k)) continue; // 민감 키는 저장하지 않음
    out[k] = v;
  }
  return out;
}

/** 사용자가 켠 사이트 id 목록 (없으면 []). */
function getEnabledSites(cfg = loadConfig()) {
  return Array.isArray(cfg.enabled_sites) ? cfg.enabled_sites.filter((s) => typeof s === "string") : [];
}

/** 켠 사이트 목록 저장 (문자열 배열만). */
function setEnabledSites(siteIds) {
  const list = Array.isArray(siteIds) ? [...new Set(siteIds.filter((s) => typeof s === "string"))] : [];
  return patchConfig({ enabled_sites: list });
}

/** 특정 사이트의 비민감 설정 조회 (없으면 {}). */
function getSiteSettings(siteId, cfg = loadConfig()) {
  // 2026-09-29 electron-verifier 검증(WARN) 대응: setSiteSettings와 동일하게 타입 검증.
  if (typeof siteId !== "string" || !siteId) return {};
  const all = cfg.site_settings || {};
  return all[siteId] ? { ...all[siteId] } : {};
}

/** 특정 사이트 설정 병합 저장 — 민감 키는 자동 제거. */
function setSiteSettings(siteId, settings) {
  if (typeof siteId !== "string" || !siteId) throw new Error("siteId 필요");
  const cfg = loadConfig();
  const all = { ...(cfg.site_settings || {}) };
  all[siteId] = { ...(all[siteId] || {}), ..._stripSensitive(settings) };
  return patchConfig({ site_settings: all });
}

// ── 영속 로그인용 JWT_SECRET / 토큰 (userData config.json, 비추적) ────────────────
// JWT_SECRET 을 이 PC 에 고정해 FastAPI 재시작에도 발급 토큰이 유효하게 한다.
// (env 미설정 시 FastAPI 는 재시작마다 랜덤 secret → 토큰 무효화되던 문제 해결)
let _ephemeralJwtSecret = "";
function getOrCreateJwtSecret() {
  const st = _readConfigState();
  const cfg = st.cfg;
  if (typeof cfg.jwt_secret === "string" && cfg.jwt_secret.length >= 32) {
    if (st.state === "corrupt") {
      try { saveConfig(cfg); } catch {} // 손상 파일에서 건진 값(비밀 포함)을 새 파일에 바로 기록 — 로그인이 유지된다
    }
    return cfg.jwt_secret;
  }
  const secret = crypto.randomBytes(32).toString("hex");
  if (st.state !== "unreadable") {
    try {
      saveConfig({ ...cfg, jwt_secret: secret }); // 기존 설정은 그대로 두고 비밀만 추가
      return secret;
    } catch (e) {
      _warnConfig(`JWT_SECRET 을 저장하지 못했습니다(${e.message})`);
    }
  }
  // 읽기/쓰기가 안 되는 상태: 설정을 덮어쓰지 않고 이번 실행에만 쓸 임시 비밀을 쓴다(로그인은 다음 실행에서 풀릴 수 있음).
  if (!_ephemeralJwtSecret) _ephemeralJwtSecret = secret;
  _warnConfig("영구 JWT_SECRET 을 쓸 수 없어 이번 실행에만 임시 비밀을 사용합니다 — 다음 실행에서 다시 로그인해야 할 수 있습니다.");
  return _ephemeralJwtSecret;
}

/** 저장된 사용자 세션 토큰(있으면). webview localStorage 에 주입해 상시 로그인 유지. */
function getAuthToken() {
  const t = loadConfig().auth_token;
  return typeof t === "string" ? t : "";
}

/** 사용자 세션 토큰 저장(로그인/갱신 시). */
function setAuthToken(token) {
  return patchConfig({ auth_token: typeof token === "string" ? token : "" });
}

// ── Windows 시작 시 자동 실행 여부 ───────────────────────────────────────────
// scripts/start_haehan_ai.ps1(시작프로그램 폴더 바로가기가 호출)이 같은 config.json 의
// autoStart 값을 읽어 켜져 있을 때만 전체 스택을 기동한다. 값이 없으면(최초 실행) 기본 꺼짐 —
// 데스크탑 아이콘을 직접 클릭하면 이 값과 무관하게 앱(+백엔드)이 바로 실행된다.
function isAutoStartEnabled(cfg = loadConfig()) {
  return cfg.autoStart === true;
}

function setAutoStartEnabled(enabled) {
  return patchConfig({ autoStart: !!enabled });
}

// ── 사용자 API 키 (userData/.env, config.json과 별도 파일) ───────────────────────
// config.json 은 _stripSensitive() 로 민감값 저장을 금지하므로, 사용자가 설정화면에서
// 입력하는 외부 API 키는 별도 .env 파일에 dotenv 포맷 그대로 저장한다.
// FastAPI 번들 서버 spawn 시 이 값들을 env로 주입한다 (lib/fastapi_server.js).
const ENV_KEYS = [
  "NAVER_OPENAPI_CLIENT_ID",
  "NAVER_OPENAPI_CLIENT_SECRET",
  "YOUTUBE_DATA_API_KEY",
  "OPENAI_API_KEY",
  "UNSPLASH_ACCESS_KEY",
];

function userEnvPath() {
  return path.join(app.getPath("userData"), ".env");
}

function loadUserEnv() {
  const p = userEnvPath();
  if (!fs.existsSync(p)) return {};
  const out = {};
  for (const line of fs.readFileSync(p, "utf-8").split("\n")) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m) out[m[1]] = m[2];
  }
  return out;
}

function saveUserEnv(patch) {
  const cur = loadUserEnv();
  const next = { ...cur, ...patch };
  const body = Object.entries(next)
    .filter(([, v]) => typeof v === "string" && v !== "")
    .map(([k, v]) => `${k}=${v}`)
    .join("\n");
  fs.mkdirSync(path.dirname(userEnvPath()), { recursive: true });
  fs.writeFileSync(userEnvPath(), body, "utf-8");
  return next;
}

/** 설정화면 표시용 — 값을 마스킹해 반환 (원문 노출 금지). */
function maskedUserEnv() {
  const cur = loadUserEnv();
  const out = {};
  for (const k of ENV_KEYS) {
    const v = cur[k] || "";
    out[k] = v ? `${"*".repeat(Math.max(0, v.length - 4))}${v.slice(-4)}` : "";
  }
  return out;
}

// ── Claude Desktop MCP 연동 ───────────────────────────────────────────────────
// Claude Desktop 의 claude_desktop_config.json 에 이 앱의 번들 MCP 서버(haehan-mcp.exe)를
// 등록한다. 다른 직원 PC에서도 python 환경 없이 바로 연결되도록 exe 그대로 가리킨다.

function claudeDesktopConfigPath() {
  return path.join(app.getPath("appData"), "Claude", "claude_desktop_config.json");
}

function connectClaudeDesktop() {
  if (!app.isPackaged) {
    return { ok: false, error: "dev_mode_unsupported", hint: "패키징된 앱에서만 지원합니다" };
  }
  const cfgPath = claudeDesktopConfigPath();
  if (!fs.existsSync(cfgPath)) {
    return { ok: false, error: "claude_desktop_not_found", hint: "Claude Desktop을 먼저 설치·실행하세요" };
  }

  let cfg;
  try {
    const raw = fs.readFileSync(cfgPath, "utf-8").replace(/^﻿/, "");
    cfg = JSON.parse(raw);
  } catch (e) {
    return { ok: false, error: "config_parse_failed", hint: String(e) };
  }

  const mcpExe = path.join(process.resourcesPath, "mcp", "haehan-mcp", "haehan-mcp.exe");
  if (!fs.existsSync(mcpExe)) {
    return { ok: false, error: "mcp_exe_missing", hint: mcpExe };
  }

  cfg.mcpServers = cfg.mcpServers || {};
  cfg.mcpServers["haehan-orchestrator"] = {
    command: mcpExe,
    args: [],
    env: { HAEHAN_DATA_DIR: path.join(app.getPath("userData"), "data") },
  };

  fs.writeFileSync(cfgPath, JSON.stringify(cfg, null, 4), "utf-8");
  return { ok: true, hint: "Claude Desktop을 재시작하면 적용됩니다" };
}

module.exports = {
  SERVER_URL,
  FASTAPI_URL,
  configPath,
  loadConfig,
  saveConfig,
  patchConfig,
  consumeConfigWarnings,
  isOwnerMode,
  getOrCreateJwtSecret,
  getAuthToken,
  setAuthToken,
  getEnabledSites,
  setEnabledSites,
  getSiteSettings,
  setSiteSettings,
  isAutoStartEnabled,
  setAutoStartEnabled,
  ENV_KEYS,
  loadUserEnv,
  saveUserEnv,
  maskedUserEnv,
  connectClaudeDesktop,
};
