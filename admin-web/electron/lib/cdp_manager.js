/**
 * lib/cdp_manager.js — Chrome을 CDP 모드로 자동 시작
 *
 * 프로필 전략 (우선순위):
 *   1. HAEHAN_CDP_PROFILE 환경변수 — 명시 지정
 *   2. USE_SYSTEM_CHROME_PROFILE=true — 사용자 실제 Chrome 프로필 사용 (모든 로그인 세션 공유)
 *   3. 기본 — 앱 전용 분리 프로필
 *
 * USE_SYSTEM_CHROME_PROFILE=true 일 때:
 *   - 기존 Chrome 프로세스를 graceful 종료 후 CDP 모드로 재실행
 *   - 사용자가 Chrome에 로그인해 둔 모든 세션(네이버·스마트스토어 등) 그대로 유지
 *
 * L3 Connectors 계층. 업무 로직 없음.
 */
const { app } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn, execFile, execSync } = require("child_process");
const http = require("http");

const CDP_PORT = 9222;
const CDP_HOST = "127.0.0.1";

let chromePid = null;
let chromeLaunching = false;

// ── Chrome 실행파일 탐색 ─────────────────────────────────────────────────────

function resolveChromeExe(isSystem = false) {
  // 시스템 Chrome 프로필 사용 모드: 시스템 Chrome exe 우선 (버전 호환 보장)
  const systemCandidates = [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    path.join(process.env.LOCALAPPDATA || "", "Google", "Chrome", "Application", "chrome.exe"),
  ];
  if (isSystem) {
    const sysExe = systemCandidates.find(fs.existsSync);
    if (sysExe) return sysExe;
    // 시스템 Chrome 없으면 번들 Chromium fallback
  }
  // 번들 Chromium (패키징 앱)
  if (app.isPackaged) {
    const bundled = path.join(
      process.resourcesPath,
      "server", "haehan-server", "_internal", "chromium", "chrome-win64", "chrome.exe"
    );
    if (fs.existsSync(bundled)) return bundled;
  }
  return systemCandidates.find(fs.existsSync) || null;
}

// ── 프로필 경로 결정 ─────────────────────────────────────────────────────────

function resolveProfileDir() {
  // 1순위: 명시 환경변수
  if (process.env.HAEHAN_CDP_PROFILE) {
    // 환경변수 경로가 실제 시스템 Chrome 프로필 경로인지 판정
    // → isSystem=true 여야 closeExistingChrome() 이 호출되어 프로필 잠금 해제됨
    const sysProfile = resolveSystemChromeProfile();
    const isSystem = sysProfile
      ? process.env.HAEHAN_CDP_PROFILE.toLowerCase() === sysProfile.toLowerCase()
      : false;
    return { dir: process.env.HAEHAN_CDP_PROFILE, isSystem };
  }
  // 2순위: 사용자 Chrome 프로필 사용 모드
  if (process.env.USE_SYSTEM_CHROME_PROFILE === "true" || _loadConfig().useSystemChromeProfile) {
    const systemProfile = resolveSystemChromeProfile();
    if (systemProfile) {
      console.log("[cdp] 시스템 Chrome 프로필 사용:", systemProfile);
      return { dir: systemProfile, isSystem: true };
    }
    console.warn("[cdp] 시스템 Chrome 프로필 없음 — 앱 전용 프로필로 대체");
  }
  // 3순위: 앱 전용 프로필
  if (!app.isPackaged) {
    return { dir: path.join(__dirname, "..", "..", "..", "data", "cdp_profile", "ai_chrome"), isSystem: false };
  }
  return { dir: path.join(app.getPath("userData"), "cdp_profile", "ai_chrome"), isSystem: false };
}

/** 사용자 실제 Chrome 프로필 Default 경로 반환. */
function resolveSystemChromeProfile() {
  const base = path.join(process.env.LOCALAPPDATA || "", "Google", "Chrome", "User Data");
  if (fs.existsSync(base)) return base;
  // Canary
  const canary = path.join(process.env.LOCALAPPDATA || "", "Google", "Chrome SxS", "User Data");
  if (fs.existsSync(canary)) return canary;
  return null;
}

/** config.json 에서 설정 로드 (없으면 기본값). */
function _loadConfig() {
  try {
    const cfgPath = path.join(app.getPath("userData"), "config.json");
    if (fs.existsSync(cfgPath)) {
      return JSON.parse(fs.readFileSync(cfgPath, "utf8"));
    }
  } catch (_) {}
  return {};
}

// ── 기존 Chrome 종료 ─────────────────────────────────────────────────────────

/**
 * 시스템 Chrome 프로필을 쓸 때: 기존 Chrome 인스턴스를 graceful 종료.
 * Chrome이 정상 종료되어야 쿠키/세션이 디스크에 플러시됨.
 */
