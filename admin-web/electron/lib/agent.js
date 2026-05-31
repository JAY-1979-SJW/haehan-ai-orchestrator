/**
 * lib/agent.js — 로컬 CDP 에이전트(Python) 프로세스 관리
 * L3 Connectors 계층(저수준 프로세스 IO). 업무 로직 없음.
 */
const { app } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn, execSync } = require("child_process");
const { SERVER_URL } = require("./config");

let agentProc = null;

function resolvePython() {
  const candidates = ["python", "python3", path.join(process.resourcesPath, "python", "python.exe")];
  for (const p of candidates) {
    try { execSync(`"${p}" --version`, { stdio: "ignore" }); return p; } catch {}
  }
  return null;
}

function startAgent(licenseKey) {
  stopAgent();

  const python = resolvePython();
  if (!python) { console.error("[agent] Python을 찾을 수 없습니다"); return; }

  // 개발: __dirname=electron/lib → 4단계 상위가 프로젝트 루트
  // 패키징: process.resourcesPath 아래 scripts/ 번들
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
    "--server", SERVER_URL.replace("https://", "wss://").replace("http://", "ws://"),
  ], { cwd: scriptDir, detached: false });

  agentProc.stdout.on("data", (d) => console.log("[agent]", d.toString().trim()));
  agentProc.stderr.on("data", (d) => console.error("[agent]", d.toString().trim()));
  agentProc.on("exit", (code) => { console.log("[agent] 종료:", code); agentProc = null; });
}

function stopAgent() {
  if (agentProc) { agentProc.kill(); agentProc = null; }
}

module.exports = { startAgent, stopAgent };
