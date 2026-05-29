/**
 * Electron 메인 프로세스 — 씬 클라이언트
 * 서버에 모든 로직(FastAPI + Chrome CDP + AI)이 있으므로
 * Electron은 서버 URL을 데스크톱 창으로 열어주기만 합니다.
 */
const { app, BrowserWindow, Menu, Tray, shell, dialog } = require("electron");
const path  = require("path");
const fs    = require("fs");

// ── 서버 URL 설정 ─────────────────────────────────────────────────────────────
// 우선순위: 환경변수 > config.json > 기본값
function getServerUrl() {
  if (process.env.HAEHAN_SERVER_URL) return process.env.HAEHAN_SERVER_URL;

  const configPath = path.join(app.getPath("userData"), "config.json");
  if (fs.existsSync(configPath)) {
    try {
      const cfg = JSON.parse(fs.readFileSync(configPath, "utf-8"));
      if (cfg.serverUrl) return cfg.serverUrl;
    } catch {}
  }

  return "http://localhost:3000";
}

function saveServerUrl(url) {
  const configPath = path.join(app.getPath("userData"), "config.json");
  const cfg = fs.existsSync(configPath)
    ? JSON.parse(fs.readFileSync(configPath, "utf-8"))
    : {};
  cfg.serverUrl = url;
  fs.writeFileSync(configPath, JSON.stringify(cfg, null, 2));
}

// ── 메인 창 ───────────────────────────────────────────────────────────────────
let mainWindow = null;
let tray       = null;
let serverUrl  = getServerUrl();

function createWindow() {
  mainWindow = new BrowserWindow({
    width:  1280,
    height: 800,
    minWidth:  900,
    minHeight: 600,
    title: "Haehan AI",
    icon: path.join(__dirname, "icon.png"),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
    show: false,
  });

  mainWindow.loadURL(`${serverUrl}/naver/smartstore`);

  mainWindow.once("ready-to-show", () => mainWindow.show());

  // 외부 링크는 시스템 브라우저로 열기
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(serverUrl)) shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.on("closed", () => { mainWindow = null; });
}

// ── 서버 URL 변경 다이얼로그 ──────────────────────────────────────────────────
async function promptServerUrl() {
  const { response, checkboxChecked } = await dialog.showMessageBox({
    type: "question",
    title: "서버 주소 설정",
    message: `현재 서버: ${serverUrl}\n\n서버 주소를 변경하려면 아래에서 입력하세요.`,
    buttons: ["변경", "취소"],
    defaultId: 1,
  });
  if (response !== 0) return;

  // 간단한 입력 창 (prompt 대체)
  const inputWin = new BrowserWindow({
    width: 480, height: 160,
    resizable: false, modal: true,
    parent: mainWindow,
    webPreferences: { nodeIntegration: true, contextIsolation: false },
  });
  inputWin.loadURL("data:text/html,<input id=u style='width:90%;margin:20px' value='" + serverUrl + "'><br><button onclick=\"require('electron').ipcRenderer.send('url-input',document.getElementById('u').value)\">확인</button>");

  const { ipcMain } = require("electron");
  ipcMain.once("url-input", (_, url) => {
    inputWin.close();
    if (url && url.startsWith("http")) {
      serverUrl = url.replace(/\/$/, "");
      saveServerUrl(serverUrl);
      if (mainWindow) mainWindow.loadURL(`${serverUrl}/naver/smartstore`);
    }
  });
}

// ── 트레이 ────────────────────────────────────────────────────────────────────
function createTray() {
  const iconPath = path.join(__dirname, "icon.png");
  if (!fs.existsSync(iconPath)) return;   // 아이콘 없으면 트레이 스킵

  tray = new Tray(iconPath);
  tray.setToolTip("Haehan AI");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "열기",          click: () => { if (mainWindow) mainWindow.show(); else createWindow(); } },
    { label: "서버 주소 변경", click: promptServerUrl },
    { type: "separator" },
    { label: "종료",          click: () => app.quit() },
  ]));
  tray.on("double-click", () => { if (mainWindow) mainWindow.show(); else createWindow(); });
}

// ── 앱 생명주기 ───────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  createWindow();
  createTray();

  // macOS: Dock 클릭 시 창 복구
  app.on("activate", () => { if (!mainWindow) createWindow(); });
});

// 모든 창 닫혀도 앱 유지 (트레이 상주)
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    // 트레이 있으면 백그라운드 유지, 없으면 종료
    if (!tray) app.quit();
  }
});

// 앱 두 번 실행 시 기존 창 포커스
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus(); }
  });
}
