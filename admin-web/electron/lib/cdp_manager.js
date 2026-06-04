/**
 * lib/cdp_manager.js — 번들 Chromium을 CDP 모드로 자동 시작
 *
 * 패키징 환경: resources/server/haehan-server/_internal/chromium/chrome-win64/chrome.exe 사용
 * 개발 환경:   시스템 Chrome 또는 이미 실행 중인 CDP 사용
 *
 * L3 Connectors 계층. 업무 로직 없음.
 */
const { app } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const http = require("http");

const CDP_PORT = 9222;
const CDP_HOST = "127.0.0.1";

let chromePid = null;

function resolveChromeExe() {
  if (app.isPackaged) {
    const bundled = path.join(
      process.resourcesPath,
      "server", "haehan-server", "_internal", "chromium", "chrome-win64", "chrome.exe"
    );
    if (fs.existsSync(bundled)) return bundled;
  }
  // 시스템 Chrome 후보
  const candidates = [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    path.join(process.env.LOCALAPPDATA || "", "Google", "Chrome", "Application", "chrome.exe"),
  ];
  return candidates.find(fs.existsSync) || null;
}

function isCdpAlive() {
  return new Promise((resolve) => {
    const req = http.get(`http://${CDP_HOST}:${CDP_PORT}/json/version`, { timeout: 2000 }, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

async function waitCdp(timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isCdpAlive()) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

function resolveProfileDir() {
  // 단일 출처: HAEHAN_CDP_PROFILE 가 있으면 dev/packaged 무관 최우선.
  // (앱·cdp_force_start.py·cdp_daemon.py 가 동일 프로필을 공유 → 상시 로그인 보장)
  if (process.env.HAEHAN_CDP_PROFILE) {
    return process.env.HAEHAN_CDP_PROFILE;
  }
  if (!app.isPackaged) {
    // 개발: 프로젝트 data/cdp_profile 사용 (세션 공유)
    return path.join(__dirname, "..", "..", "..", "data", "cdp_profile", "ai_chrome");
  }
  // 패키징: userData 기준
  return path.join(app.getPath("userData"), "cdp_profile", "ai_chrome");
}

/**
 * CDP Chrome 시작. 이미 실행 중이면 스킵.
 * @returns {Promise<boolean>}
 */
async function startCdpBrowser() {
  if (await isCdpAlive()) {
    console.log("[cdp] 이미 실행 중");
    return true;
  }

  const chromeExe = resolveChromeExe();
  if (!chromeExe) {
    console.warn("[cdp] Chrome 실행 파일 없음 — CDP 브라우저 수동 실행 필요");
    return false;
  }

  const profileDir = resolveProfileDir();
  fs.mkdirSync(profileDir, { recursive: true });

  console.log("[cdp] Chrome 시작:", chromeExe);
  const proc = spawn(chromeExe, [
    `--remote-debugging-port=${CDP_PORT}`,
    "--remote-allow-origins=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001",
    `--user-data-dir=${profileDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-session-crashed-bubble",
    "--hide-crash-restore-bubble",
    "--window-size=1100,800",
  ], {
    detached: true,
    stdio: "ignore",
  });
  proc.unref();
  chromePid = proc.pid;
  console.log("[cdp] Chrome PID:", chromePid);

  // 창이 뜨자마자 즉시·반복 최소화 → 백그라운드(보이는 플래시 최소화).
  // 사용자가 닫아 watchdog가 재기동해도 화면에 뜨지 않고 백그라운드로 들어감.
  minimizeCdpWindow(5000);

  const ok = await waitCdp(15000);
  if (!ok) { console.error("[cdp] Chrome CDP 응답 타임아웃"); return ok; }
  // 세션 복원된 여분 탭 정리(탭 1개만 유지)
  await closeExtraTabs();
  minimizeCdpWindow(2000);  // 탭 정리 후 한 번 더(로그인 필요 시 자동화가 bring_to_front)
  return ok;
}

/** CDP HTTP GET → JSON (실패 시 null). */
function httpGetJson(p) {
  return new Promise((resolve) => {
    const req = http.get(`http://${CDP_HOST}:${CDP_PORT}${p}`, { timeout: 3000 }, (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => { try { resolve(JSON.parse(data)); } catch { resolve(null); } });
    });
    req.on("error", () => resolve(null));
    req.on("timeout", () => { req.destroy(); resolve(null); });
  });
}

/** 세션 복원으로 열린 여분 탭을 닫아 page 탭 1개만 유지(쿠키/로그인은 프로필에 보존). */
async function closeExtraTabs() {
  try {
    const list = await httpGetJson("/json/list");
    if (!Array.isArray(list)) return;
    const pages = list.filter((t) => t.type === "page");
    for (let i = 1; i < pages.length; i++) {
      await new Promise((resolve) => {
        const req = http.get(`http://${CDP_HOST}:${CDP_PORT}/json/close/${pages[i].id}`, { timeout: 3000 }, () => resolve());
        req.on("error", () => resolve());
        req.on("timeout", () => { req.destroy(); resolve(); });
      });
    }
    if (pages.length > 1) console.log(`[cdp] 여분 탭 ${pages.length - 1}개 정리`);
  } catch (_) { /* best-effort */ }
}

/** CDP 크롬 창을 백그라운드로 최소화. --remote-debugging-port 마커로 우리 Chrome을
 * 직접 찾아 최소화(PID 트리 의존 X — spawn PID가 죽어도 동작). 사용자 다른 크롬엔 영향 없음.
 * 창이 뜨자마자 잡게 durationMs 동안 300ms 간격 반복(플래시 최소화). */
function minimizeCdpWindow(durationMs = 4000) {
  if (process.platform !== "win32") return;
  const ps =
    "$ErrorActionPreference='SilentlyContinue';" +
    "Add-Type -Name U -Namespace W -MemberDefinition '[DllImport(\"user32.dll\")] public static extern bool ShowWindowAsync(System.IntPtr h,int n);';" +
    `Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*--remote-debugging-port=${CDP_PORT}*' } | ForEach-Object { ` +
    "$p=Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue; if($p -and $p.MainWindowHandle -ne 0){ [W.U]::ShowWindowAsync($p.MainWindowHandle,6) | Out-Null } }";
  const deadline = Date.now() + durationMs;
  const tick = () => {
    if (Date.now() > deadline) return;
    try {
      require("child_process").exec(`powershell -NoProfile -WindowStyle Hidden -Command "${ps}"`, () => {});
    } catch (_) { /* ignore */ }
    setTimeout(tick, 300);
  };
  tick();
}

function stopCdpBrowser() {
  if (chromePid) {
    try {
      process.kill(chromePid);
    } catch {}
    chromePid = null;
  }
}

module.exports = { startCdpBrowser, stopCdpBrowser, isCdpAlive };
