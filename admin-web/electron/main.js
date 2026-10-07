/**
 * Haehan AI Desktop — 진입점 (신버전)
 *
 * 앱 실행 코드는 lib/* 모듈로 분리:
 *   lib/config.js        설정 IO + 소유자 모드 판정
 *   lib/agent.js         로컬 CDP 에이전트(Python) 프로세스
 *   lib/mainWindow.js    메인 창(shell.html webview) + 트레이 복원
 *   (라이선스 입력 창은 2026-10-08 삭제 — 데스크톱은 라이선스 없이 이 PC 전용 로컬 키로 시작)
 *   lib/youtube.js       YouTube OAuth
 *   lib/tray.js          시스템 트레이
 *
 * 동작 모드:
 *   - 소유자(내 PC) 모드: config.owner_mode === true 또는 HAEHAN_OWNER=1
 *       → 라이선스 게이트 생략, 메인 화면(자유 네비게이션) 바로 진입(상시 로그인)
 *   - 일반 클라이언트: 라이선스 키 입력·검증 후 진입
 */
const { app, ipcMain, shell: electronShell } = require("electron");
const fs = require("fs");
const path = require("path");

// Electron 앱 자신의 창(webview 포함)을 CDP로 제어할 수 있게 원격 디버깅 포트를 연다.
// ready 이벤트 이전에 호출해야 한다(공식 문서: code.electronjs.org/docs/latest/api/command-line-switches).
// 9222는 scripts/local_agent/start_chrome_with_cdp.py 가 쓰는 "사용자 Chrome" CDP 포트와 겹치므로
// 별도 포트(9333)를 쓴다 — 웹사이트 자동화(사용자 Chrome)와 앱 자체 자동화(이 창)를 분리한다.
app.commandLine.appendSwitch("remote-debugging-port", "9333");

const {
  loadConfig, isOwnerMode, ensureDesktopAgentKey,
  getEnabledSites, setEnabledSites, getSiteSettings, setSiteSettings,
  getAuthToken, isAutoStartEnabled, setAutoStartEnabled,
  ENV_KEYS, saveUserEnv, maskedUserEnv, patchConfig,
  consumeConfigWarnings,
  SERVER_URL, FASTAPI_URL,
} = require("./lib/config");
const { startAgent, stopAgent } = require("./lib/agent");
const { createMainWindow, loadMainShell, showMainWindow, getMainWindow, setQuiting } = require("./lib/mainWindow");
const { stage } = require("./lib/startup_log");
const { startAutoUpdate } = require("./lib/updater");
const { startYouTubeOAuth, ensureYouTubeAuth, setWindowProvider } = require("./lib/youtube");
const { createTray, updateAutoLaunchCheck, hasTray } = require("./lib/tray");
const { bus, EVENTS } = require("./lib/bus");
const { Menu, Notification, dialog, session, webContents } = require("electron");
const { startFastAPIServer, stopFastAPIServer, FASTAPI_PORT } = require("./lib/fastapi_server");
const { refreshDesktopSession } = require("./lib/desktop_session");
const { startNextServer, stopNextServer } = require("./lib/nextjs_server");
const claudeMcp = require("./lib/claude_mcp");
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

