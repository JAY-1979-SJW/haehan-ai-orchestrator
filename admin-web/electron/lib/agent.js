/**
 * lib/agent.js — 로컬 CDP 에이전트(Python) 프로세스 관리
 * L3 Connectors 계층(저수준 프로세스 IO). 업무 로직 없음.
 */
const { app } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn, execSync } = require("child_process");
const { FASTAPI_URL, getEnabledSites } = require("./config");

let agentProc = null;

function resolvePython() {
  const candidates = ["python", "python3"];
  for (const p of candidates) {
    try { execSync(`"${p}" --version`, { stdio: "ignore" }); return p; } catch {}
  }
  return null;
}

function startAgent(licenseKey) {
  stopAgent();

  let cmd, args, cwd;

  if (app.isPackaged) {
    // 패키징: local-agent.exe 사용 (Python 런타임 포함 번들)
    const exePath = path.join(process.resourcesPath, "local-agent", "local-agent.exe");
    if (!fs.existsSync(exePath)) {
      console.error("[agent] local-agent.exe 없음:", exePath);
      return;
    }
    cmd = exePath;
    args = [];
    cwd = path.join(process.resourcesPath, "local-agent");
  } else {
    // 개발: Python + local_agent.py
    const python = resolvePython();
    if (!python) { console.error("[agent] Python을 찾을 수 없습니다"); return; }
    const scriptDir = path.join(__dirname, "..", "..", "..");
    const agentScript = path.join(scriptDir, "scripts", "local_agent.py");
    if (!fs.existsSync(agentScript)) {
      console.error("[agent] local_agent.py 없음:", agentScript);
      return;
    }
    cmd = python;
    args = [agentScript];
    cwd = scriptDir;
  }

  // 사용자가 켠 사이트만 에이전트에 활성(비면 제한 없음 — 기존/owner 보존). P1-4
  const enabledSites = getEnabledSites().join(",");

  console.log("[agent] 시작:", cmd, enabledSites ? `(사이트: ${enabledSites})` : "(사이트 제한 없음)");
  agentProc = spawn(cmd, [
    ...args,
    "--license", licenseKey,
    "--server", FASTAPI_URL.replace("https://", "wss://").replace("http://", "ws://"),
    "--parent-pid", String(process.pid),
    "--enabled-sites", enabledSites,
  ], { cwd, detached: false, windowsHide: true });

  agentProc.stdout.on("data", (d) => console.log("[agent]", d.toString().trim()));
  agentProc.stderr.on("data", (d) => console.error("[agent]", d.toString().trim()));
  agentProc.on("exit", (code) => { console.log("[agent] 종료:", code); agentProc = null; });
}

function stopAgent() {
  if (!agentProc) return;
  const pid = agentProc.pid;
  try {
    if (process.platform === "win32" && pid) {
      // Windows: 자식 프로세스 트리까지 강제 종료 (kill()은 트리 미정리)
      execSync(`taskkill /pid ${pid} /T /F`, { stdio: "ignore" });
    } else {
      agentProc.kill();
    }
  } catch {
    try { agentProc.kill(); } catch {}
  }
  agentProc = null;
}

module.exports = { startAgent, stopAgent };
