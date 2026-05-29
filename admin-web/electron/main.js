/**
 * Haehan AI Desktop — 통제형 SaaS 클라이언트
 * - 라이선스 키 입력 (1회)
 * - 로컬 CDP 에이전트 자동 시작 (Python)
 * - 서버 UI 표시
 */
const { app, BrowserWindow, Menu, Tray, ipcMain, shell, dialog } = require("electron");
const path  = require("path");
const fs    = require("fs");
const { spawn, execSync } = require("child_process");

// 상단 메뉴바 완전 제거
Menu.setApplicationMenu(null);

// ── 설정 ─────────────────────────────────────────────────────────────────────
const SERVER_URL  = "http://localhost:3000";
const CONFIG_PATH = path.join(app.getPath("userData"), "config.json");

function loadConfig() {
  try {
    if (fs.existsSync(CONFIG_PATH)) return JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
  } catch {}
  return {};
}

function saveConfig(cfg) {
  fs.mkdirSync(path.dirname(CONFIG_PATH), { recursive: true });
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
}

// ── 로컬 에이전트 프로세스 ────────────────────────────────────────────────────
let agentProc = null;

function startAgent(licenseKey) {
  if (agentProc) { agentProc.kill(); agentProc = null; }

  // Python 경로 탐색
  const pythonCandidates = ["python", "python3",
    path.join(process.resourcesPath, "python", "python.exe"),   // 번들된 Python
  ];

  let python = null;
  for (const p of pythonCandidates) {
    try { execSync(`"${p}" --version`, { stdio: "ignore" }); python = p; break; } catch {}
  }

  if (!python) {
    console.error("[agent] Python을 찾을 수 없습니다");
    return;
  }

  // 개발: __dirname은 electron/ 안 → 3단계 상위가 프로젝트 루트
  // 패키징: process.resourcesPath 아래에 scripts/ 를 번들링
  const scriptDir = app.isPackaged
    ? process.resourcesPath
    : path.join(__dirname, "..", "..", "..");
  const agentScript = path.join(scriptDir, "scripts", "local_agent.py");

  if (!fs.existsSync(agentScript)) {
    console.error("[agent] local_agent.py를 찾을 수 없습니다:", agentScript);
    return;
  }

  console.log("[agent] 시작:", python, agentScript);
  agentProc = spawn(python, [
    agentScript,
    "--license", licenseKey,
    "--server",  SERVER_URL.replace("https://", "wss://").replace("http://", "ws://"),
  ], { cwd: scriptDir, detached: false });

  agentProc.stdout.on("data", (d) => console.log("[agent]", d.toString().trim()));
  agentProc.stderr.on("data", (d) => console.error("[agent]", d.toString().trim()));
  agentProc.on("exit", (code) => { console.log("[agent] 종료:", code); agentProc = null; });
}