// ── webview(shell.html의 <webview>, Next.js UI) 탐색 보안 ──────────────────────
// mainWindow.webContents.setWindowOpenHandler(lib/mainWindow.js)는 메인 창 자체의
// window.open 만 막는다 — <webview> 태그가 만드는 별도 webContents는 범위 밖이라
// 따로 처리해야 한다(Electron 공식 권고: 이런 보안 판단은 렌더러가 아니라 메인
// 프로세스에서). 기존엔 shell.html 렌더러 스크립트가 new-window 이벤트에서
// require("electron")로 직접 열었는데, 이 창은 nodeIntegration:false 라 require가
// 없어 실행 시 ReferenceError로 항상 실패하고 있었다(2026-09-29 electron-verifier
// 검증 실측 발견 — "외부 링크는 시스템 브라우저로" 방어가 죽은 코드였음). 그리고
// will-navigate 가드가 전혀 없어서, webview 내부 콘텐츠(Next.js)의 오픈리다이렉트나
// 잘못된 링크로 SERVER_URL 밖으로 같은 탭 네비게이션이 일어나면 webview_preload.js가
// 노출한 window.haehanLocal(사이트 설정 변경, 파일 선택 등)이 그 외부 오리진에서도
// 계속 접근 가능한 상태였다(같은 검증에서 지적된 최우선 항목) — 여기서 두 가지를
// 한 번에 막는다: 팝업(setWindowOpenHandler)과 같은 탭 이동(will-navigate) 둘 다
// SERVER_URL 밖이면 차단하고 시스템 브라우저로만 연다.
app.on("web-contents-created", (_event, contents) => {
  if (contents.getType() !== "webview") return;
  contents.setWindowOpenHandler(({ url }) => {
    // 기존 렌더러 로직(new-window 이벤트)과 동일한 분기 유지: 내부 링크는 webview
    // 자신을 그 주소로 이동, 외부 링크만 시스템 브라우저로.
    if (url.startsWith(SERVER_URL)) contents.loadURL(url);
    else electronShell.openExternal(url);
    return { action: "deny" };
  });
  contents.on("will-navigate", (navEvent, url) => {
    if (!url.startsWith(SERVER_URL)) {
      navEvent.preventDefault();
      electronShell.openExternal(url);
    }
  });
});

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
    stage("ready");
    const startCfg = loadConfig();
    // 소유자 모드 환경변수 조기 주입 — Next.js fork에 상속되어 미들웨어 인증 우회
    if (isOwnerMode(startCfg)) process.env.OWNER_MODE = "true";

    // 데스크톱은 라이선스 없이 시작한다(대표님 결정 2026-10-08) — 라이선스 키가 없으면 이 PC 전용 로컬 키를 쓴다.
    // 로컬 서버가 이 키로 에이전트 접속을 인증하도록 서버를 띄우기 전에 환경변수로 넘긴다.
    const agentKey = startCfg.license_key || ensureDesktopAgentKey();
    process.env.HAEHAN_DESKTOP_AGENT_KEY = agentKey;

    // 빠른 시작: 창부터 바로 띄우고(대기 화면), 서버는 뒤에서 준비한다.
    const startHidden = process.argv.includes("--hidden");
    if (!startHidden) {
      createMainWindow(agentKey, false, { deferLoad: true });
      stage("window-shown");
    }

    // 자동실행 여부는 electron.app 로그인아이템 레지스트리가 아니라 config.json 의 autoStart
    // 값으로 관리한다(isAutoStartEnabled/setAutoStartEnabled). 시작프로그램 폴더의
    // start_haehan_ai.ps1(전체 스택 런처)이 같은 값을 읽어 꺼져 있으면 기동을 건너뛴다.
    // 트레이 메뉴(TOGGLE_AUTO_LAUNCH)에서 켜고 끌 수 있다.

    // 권한 요청 기본 거부(Electron 공식 체크리스트 9번) — 카메라/마이크/알림 등 이
    // 앱은 필요로 하는 게 없으므로 명시적으로 전부 deny. 미설정 시 Electron 버전별
    // 기본 동작에 암묵적으로 의존하게 되던 것을 명시적으로 고정(2026-09-29
    // electron-verifier 검증 CONDITIONAL 대응). 웹뷰(persist:haehan)와 라이선스/유튜브
    // 창(defaultSession) 둘 다 적용.
    for (const s of [session.defaultSession, session.fromPartition("persist:haehan")]) {
      s.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
    }

    // webview 파티션의 Service Worker/캐시 정리 — 빌드 변경 시 옛 SW가 cache-first로
    // 깨진 자원을 서빙해 화면이 RSC 원문으로 깨지는 문제 방지. 쿠키(로그인)는 보존.
    const clearWebviewCache = async () => {
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
    };

    // ── 서버 두 개를 동시에 시작(빠른 시작) ───────────────────────────────────
    // UI 서버(Next)는 FastAPI 에 의존하지 않고 기동한다(주소는 환경변수로 고정) — 순서대로 기다리던
    // 것을 병렬로 바꿔 시작 시간을 줄인다. webview 캐시 정리도 함께.
    const timed = (name, p) => p.then((ok) => { stage(name, ok ? "ok" : "FAIL"); return ok; });
    const [serverReady, nextReady] = await Promise.all([
      timed("fastapi-ready", startFastAPIServer()),
      timed("next-ready", startNextServer()),
      clearWebviewCache(),
    ]);
    if (!serverReady) {
      failStartup(
        "서버 시작 실패",
        "Haehan AI 서버를 시작할 수 없습니다.\n" +
        "로그 파일(%APPDATA%\\Haehan AI\\logs\\fastapi.log)을 확인하세요."
      );
      return;
    }

    // ── CDP 브라우저: 온디맨드 ────────────────────────────────────────────────
    // 자동 시작/15초 워치독 제거(사용자 선택). CDP 창을 닫아도 다시 뜨지 않는다.
    // 브라우저가 필요한 작업이 들어오면 백엔드(web_connector._ensure_cdp_daemon)가
    // 그 시점에 CDP를 자동 기동하므로 기능 손실 없음. (startCdpBrowser 는 보존 —
    // 추후 명시적 요청 시 호출 가능)
    if (cdpWatchdogTimer) { clearInterval(cdpWatchdogTimer); cdpWatchdogTimer = null; }

    // 데스크톱 자동 세션: 시작할 때마다 등록된 owner 의 새 토큰을 받아 config(auth_token)에 보관한다(webview 가 이를 쿠키로 사용).
    // 첫 실행(사용자 없음)이면 옛 토큰만 지우고, Next 가 /setup(이름·이메일 등록)으로 보낸다. 실패해도 시작은 계속한다.
    try {
      const sessionState = await refreshDesktopSession(FASTAPI_PORT);
      console.log("[desktop-session]", sessionState);
    } catch (e) {
      console.warn("[desktop-session] 건너뜀:", e.message);
    }

    // config.json 이 손상·잠김이었다면(보존·복구한 내용) 한 번 알린다 — 기존 설정을 조용히 잃지 않도록(D6)
    const cfgWarnings = consumeConfigWarnings();
    if (cfgWarnings.length) {
      dialog.showMessageBox({
        type: "warning",
        title: "설정 파일 경고",
        message: "설정 파일에 문제가 있었습니다",
        detail: cfgWarnings.join("\n\n"),
      }).catch(() => {});
    }

    if (!nextReady) {
      failStartup(
        "UI 서버 시작 실패",
        "Haehan AI UI 서버를 시작할 수 없습니다.\n" +
        "로그 파일(%APPDATA%\\Haehan AI\\logs\\nextjs.log)을 확인하세요."
      );
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

    // 라이선스 입력 화면 없이 바로 시작(첫 실행이면 Next 가 /setup 으로 이름·이메일 등록을 안내 — B안)
    startAgent(agentKey);
    // 대기 화면으로 먼저 띄운 창이 있으면 본 화면만 열고, 없으면(자동시작 숨김 등) 새로 만든다
    if (!loadMainShell()) createMainWindow(agentKey, startHidden);
    stage("shell-loaded");
    createTray(isAutoStartEnabled());
    // 설치형이면 새 버전을 백그라운드로 확인·다운로드(본 화면이 뜬 뒤 지연 시작 — 시작 시간에 영향 없음)
    startAutoUpdate(getMainWindow);
    // 창이 뜬 뒤 백그라운드로 Claude 연결 확인(처음이면 동의 요청) — 시작을 막지 않는다
    if (!startHidden) setTimeout(() => syncClaudeOnStart().catch((e) => console.warn("[main] Claude 연결 확인 실패(무시):", e.message)), 5000);
    else syncClaudeOnStart().catch(() => {});

    // 창 표시/복원은 버스로 일원화 (showMainWindow 가 없으면 재생성까지 처리)
    app.on("activate", () => bus.emit(EVENTS.SHOW_WINDOW));
  });
}

