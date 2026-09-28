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

// Electron 앱 자신의 창(webview 포함)을 CDP로 제어할 수 있게 원격 디버깅 포트를 연다.
// ready 이벤트 이전에 호출해야 한다(공식 문서: code.electronjs.org/docs/latest/api/command-line-switches).
// 9222는 scripts/local_agent/start_chrome_with_cdp.py 가 쓰는 "사용자 Chrome" CDP 포트와 겹치므로
// 별도 포트(9333)를 쓴다 — 웹사이트 자동화(사용자 Chrome)와 앱 자체 자동화(이 창)를 분리한다.
app.commandLine.appendSwitch("remote-debugging-port", "9333");

const {
  loadConfig, saveConfig, isOwnerMode,
  getEnabledSites, setEnabledSites, getSiteSettings, setSiteSettings,
  getAuthToken, isAutoStartEnabled, setAutoStartEnabled,
  ENV_KEYS, saveUserEnv, maskedUserEnv, connectClaudeDesktop,
} = require("./lib/config");
const { startAgent, stopAgent } = require("./lib/agent");
const { createMainWindow, showMainWindow, getMainWindow, setQuiting } = require("./lib/mainWindow");
const { createLicenseWindow, verifyLicense } = require("./lib/licenseWindow");
const { startYouTubeOAuth, ensureYouTubeAuth, setWindowProvider } = require("./lib/youtube");
const { createTray, updateAutoLaunchCheck, hasTray } = require("./lib/tray");
const { bus, EVENTS } = require("./lib/bus");
const { Menu, dialog, session } = require("electron");
const { startFastAPIServer, stopFastAPIServer } = require("./lib/fastapi_server");
const { startNextServer, stopNextServer } = require("./lib/nextjs_server");
const { fetchAndApplyRemoteConfig } = require("./lib/remote_config");
const { startCdpBrowser, stopCdpBrowser, isCdpAlive, setUseSystemChromeProfile } = require("./lib/cdp_manager");
// CDP watchdog — 앱이 CDP 를 책임지고 항상 살려둔다(클릭→앱 출력이 항상 되도록)
let cdpWatchdogTimer = null;
let appQuitting = false;

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
// 시스템 Chrome 프로필 토글 (트레이 체크박스)
bus.on(EVENTS.TOGGLE_SYSTEM_CHROME, () => {
  const cfg = loadConfig();
  const next = !cfg.useSystemChromeProfile;
  setUseSystemChromeProfile(next);
  // 트레이 메뉴 체크 상태 갱신
  // 동적 require: tray → config → electron 경로로 인한 순환 의존성을 런타임 로드로 회피
  const { updateAutoLaunchCheck } = require("./lib/tray");
  updateAutoLaunchCheck(isAutoStartEnabled());
  const win = getMainWindow();
  if (win) win.webContents.send("notify", next
    ? "✅ 내 Chrome 세션 사용 ON — 다음 CDP 시작부터 적용됩니다"
    : "ℹ️ 내 Chrome 세션 사용 OFF — 앱 전용 프로필로 전환됩니다");
});
// 트레이 자동실행 토글 — start_haehan_ai.ps1(시작프로그램 바로가기)이 읽는 config.json
// autoStart 값을 직접 변경한다(electron 자체 로그인아이템 레지스트리는 사용 안 함 — ps1
// 런처와 이중 등록되어 앱이 두 번 뜨는 문제 방지).
bus.on(EVENTS.TOGGLE_AUTO_LAUNCH, () => {
  const next = !isAutoStartEnabled();
  setAutoStartEnabled(next);
  updateAutoLaunchCheck(next);
});

