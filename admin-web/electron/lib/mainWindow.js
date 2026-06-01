/**
 * lib/mainWindow.js — 메인 창(shell.html webview) 생성 및 표시 제어
 * L9 Admin UI(데스크톱 셸) 계층.
 *
 * 트레이 버그 수정 포인트:
 *  - 창 닫기(close)는 파괴하지 않고 트레이로 숨김 → 트레이 클릭 시 즉시 복원, webview 상태 보존
 *  - showMainWindow(): 숨김/최소화/파괴 어떤 상태에서도 확실히 앞으로 표시(없으면 재생성)
 */
const { BrowserWindow, shell } = require("electron");
const path = require("path");
const { SERVER_URL, loadConfig } = require("./config");

let mainWindow = null;
let isQuiting = false;

function setQuiting(v) { isQuiting = v; }
function getMainWindow() { return mainWindow; }

function createMainWindow(licenseKey) {
  mainWindow = new BrowserWindow({
    width: 1280, height: 820,
    minWidth: 900, minHeight: 600,
    title: "Haehan AI",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webviewTag: true,          // shell.html의 <webview> 허용
    },
    show: false,
  });

  // shell.html에 서버 URL·라이선스 키·webview preload 경로를 쿼리로 전달
  // (신버전: 네비바 없이 / 통합 UI 로드). preload = 로컬 설정 브리지(P1-3).
  const shellPath = path.join(__dirname, "..", "shell.html");
  const webviewPreload = path.join(__dirname, "..", "webview_preload.js"); // dev·설치본 모두 electron 리소스 기준
  const shellUrl =
    `file://${shellPath}` +
    `?server=${encodeURIComponent(SERVER_URL)}` +
    `&license=${encodeURIComponent(licenseKey)}` +
    `&preload=${encodeURIComponent("file://" + webviewPreload)}`;
  mainWindow.loadURL(shellUrl);

  mainWindow.once("ready-to-show", () => mainWindow.show());

  // 서버 내부 링크는 webview, 외부 링크는 시스템 브라우저
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(SERVER_URL)) shell.openExternal(url);
    return { action: "deny" };
  });

  // 닫기 → 종료 중이 아니면 트레이로 숨김(상태 보존). 트레이에서 다시 열 수 있음.
  mainWindow.on("close", (e) => {
    if (!isQuiting) { e.preventDefault(); mainWindow.hide(); }
  });
  mainWindow.on("closed", () => { mainWindow = null; });

  return mainWindow;
}

/** 트레이 클릭/활성화 시 호출 — 숨김/최소화/파괴 모두 처리 */
function showMainWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  } else {
    createMainWindow(loadConfig().license_key || "");
  }
}

module.exports = { createMainWindow, showMainWindow, getMainWindow, setQuiting };
