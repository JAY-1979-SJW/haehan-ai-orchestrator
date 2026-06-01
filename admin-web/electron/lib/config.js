/**
 * lib/config.js — 설정 로드/저장 + 소유자(개발) 모드 판정
 * L10 Local PC App 계층. 환경변수/파일 IO만 담당, 업무 로직 없음.
 */
const { app } = require("electron");
const path = require("path");
const fs = require("fs");

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

function loadConfig() {
  try {
    const p = configPath();
    if (fs.existsSync(p)) {
      // UTF-8 BOM 제거 후 파싱 — 일부 에디터/PowerShell 이 BOM 을 붙여
      // JSON.parse 가 실패하던 문제 방지
      const raw = fs.readFileSync(p, "utf-8").replace(/^﻿/, "");
      return JSON.parse(raw);
    }
  } catch {}
  return {};
}

function saveConfig(cfg) {
  const p = configPath();
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(cfg, null, 2));
}

function patchConfig(patch) {
  const next = { ...loadConfig(), ...patch };
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

module.exports = {
  SERVER_URL,
  FASTAPI_URL,
  configPath,
  loadConfig,
  saveConfig,
  patchConfig,
  isOwnerMode,
  getEnabledSites,
  setEnabledSites,
  getSiteSettings,
  setSiteSettings,
};