// 시작 실패 처리: 사용자에게는 오류 창, 자동 점검(HAEHAN_E2E=1)에서는 창을 띄우지 않고 바로 종료
// (사람이 닫아야 하는 오류 창이 뜨면 점검 환경에서 앱이 끝나지 않아 다음 점검까지 막히던 문제).
function failStartup(title, body) {
  stage("startup-failed", title);
  if (process.env.HAEHAN_E2E === "1") {
    console.error(`[main] ${title}: ${body}`);
    // app.exit 은 before-quit 정리를 건너뛰므로, 먼저 띄운 서버를 직접 끈다(남으면 다음 실행에서 포트 3000·8401 충돌)
    try { stopNextServer(); } catch {}
    try { stopFastAPIServer(); } catch {}
    setTimeout(() => app.exit(1), 1500);
    return;
  }
  dialog.showErrorBox(title, body);
  app.quit();
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

// ── Claude(데스크톱·Code) MCP 연동 ─────────────────────────────────────────────
// 포터블 타깃은 실행마다 임시 폴더로 풀리므로 번들 MCP 를 userData\mcp\<빌드>\ 로 복사한 고정 경로를 등록한다.
// 등록·해제 로직은 lib/claude_mcp.js(시험 가능한 순수 IO 모듈). 여기서는 앱 경로와 사용자 동의 흐름만 잇는다.
function claudeCtx() {
  return {
    srcDir: path.join(process.resourcesPath, "mcp", "haehan-mcp"),
    userDataDir: app.getPath("userData"),
    version: app.getVersion(),
    buildVersion: claudeMcp.readBuildVersion(process.resourcesPath), // build-info.json 의 yyyymmdd-sha7 (없으면 앱 버전-exe크기)
    appDataDir: app.getPath("appData"),
    fastapiUrl: FASTAPI_URL,
  };
}

// 연결 상태가 바뀌면 화면(webview)의 Claude 연결 배지가 바로 다시 읽게 알린다(화면 버튼·트레이 어느 쪽이든).
// result 가 있으면 배지가 그 결과 문구를 화면 안에 보여 준다. 알릴 화면이 없으면 false.
function notifyClaudeChanged(result = null) {
  let sent = false;
  for (const wc of webContents.getAllWebContents()) {
    if (wc.getType() === "webview" && !wc.isDestroyed()) {
      wc.send("claude-status-changed", result);
      sent = true;
    }
  }
  return sent;
}

async function connectClaudeNow() {
  if (!app.isPackaged) return { ok: false, error: "dev_mode_unsupported", hint: "패키징된 앱에서만 지원합니다" };
  const r = await claudeMcp.connectClaude(claudeCtx());
  if (r.ok) patchConfig({ claude_mcp: { ...(loadConfig().claude_mcp || {}), connected: true, prompted: true, build_id: r.buildId, fastapi_url: FASTAPI_URL } });
  notifyClaudeChanged();
  return r;
}

function disconnectClaudeNow() {
  const r = claudeMcp.disconnectClaude(claudeCtx());
  if (r.ok) patchConfig({ claude_mcp: { ...(loadConfig().claude_mcp || {}), connected: false, prompted: true } });
  notifyClaudeChanged();
  return r;
}

// 결과는 Windows 기본 대화상자 대신 화면 안 배지로 보여 준다(대표님 지시 2026-10-08: 기본 창은 보기 좋지 않다).
// 화면이 없을 때(창을 아직 안 띄움)만 Windows 알림으로 대신한다.
function notifyClaudeResult(title, r) {
  const parts = [];
  if (r.desktop) parts.push(`Claude Desktop ${r.desktop.ok ? (r.desktop.changed === false ? "변경 없음" : "완료") : (r.desktop.error === "claude_desktop_not_found" ? "설치 안 됨" : "실패")}`);
  if (r.code) parts.push(`Claude Code ${r.code.ok ? (r.code.skipped ? "건너뜀" : r.code.changed === false ? "변경 없음" : "완료") : "실패"}`);
  const summary = { title, ok: !!r.ok, detail: parts.join(" · "), hint: r.ok ? "" : r.hint || "" };
  if (notifyClaudeChanged(summary)) return;
  new Notification({ title: r.ok ? `${title} 완료` : `${title} 실패`, body: [summary.detail, summary.hint].filter(Boolean).join("\n") }).show();
}

// 앱 시작 때: 이미 동의한 사용자는 새 빌드·주소 변경 시 조용히 갱신한다.
// 처음이면 따로 창을 띄우지 않는다 — 화면 배지가 "연결 / 나중에" 안내 카드를 보여 준다(prompted 가 false 인 동안).
async function syncClaudeOnStart() {
  if (!app.isPackaged) return;
  const ctx = claudeCtx();
  if (!fs.existsSync(path.join(ctx.srcDir, claudeMcp.EXE_NAME))) return;
  const st = loadConfig().claude_mcp || {};
  if (!st.connected) return;
  if (st.build_id === claudeMcp.buildId(ctx.srcDir, ctx.version, ctx.buildVersion) && st.fastapi_url === FASTAPI_URL) return;
  await connectClaudeNow();
}

ipcMain.handle("local-config:connect-claude", () => connectClaudeNow());
ipcMain.handle("local-config:disconnect-claude", () => disconnectClaudeNow());
ipcMain.handle("local-config:claude-status", () => {
  const st = loadConfig().claude_mcp || {};
  return { ...claudeMcp.claudeStatus({ ...claudeCtx(), exePath: undefined }), consented: !!st.connected, prompted: !!st.prompted };
});
// 안내 카드의 "나중에" — 다시 묻지 않는다(배지의 "연결" 버튼·트레이 메뉴로 언제든 연결 가능)
ipcMain.handle("local-config:claude-later", () => {
  patchConfig({ claude_mcp: { ...(loadConfig().claude_mcp || {}), prompted: true } });
  return { ok: true };
});
bus.on(EVENTS.CLAUDE_CONNECT, async () => notifyClaudeResult("Claude 연결", await connectClaudeNow()));
bus.on(EVENTS.CLAUDE_DISCONNECT, () => notifyClaudeResult("Claude 연결 해제", disconnectClaudeNow()));

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
