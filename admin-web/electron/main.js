/**
 * Haehan AI Desktop — 진입점 (신버전)
 *
 * 앱 실행 코드는 lib/* 모듈로 분리:
 *   lib/config.js        설정 IO + 소유자 모드 판정
 *   lib/agent.js         로컬 CDP 에이전트(Python) 프로세스
 *   lib/mainWindow.js    메인 창(shell.html webview) + 트레이 복원
 *   lib/licenseWindow.js 라이선스 입력 창 + 검증
 *   lib/youtube.js       YouTube OAuth
 *   lib/tray.js          시스템 트레이
 *
 * 동작 모드:
 *   - 소유자(내 PC) 모드: config.owner_mode === true 또는 HAEHAN_OWNER=1
 *       → 라이선스 게이트 생략, 메인 화면(자유 네비게이션) 바로 진입(상시 로그인)
 *   - 일반 클라이언트: 라이선스 키 입력·검증 후 진입
 */
const { app, ipcMain } = require("electron");

const { loadConfig, saveConfig, isOwnerMode } = require("./lib/config");
const { startAgent, stopAgent } = require("./lib/agent");
const { createMainWindow, showMainWindow, getMainWindow, setQuiting } = require("./lib/mainWindow");
const { createLicenseWindow, verifyLicense } = require("./lib/licenseWindow");
const { startYouTubeOAuth } = require("./lib/youtube");
const { createTray, hasTray } = require("./lib/tray");
const { Menu } = require("electron");

// 앱 이름 고정 (userData = AppData\Roaming\Haehan AI), 상단 메뉴바 제거
app.setName("Haehan AI");
Menu.setApplicationMenu(null);

// 단일 인스턴스 보장
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => showMainWindow());

  app.whenReady().then(() => {
    // 이 PC 상시 자동 시작 등록
    app.setLoginItemSettings({ openAtLogin: true, openAsHidden: false });

    const cfg = loadConfig();

    // 소유자 모드 또는 저장된 라이선스 → 바로 시작
    if (isOwnerMode(cfg) || cfg.license_key) {
      const key = cfg.license_key || "OWNER";
      startAgent(key);
      createMainWindow(key);
      createTray();
    } else {
      startLicenseFlow();
    }

    app.on("activate", () => {
      if (!getMainWindow()) createMainWindow(loadConfig().license_key || "");
      else showMainWindow();
    });
  });
}

// ── 라이선스 입력 흐름 (일반 클라이언트 전용) ──────────────────────────────────
function startLicenseFlow() {
  const licWin = createLicenseWindow();

  ipcMain.once("license-submit", async (_, key) => {
    let ok = true;
    try {
      const res = await verifyLicense(key);
      ok = !!res.ok;
    } catch { ok = true; } // 예외 시 로컬 개발 편의로 허용

    if (ok) {
      saveConfig({ ...loadConfig(), license_key: key });
      licWin.close();
      startAgent(key);
      createMainWindow(key);
      createTray();
    } else {
      licWin.webContents.send("license-error");
    }
  });
}

// shell.html → YouTube 연결 요청
ipcMain.on("youtube-connect", async () => {
  const key = loadConfig().license_key || "";
  const ok = await startYouTubeOAuth(key);
  const win = getMainWindow();
  if (win) win.webContents.send("youtube-status", ok ? "connected" : "failed");
});

// ── 종료 처리 ────────────────────────────────────────────────────────────────
app.on("before-quit", () => { setQuiting(true); stopAgent(); });

// 트레이가 있으면 창을 닫아도 백그라운드 상주(트레이에서 다시 열기)
app.on("window-all-closed", () => { if (!hasTray()) app.quit(); });
