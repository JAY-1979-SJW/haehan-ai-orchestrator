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
const SERVER_URL  = "https://autowork.haehan-ai.kr";
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

  // 프로젝트 루트 기준 agent 스크립트
  const scriptDir = path.join(__dirname, "..", "..", "..");  // electron/ → admin-web/ → project root
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
    webPreferences: { nodeIntegration: true, contextIsolation: false },
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
const { ipcRenderer } = require('electron');
document.getElementById('key').addEventListener('keydown', e => { if(e.key==='Enter') submit(); });
ipcRenderer.on('license-error', () => {
  document.getElementById('err').style.display = 'block';
  document.getElementById('btn').textContent = '시작하기';
});
function submit() {
  const k = document.getElementById('key').value.trim();
  if (!k) return;
  document.getElementById('btn').textContent = '확인 중...';
  document.getElementById('err').style.display = 'none';
  ipcRenderer.send('license-submit', k);
}
</script>
</body>
</html>
  `)}`);

  return win;
}

// ── 메인 창 ───────────────────────────────────────────────────────────────────
let mainWindow = null;
let tray       = null;

function createMainWindow(licenseKey) {
  mainWindow = new BrowserWindow({
    width: 1280, height: 820,
    minWidth: 900, minHeight: 600,
    title: "Haehan AI",
    webPreferences: { nodeIntegration: false, contextIsolation: true },
    show: false,
  });

  // 라이선스 키를 쿼리로 전달 (채팅에서 사용)
  mainWindow.loadURL(`${SERVER_URL}/naver/smartstore?license=${encodeURIComponent(licenseKey)}`);
  mainWindow.once("ready-to-show", () => mainWindow.show());

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
    { type: "separator" },
    { label: "종료",   click: () => app.quit() },
  ]));
  tray.on("double-click", () => { if (mainWindow) mainWindow.show(); });
}

// ── 앱 진입 ───────────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  const cfg = loadConfig();

  if (cfg.license_key) {
    // 저장된 라이선스 있으면 바로 시작
    startAgent(cfg.license_key);
    createMainWindow(cfg.license_key);
    createTray();
  } else {
    // 라이선스 입력 창
    const licWin = createLicenseWindow();

    ipcMain.on("license-submit", async (_, key) => {
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

app.on("window-all-closed", () => { if (!tray) app.quit(); });

app.on("before-quit", () => {
  if (agentProc) { agentProc.kill(); agentProc = null; }
});

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) { app.quit(); }
else { app.on("second-instance", () => { if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus(); } }); }