// ── 라이선스 입력 창 ──────────────────────────────────────────────────────────
function createLicenseWindow() {
  const win = new BrowserWindow({
    width: 460, height: 320,
    resizable: false,
    title: "Haehan AI — 라이선스 입력",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; font-family: -apple-system, 'Malgun Gothic', sans-serif; margin: 0; }
  body { background: #F9FAFB; display: flex; align-items: center; justify-content: center; height: 100vh; }
  .card { background: white; border: 1px solid #E5E7EB; border-radius: 16px; padding: 32px; width: 380px; }
  h1 { font-size: 18px; font-weight: 700; color: #111827; margin-bottom: 4px; }
  p  { font-size: 13px; color: #6B7280; margin-bottom: 24px; }
  label { font-size: 12px; font-weight: 600; color: #374151; display: block; margin-bottom: 6px; }
  input { width: 100%; padding: 10px 12px; border: 1px solid #E5E7EB; border-radius: 8px; font-size: 14px;
          font-family: monospace; outline: none; }
  input:focus { border-color: #F97316; box-shadow: 0 0 0 3px rgba(249,115,22,0.15); }
  button { width: 100%; margin-top: 16px; padding: 11px; background: #F97316; color: white;
           border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; }
  button:hover { background: #EA580C; }
  .err { color: #DC2626; font-size: 12px; margin-top: 8px; display: none; }
  .accent { color: #F97316; }
</style>
</head>
<body>
<div class="card">
  <h1>Haehan <span class="accent">AI</span></h1>
  <p>운영자로부터 받은 라이선스 키를 입력하세요.</p>
  <label>라이선스 키</label>
  <input id="key" type="text" placeholder="xxxxxxxxxxxx" autocomplete="off" spellcheck="false" />
  <div class="err" id="err">유효하지 않은 라이선스 키입니다.</div>
  <button id="btn" onclick="submit()">시작하기</button>
</div>
<script>
document.getElementById('key').addEventListener('keydown', e => { if(e.key==='Enter') submit(); });
window.electronAPI.onLicenseError(() => {
  document.getElementById('err').style.display = 'block';
  document.getElementById('btn').textContent = '시작하기';
});
function submit() {
  const k = document.getElementById('key').value.trim();
  if (!k) return;
  document.getElementById('btn').textContent = '확인 중...';
  document.getElementById('err').style.display = 'none';
  window.electronAPI.submitLicense(k);
}
</script>
</body>
</html>
  `)}`);

  return win;
}

// ── YouTube OAuth 자동 로그인 ─────────────────────────────────────────────────
let youtubeOAuthWin = null;

function checkYouTubeToken() {
  const cfg = loadConfig();
  const tokenFile = cfg.youtube_token_file ||
    path.join(__dirname, "..", "..", "..", "ai_orchestrator", "storage", "secrets", "youtube_oauth_authorized_user.json");
  return fs.existsSync(tokenFile);
}

function startYouTubeOAuth(licenseKey) {
  return new Promise((resolve) => {
    // 서버에서 auth URL 가져오기
    const https = require("https");
    https.get(
      `${SERVER_URL}/api/v1/oauth/youtube/auth-url`,
      { headers: { "x-license-key": licenseKey } },
      (res) => {
        let data = "";
        res.on("data", (d) => data += d);
        res.on("end", () => {
          try {
            const json = JSON.parse(data);
            const authUrl = json.auth_url;
            if (!authUrl) { resolve(false); return; }
            openYouTubeOAuthPopup(authUrl, licenseKey, resolve);
          } catch { resolve(false); }
        });
      }
    ).on("error", () => resolve(false));
  });
}

function openYouTubeOAuthPopup(authUrl, licenseKey, resolve) {
  if (youtubeOAuthWin) { youtubeOAuthWin.close(); }

  youtubeOAuthWin = new BrowserWindow({
    width: 520, height: 680,
    title: "YouTube 계정 연결",
    webPreferences: { nodeIntegration: false, contextIsolation: true },
    parent: mainWindow, modal: true,
  });

  youtubeOAuthWin.loadURL(authUrl);

  // 콜백 URL 감지
  const CALLBACK_PREFIX = `${SERVER_URL}/api/v1/oauth/youtube/callback`;
  youtubeOAuthWin.webContents.on("will-navigate", (_, url) => handleCallback(url));
  youtubeOAuthWin.webContents.on("did-navigate", (_, url) => handleCallback(url));

  function handleCallback(url) {
    if (!url.startsWith(CALLBACK_PREFIX)) return;
    const code = new URL(url).searchParams.get("code");
    if (!code) { resolve(false); return; }
    youtubeOAuthWin.close();
    youtubeOAuthWin = null;

    // 서버에 코드 교환 요청
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

  const choice = await dialog.showMessageBox(mainWindow, {
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
      dialog.showMessageBox(mainWindow, {
        type: "info", title: "연결 완료",
        message: "YouTube 계정이 성공적으로 연결되었습니다.", buttons: ["확인"],
      });
    }
  }
}

// ── 메인 창 ───────────────────────────────────────────────────────────────────
let mainWindow = null;
let tray       = null;

function createMainWindow(licenseKey) {
  mainWindow = new BrowserWindow({
    width: 1280, height: 820,
    minWidth: 900, minHeight: 600,
    title: "Haehan AI",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webviewTag: true,           // shell.html의 <webview> 허용
    },
    show: false,
  });

  // shell.html에 서버 URL과 라이선스 키를 쿼리로 전달
  const shellPath = path.join(__dirname, "shell.html");
  const shellUrl  = `file://${shellPath}?server=${encodeURIComponent(SERVER_URL)}&license=${encodeURIComponent(licenseKey)}`;
  mainWindow.loadURL(shellUrl);
  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
    // 창 표시 후 YouTube OAuth 상태 확인 (2초 딜레이)
    setTimeout(() => ensureYouTubeAuth(licenseKey), 2000);
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(SERVER_URL)) shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.on("closed", () => { mainWindow = null; });
}

// ── 트레이 ────────────────────────────────────────────────────────────────────
function createTray() {
  const iconPath = path.join(__dirname, "icon.png");
  if (!fs.existsSync(iconPath)) return;
  tray = new Tray(iconPath);
  tray.setToolTip("Haehan AI");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "열기",   click: () => { if (mainWindow) mainWindow.show(); else createMainWindow(loadConfig().license_key || ""); } },
    { label: "YouTube 계정 재연결", click: () => {
      const key = loadConfig().license_key || "";
      if (mainWindow) ensureYouTubeAuth(key);
    }},
    { type: "separator" },
    { label: "종료",   click: () => app.quit() },
  ]));
  tray.on("double-click", () => { if (mainWindow) mainWindow.show(); });
}

// ── 앱 진입 ───────────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  // 이 PC에서 상시 자동 시작 등록
  app.setLoginItemSettings({ openAtLogin: true, openAsHidden: false });

  const cfg = loadConfig();

  if (cfg.license_key) {
    // 저장된 라이선스 있으면 바로 시작
    startAgent(cfg.license_key);
    createMainWindow(cfg.license_key);
    createTray();
  } else {
    // 라이선스 입력 창
    const licWin = createLicenseWindow();

    ipcMain.once("license-submit", async (_, key) => {
      // 서버에 라이선스 검증 요청
      try {
        const https = require("https");
        const res = await new Promise((resolve) => {
          const req = https.get(
            `${SERVER_URL}/api/v1/smartstore/admin/licenses/${encodeURIComponent(key)}/verify`,
            (r) => {
              let data = "";
              r.on("data", (d) => data += d);
              r.on("end", () => resolve(JSON.parse(data)));
            }
          );
          req.on("error", () => resolve({ ok: false }));
        });

        if (res.ok) {
          saveConfig({ license_key: key });
          licWin.close();
          startAgent(key);
          createMainWindow(key);
          createTray();
        } else {
          licWin.webContents.send("license-error");
        }
      } catch {
        licWin.webContents.send("license-error");
      }
    });
  }

  app.on("activate", () => { if (!mainWindow) createMainWindow(loadConfig().license_key || ""); });
});

// shell.html에서 YouTube 연결 요청
ipcMain.on("youtube-connect", async () => {
  const key = loadConfig().license_key || "";
  const ok = await startYouTubeOAuth(key);
  if (mainWindow) mainWindow.webContents.send("youtube-status", ok ? "connected" : "failed");
});

app.on("window-all-closed", () => { if (!tray) app.quit(); });

app.on("before-quit", () => {
  if (agentProc) { agentProc.kill(); agentProc = null; }
});

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) { app.quit(); }
else { app.on("second-instance", () => { if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus(); } }); }