async function closeExistingChrome(profileDir) {
  if (process.platform !== "win32") return;
  console.log("[cdp] 기존 Chrome 종료 시도...");
  try {
    // 해당 프로필을 쓰는 Chrome 프로세스만 graceful 종료
    const ps =
      `$procs = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | ` +
      `Where-Object { $_.CommandLine -like '*${profileDir.replace(/\\/g, "\\\\")}*' -and $_.CommandLine -notlike '*--remote-debugging-port*' }; ` +
      `foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -ErrorAction SilentlyContinue }`;
    execSync(`powershell -NoProfile -WindowStyle Hidden -Command "${ps}"`, { timeout: 5000 });
    // 완전 종료 대기
    await new Promise((r) => setTimeout(r, 2000));
  } catch (_) {}

  // 혹시 CDP 포트가 살아있는 Chrome(다른 프로필)은 건드리지 않음
  console.log("[cdp] 기존 Chrome 종료 완료");
}

// ── CDP 상태 확인 ────────────────────────────────────────────────────────────

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

// ── Chrome 시작 ──────────────────────────────────────────────────────────────

async function startCdpBrowser() {
  if (await isCdpAlive()) {
    console.log("[cdp] 이미 실행 중");
    return true;
  }
  if (chromeLaunching) {
    console.log("[cdp] 기동 중 — 중복 실행 생략, CDP 대기");
    return await waitCdp(15000);
  }
  chromeLaunching = true;
  try {
    return await _doStartCdp();
  } finally {
    chromeLaunching = false;
  }
}

async function _doStartCdp() {
  const { dir: profileDir, isSystem } = resolveProfileDir();
  const chromeExe = resolveChromeExe(isSystem);
  if (!chromeExe) {
    console.warn("[cdp] Chrome 실행 파일 없음 — CDP 브라우저 수동 실행 필요");
    return false;
  }

  // 시스템 Chrome 프로필 사용 시: 기존 Chrome 먼저 종료 (프로필 잠금 해제)
  if (isSystem) {
    await closeExistingChrome(profileDir);
  } else {
    fs.mkdirSync(profileDir, { recursive: true });
  }

  console.log("[cdp] Chrome 시작:", chromeExe, "| 프로필:", profileDir, isSystem ? "(시스템)" : "(앱전용)");

  const args = [
    `--remote-debugging-port=${CDP_PORT}`,
    "--remote-allow-origins=*",
    `--user-data-dir=${profileDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-session-crashed-bubble",
    "--hide-crash-restore-bubble",
  ];

  // 시스템 프로필 모드: 창 표시 (사용자가 직접 쓰는 Chrome이므로 최소화 안 함)
  if (!isSystem) {
    args.push("--window-size=1100,800");
  }

  const proc = spawn(chromeExe, args, {
    detached: true,
    stdio: "ignore",
    windowsHide: isSystem ? false : true,
  });
  proc.unref();
  chromePid = proc.pid;
  console.log("[cdp] Chrome PID:", chromePid);

  if (!isSystem) {
    minimizeCdpWindow(5000);
  }

  const ok = await waitCdp(15000);
  if (!ok) { console.error("[cdp] Chrome CDP 응답 타임아웃"); return false; }

  if (!isSystem) {
    await closeExtraTabs();
    minimizeCdpWindow(2000);
  }
  return true;
}

// ── 유틸 ─────────────────────────────────────────────────────────────────────

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
  } catch (_) {}
}

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
      execFile("powershell", ["-NoProfile", "-WindowStyle", "Hidden", "-Command", ps], { windowsHide: true }, () => {});
    } catch (_) {}
    setTimeout(tick, 300);
  };
  tick();
}

function stopCdpBrowser() {
  if (chromePid) {
    try {
      if (process.platform === "win32") {
        // Windows: 자식 프로세스 트리까지 강제 종료 (process.kill() 은 트리 미정리 —
        // agent.js 와 동일한 이유). 렌더러/GPU 자식이 고아로 남는 것 방지.
        execSync(`taskkill /pid ${chromePid} /T /F`, { stdio: "ignore" });
      } else {
        process.kill(chromePid);
      }
    } catch {
      try { process.kill(chromePid); } catch {}
    }
    chromePid = null;
  }
}

/**
 * 시스템 Chrome 프로필 사용 여부를 config.json에 저장.
 * @param {boolean} enable
 */
function setUseSystemChromeProfile(enable) {
  try {
    const cfgPath = path.join(app.getPath("userData"), "config.json");
    const cfg = fs.existsSync(cfgPath) ? JSON.parse(fs.readFileSync(cfgPath, "utf8")) : {};
    cfg.useSystemChromeProfile = enable;
    fs.writeFileSync(cfgPath, JSON.stringify(cfg, null, 2));
    console.log("[cdp] useSystemChromeProfile =", enable);
  } catch (e) {
    console.error("[cdp] config 저장 실패:", e);
  }
}

module.exports = {
  startCdpBrowser,
  stopCdpBrowser,
  isCdpAlive,
  setUseSystemChromeProfile,
  resolveSystemChromeProfile,
};
