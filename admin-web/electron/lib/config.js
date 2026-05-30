/**
 * lib/config.js — 설정 로드/저장 + 소유자(개발) 모드 판정
 * L10 Local PC App 계층. 환경변수/파일 IO만 담당, 업무 로직 없음.
 */
const { app } = require("electron");
const path = require("path");
const fs = require("fs");

// 서버 URL (webview가 띄우는 Next.js / API 베이스)
const SERVER_URL = "http://localhost:3000";

// userData\config.json (예: %APPDATA%\Haehan AI\config.json)
const CONFIG_PATH = path.join(app.getPath("userData"), "config.json");

function loadConfig() {
  try {
    if (fs.existsSync(CONFIG_PATH)) return JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
  } catch {}
  return {};
}

function saveConfig(cfg) {
  fs.mkdirSync(path.dirname(CONFIG_PATH), { recursive: true });
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
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

module.exports = { SERVER_URL, CONFIG_PATH, loadConfig, saveConfig, patchConfig, isOwnerMode };
