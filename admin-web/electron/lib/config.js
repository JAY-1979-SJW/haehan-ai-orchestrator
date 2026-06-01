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

module.exports = { SERVER_URL, FASTAPI_URL, configPath, loadConfig, saveConfig, patchConfig, isOwnerMode };