// 단일 인스턴스 보장
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => bus.emit(EVENTS.SHOW_WINDOW));

  app.whenReady().then(async () => {
    // 소유자 모드 환경변수 조기 주입 — Next.js fork에 상속되어 미들웨어 인증 우회
    if (isOwnerMode(loadConfig())) process.env.OWNER_MODE = "true";

    // 자동실행 여부는 electron.app 로그인아이템 레지스트리가 아니라 config.json 의 autoStart
    // 값으로 관리한다(isAutoStartEnabled/setAutoStartEnabled). 시작프로그램 폴더의
    // start_haehan_ai.ps1(전체 스택 런처)이 같은 값을 읽어 꺼져 있으면 기동을 건너뛴다.
    // 트레이 메뉴(TOGGLE_AUTO_LAUNCH)에서 켜고 끌 수 있다.

    // webview 파티션의 Service Worker/캐시 정리 — 빌드 변경 시 옛 SW가 cache-first로
    // 깨진 자원을 서빙해 화면이 RSC 원문으로 깨지는 문제 방지. 쿠키(로그인)는 보존.
    try {
      await session.fromPartition("persist:haehan").clearStorageData({
        storages: ["serviceworkers", "cachestorage"],
      });
    } catch (e) {
      console.warn("[main] webview SW/캐시 정리 실패(무시):", e.message);
    }
    // HTTP 디스크 캐시도 비움 — 빌드 변경 시 옛 Next 청크/HTML 이 캐시돼 옛 화면이 뜨던
    // 문제 해결(쿠키·localStorage 토큰은 보존). 로컬 서버라 재다운로드 비용 작음.
    try {
      await session.fromPartition("persist:haehan").clearCache();
    } catch (e) {
      console.warn("[main] webview HTTP 캐시 정리 실패(무시):", e.message);
    }

    // ── FastAPI 서버 시작 (번들 EXE 또는 외부 uvicorn 대기) ───────────────
    const serverReady = await startFastAPIServer();
    if (!serverReady) {
      dialog.showErrorBox(
        "서버 시작 실패",
        "Haehan AI 서버를 시작할 수 없습니다.\n" +
        "로그 파일(%APPDATA%\\Haehan AI\\logs\\fastapi.log)을 확인하세요."
      );
      app.quit();
      return;
    }

    // ── CDP 브라우저: 온디맨드 ────────────────────────────────────────────────
    // 자동 시작/15초 워치독 제거(사용자 선택). CDP 창을 닫아도 다시 뜨지 않는다.
    // 브라우저가 필요한 작업이 들어오면 백엔드(web_connector._ensure_cdp_daemon)가
    // 그 시점에 CDP를 자동 기동하므로 기능 손실 없음. (startCdpBrowser 는 보존 —
    // 추후 명시적 요청 시 호출 가능)
    if (cdpWatchdogTimer) { clearInterval(cdpWatchdogTimer); cdpWatchdogTimer = null; }

    // ── Next.js 서버 시작 ────────────────────────────────────────────────────
    const nextReady = await startNextServer();
    if (!nextReady) {
      dialog.showErrorBox(
        "UI 서버 시작 실패",
        "Haehan AI UI 서버를 시작할 수 없습니다.\n" +
        "로그 파일(%APPDATA%\\Haehan AI\\logs\\nextjs.log)을 확인하세요."
      );
      app.quit();
      return;
    }

    const cfg = loadConfig();

    // ── 원격 서버에서 환경변수 fetch → 로컬 FastAPI에 주입 ───────────────────
    const licenseKey = cfg.license_key || "";
    if (licenseKey) {
      fetchAndApplyRemoteConfig(licenseKey).catch((e) =>
        console.warn("[main] remote config 적용 실패 (무시):", e.message)
      );
    }

    // 소유자 모드 또는 저장된 라이선스 → 바로 시작
    if (isOwnerMode(cfg) || cfg.license_key) {
      const key = cfg.license_key || "OWNER";
      const startHidden = process.argv.includes("--hidden");
      startAgent(key);
      createMainWindow(key, startHidden);
      createTray(isAutoStartEnabled());
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

  // on(반복 허용) — 첫 시도가 틀렸을 때도 사용자가 다시 제출할 수 있어야 하므로 once() 는 부적합.
  // 성공 시에만 리스너를 해제한다(창이 닫히므로 이후 제출 불가).
  const onSubmit = async (_, key) => {
    let ok = false;
    try {
      const res = await verifyLicense(key);
      ok = !!res.ok;
    } catch { ok = false; } // fail-close: verifyLicense 자체 예외 시 거부 (오프라인 허용은 verifyLicense 내부에서 담당)

    if (ok) {
      ipcMain.removeListener("license-submit", onSubmit);
      saveConfig({ ...loadConfig(), license_key: key });
      licWin.close();
      startAgent(key);
      createMainWindow(key);
      createTray(isAutoStartEnabled());
    } else {
      licWin.webContents.send("license-error");
    }
  };
  ipcMain.on("license-submit", onSubmit);
}

// ── 로컬 설정 브리지 (P1-3) — webview UI ↔ config.json ──────────────────────
// invoke/handle (비동기, 값 반환). 사이트 선택·설정만. config.js가 민감값 차단.
// 영속 로그인: webview_preload 가 저장된 세션 토큰을 localStorage 에 주입하기 위해 조회
ipcMain.handle("local-config:get-auth-token", () => getAuthToken());
ipcMain.handle("local-config:get-enabled-sites", () => getEnabledSites());
ipcMain.handle("local-config:set-enabled-sites", (_e, ids) => setEnabledSites(ids).enabled_sites || []);
ipcMain.handle("local-config:get-site-settings", (_e, siteId) => getSiteSettings(siteId));
ipcMain.handle("local-config:set-site-settings", (_e, siteId, settings) => {
  setSiteSettings(siteId, settings);
  return getSiteSettings(siteId);
});

// API 키 설정: userData/.env 에 저장. 조회는 마스킹된 값만 반환(원문 재노출 금지).
// 저장 시 마스킹 값("****abcd")이 그대로 들어오면 변경 없는 항목으로 간주해 건너뜀.
ipcMain.handle("local-config:get-env-keys", () => ({ keys: ENV_KEYS, values: maskedUserEnv() }));
ipcMain.handle("local-config:set-env-keys", (_e, patch) => {
  const clean = {};
  for (const [k, v] of Object.entries(patch || {})) {
    if (!ENV_KEYS.includes(k)) continue;
    if (typeof v !== "string" || v === "" || v.startsWith("*")) continue;
    clean[k] = v.trim();
  }
  saveUserEnv(clean);
  return { ok: true, values: maskedUserEnv() };
});

// Claude Desktop MCP 연동: claude_desktop_config.json 에 번들 MCP 서버 등록
ipcMain.handle("local-config:connect-claude-desktop", () => connectClaudeDesktop());

// 사진 선택: 네이티브 파일 탐색기로 이미지를 고르면 로컬 경로 배열 반환.
// (사용자가 경로를 직접 타이핑하지 않게 — 백엔드는 로컬 경로를 직접 읽어 base64 처리)
ipcMain.handle("local-file:pick-images", async () => {
  const res = await dialog.showOpenDialog({
    title: "상품 사진 선택",
    properties: ["openFile", "multiSelections"],
    filters: [{ name: "이미지", extensions: ["jpg", "jpeg", "png", "webp", "gif", "bmp"] }],
  });
  return res.canceled ? [] : res.filePaths;
});

// shell.html → YouTube 연결 요청
ipcMain.on("youtube-connect", async () => {
  const key = loadConfig().license_key || "";
  const ok = await startYouTubeOAuth(key);
  bus.emit(EVENTS.YOUTUBE_STATUS, ok ? "connected" : "failed");
});

// ── 종료 처리 ────────────────────────────────────────────────────────────────
// stopFastAPIServer/stopNextServer 는 SIGTERM 후 3초 뒤 SIGKILL 폴백을 예약한다. before-quit 이
// 동기로 끝나자마자 Electron 이 프로세스를 종료해버리면 그 타이머가 실행되기 전에 죽어 정리가
// 안 되므로, 첫 호출에서 종료를 한 번 유예(preventDefault)하고 폴백 시간만큼 기다렸다가 quit().
app.on("before-quit", (event) => {
  if (appQuitting) return; // 유예 후 재호출된 두 번째 패스 — 그대로 종료 진행
  event.preventDefault();
  appQuitting = true;
  if (cdpWatchdogTimer) clearInterval(cdpWatchdogTimer);
  setQuiting(true);
  stopAgent();
  stopFastAPIServer();
  stopNextServer();
  stopCdpBrowser();
  setTimeout(() => app.quit(), 3200);
});

// 트레이가 있으면 창을 닫아도 백그라운드 상주(트레이에서 다시 열기)
app.on("window-all-closed", () => { if (!hasTray()) app.quit(); });
