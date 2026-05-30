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
const { startYouTubeOAuth, ensureYouTubeAuth, setWindowProvider } = require("./lib/youtube");
const { createTray, hasTray } = require("./lib/tray");
const { bus, EVENTS } = require("./lib/bus");
const { Menu } = require("electron");

// youtube 모듈에 메인 창 provider 주입 (youtube → mainWindow 직접 의존 제거)
setWindowProvider(getMainWindow);

// 앱 이름 고정 (userData = AppData\Roaming\Haehan AI), 상단 메뉴바 제거
app.setName("Haehan AI");
Menu.setApplicationMenu(null);

// ── 버스 구독 (컴포지션 루트) ──────────────────────────────────────────────────
// 발행자(tray 등)는 sibling 모듈을 직접 부르지 않고 이벤트만 emit 하며,
// 실제 처리는 여기(main)에서 모듈 동작에 연결한다.
bus.on(EVENTS.SHOW_WINDOW, () => showMainWindow());
bus.on(EVENTS.YOUTUBE_RECONNECT, () => ensureYouTubeAuth(loadConfig().license_key || ""));
// YouTube 연결 상태 → 렌더러(shell.html)로 전달하는 단일 경로
bus.on(EVENTS.YOUTUBE_STATUS, (status) => {
  const win = getMainWindow();
  if (win) win.webContents.send("youtube-status", status);
});

// 단일 인스턴스 보장
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => bus.emit(EVENTS.SHOW_WINDOW));

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

    // 창 표시/복원은 버스로 일원화 (showMainWindow 가 없으면 재생성까지 처리)
    app.on("activate", () => bus.emit(EVENTS.SHOW_WINDOW));
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
  bus.emit(EVENTS.YOUTUBE_STATUS, ok ? "connected" : "failed");
});

// ── 종료 처리 ────────────────────────────────────────────────────────────────
app.on("before-quit", () => { setQuiting(true); stopAgent(); });

// 트레이가 있으면 창을 닫아도 백그라운드 상주(트레이에서 다시 열기)
app.on("window-all-closed", () => { if (!hasTray()) app.quit(); });
