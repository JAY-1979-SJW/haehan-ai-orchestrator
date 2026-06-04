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

  const ok = await waitCdp(15000);
  if (!ok) console.error("[cdp] Chrome CDP 응답 타임아웃");
  else minimizeCdpWindow();  // 백그라운드: CDP 준비 후 우리 창만 최소화(로그인 필요 시 복원)
  return ok;
}

/** CDP 크롬 창을 백그라운드로 최소화 (우리 PID의 창만, 사용자 다른 크롬엔 영향 없음). */
function minimizeCdpWindow() {
  if (process.platform !== "win32" || !chromePid) return;
  // 우리가 띄운 chrome.exe 의 자식 포함, 해당 PID 트리의 MainWindowHandle 만 최소화(6=SW_MINIMIZE)
  const ps =
    "$ErrorActionPreference='SilentlyContinue';" +
    "Add-Type -Name U -Namespace W -MemberDefinition '[DllImport(\"user32.dll\")] public static extern bool ShowWindowAsync(System.IntPtr h,int n);';" +
    `$ids=@(${chromePid}); ` +
    `Get-CimInstance Win32_Process -Filter \"ParentProcessId=${chromePid}\" | ForEach-Object { $ids+=$_.ProcessId };` +
    "Get-Process -Id $ids -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object { [W.U]::ShowWindowAsync($_.MainWindowHandle,6) | Out-Null }";
  try {
    require("child_process").exec(`powershell -NoProfile -WindowStyle Hidden -Command "${ps}"`, () => {});
  } catch (_) { /* best-effort */ }
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
