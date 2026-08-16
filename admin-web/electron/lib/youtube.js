/**
 * lib/youtube.js — YouTube OAuth 자동 로그인 흐름
 * L3 Connectors(외부 OAuth IO) + 데스크톱 팝업 제어.
 * 토큰/시크릿 원문은 로깅하지 않는다.
 */
const { app, BrowserWindow, dialog } = require("electron");
const path = require("path");
const fs = require("fs");
const https = require("https");
const { SERVER_URL, loadConfig } = require("./config");
// 통신 분리: mainWindow 모듈을 직접 import 하지 않는다.
// 모달 부모 창 참조는 컴포지션 루트(main.js)가 provider 로 주입한다.
let _getParentWindow = () => null;
function setWindowProvider(fn) { _getParentWindow = typeof fn === "function" ? fn : () => null; }

let youtubeOAuthWin = null;

function checkYouTubeToken() {
  const cfg = loadConfig();
  // packed app: __dirname은 asar 내부 → process.execPath 기준 프로젝트 루트 사용
  // 비패키지: __dirname=electron/lib → 3단계 상위가 프로젝트 루트
  const BASE = app.isPackaged
    ? path.resolve(path.dirname(process.execPath), "..", "..", "..")
    : path.resolve(__dirname, "..", "..", "..");
  const tokenFile = cfg.youtube_token_file ||
    path.join(BASE, "ai_orchestrator", "storage", "secrets", "youtube_oauth_authorized_user.json");
  return fs.existsSync(tokenFile);
}

function startYouTubeOAuth(licenseKey) {
  return new Promise((resolve) => {
    https.get(
      `${SERVER_URL}/api/v1/oauth/youtube/auth-url`,
      { headers: { "x-license-key": licenseKey } },
      (res) => {
        let data = "";
        res.on("data", (d) => data += d);
        res.on("end", () => {
          try {
            const authUrl = JSON.parse(data).auth_url;
            if (!authUrl) { resolve(false); return; }
            openYouTubeOAuthPopup(authUrl, licenseKey, resolve);
          } catch { resolve(false); }
        });
      }
    ).on("error", () => resolve(false));
  });
}

function openYouTubeOAuthPopup(authUrl, licenseKey, resolve) {
  if (youtubeOAuthWin) youtubeOAuthWin.close();

  youtubeOAuthWin = new BrowserWindow({
    width: 520, height: 680,
    title: "YouTube 계정 연결",
    webPreferences: { nodeIntegration: false, contextIsolation: true },
    parent: _getParentWindow(), modal: true,
  });

  youtubeOAuthWin.loadURL(authUrl);

  const CALLBACK_PREFIX = `${SERVER_URL}/api/v1/oauth/youtube/callback`;
  // will-navigate 와 did-navigate 가 같은 콜백 URL 이동에 대해 둘 다 발화한다. 가드 없이 두 번
  // 실행되면 두 번째 호출 시 youtubeOAuthWin 이 이미 null 이라 close() 에서 TypeError 로 크래시.
  let handled = false;
  youtubeOAuthWin.webContents.on("will-navigate", (_, url) => handleCallback(url));
  youtubeOAuthWin.webContents.on("did-navigate", (_, url) => handleCallback(url));

  function handleCallback(url) {
    if (handled) return;
    if (!url.startsWith(CALLBACK_PREFIX)) return;
    handled = true;
    const code = new URL(url).searchParams.get("code");
    if (!code) { resolve(false); return; }
    youtubeOAuthWin.close();
    youtubeOAuthWin = null;

    const body = JSON.stringify({ code });
    const req = https.request(
      new URL(`${SERVER_URL}/api/v1/oauth/youtube/callback`),
      { method: "POST", headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body), "x-license-key": licenseKey } },
      (res) => {
        let d = "";
        res.on("data", (c) => d += c);
        res.on("end", () => { try { resolve(JSON.parse(d).ok === true); } catch { resolve(false); } });
      }
    );
    req.on("error", () => resolve(false));
    req.write(body); req.end();
  }

  youtubeOAuthWin.on("closed", () => { youtubeOAuthWin = null; resolve(false); });
}

async function ensureYouTubeAuth(licenseKey) {
  if (checkYouTubeToken()) return; // 이미 토큰 있음
  const win = _getParentWindow();

  const choice = await dialog.showMessageBox(win, {
    type: "question",
    title: "YouTube 계정 연결",
    message: "YouTube 기능을 사용하려면 Google 계정 연결이 필요합니다.",
    detail: "지금 연결하시겠습니까? (나중에 설정에서 다시 연결할 수 있습니다)",
    buttons: ["지금 연결", "나중에"],
    defaultId: 0,
  });

  if (choice.response === 0) {
    const ok = await startYouTubeOAuth(licenseKey);
    if (ok) {
      dialog.showMessageBox(win, {
        type: "info", title: "연결 완료",
        message: "YouTube 계정이 성공적으로 연결되었습니다.", buttons: ["확인"],
      });
    }
  }
}

module.exports = { checkYouTubeToken, startYouTubeOAuth, ensureYouTubeAuth, setWindowProvider };
