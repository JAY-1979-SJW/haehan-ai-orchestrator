/**
 * lib/agent.js — 로컬 CDP 에이전트(Python) 프로세스 관리
 * L3 Connectors 계층(저수준 프로세스 IO). 업무 로직 없음.
 */
const { app } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn, execSync } = require("child_process");
const { FASTAPI_URL, getEnabledSites } = require("./config");
const { writePid, clearPid, killPreviousFromPidFile, killTreeAndWait } = require("./pid_guard");

let agentProc = null;
let mcpAgentProc = null;
let mcpAgentStopRequested = false; // stopMcpAgent()가 의도적으로 부른 건지 구분(재기동 여부 판단용)
let mcpAgentRestartCount = 0;
let mcpAgentRestartTimer = null;
const MCP_AGENT_MAX_RESTARTS = 5; // 연속 크래시(예: 파이썬 없음) 시 무한 재시도 방지

function resolvePython() {
  // Windows py 런처로 프로젝트 고정 버전(3.14)을 우선 찾는다 — PATH의 "python"이
  // 다른 버전(예: 3.11)을 가리키면 requirements.txt로 설치한 패키지(예:
  // websocket-client)가 없어 조용히 실패한다(2026-09-28 Electron 셸 복원 후 재현·확인:
  // "python"이 3.11을 가리켜 local_agent.py가 websocket-client ImportError로 즉시 종료).
  if (process.platform === "win32") {
    try {
      execSync("py -3.14 --version", { stdio: "ignore" });
      return { cmd: "py", prefixArgs: ["-3.14"] };
    } catch {}
  }
  for (const p of ["python3.14", "python3", "python"]) {
    try { execSync(`"${p}" --version`, { stdio: "ignore" }); return { cmd: p, prefixArgs: [] }; } catch {}
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
    cmd = python.cmd;
    args = [...python.prefixArgs, agentScript];
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

  startMcpAgent();
}

// 설치본: resources/local-agent-ai/local-agent-ai.exe (PyInstaller 번들 = local_agent/agent.py).
// 2026-10-08 결함: 이 분기가 아무것도 띄우지 않고 건너뛰어져 설치 앱의 AI 작업 콘솔이 항상 "연결된 로컬 에이전트가 없습니다"(503)였다.
// 서버와 같은 원칙 — 데이터는 userData 아래, 부모(앱)가 사라지면 스스로 종료(HAEHAN_PARENT_PID), PID 를 기록해 비정상 종료 뒤 남은 것을 다음 실행이 정리.
function startPackagedMcpAgent() {
  const exePath = path.join(process.resourcesPath, "local-agent-ai", "local-agent-ai.exe");
  if (!fs.existsSync(exePath)) {
    console.error("[mcp-agent] local-agent-ai.exe 없음:", exePath);
    return;
  }
  const prev = killPreviousFromPidFile("mcp-agent");
  if (prev.killed) console.log("[mcp-agent] 이전 실행의 에이전트를 정리했다 (PID %d)", prev.pid);

  const dataRoot = app.getPath("userData");
  const logDir = path.join(dataRoot, "logs");
  const agentDir = path.join(dataRoot, "agent");
  fs.mkdirSync(logDir, { recursive: true });
  fs.mkdirSync(agentDir, { recursive: true });
  const logStream = fs.createWriteStream(path.join(logDir, "local-agent-ai.log"), { flags: "a" });

  console.log("[mcp-agent] 시작(auto-connect, 번들):", exePath);
  const proc = spawn(exePath, ["--auto-connect", "--server", FASTAPI_URL], {
    cwd: path.dirname(exePath),
    detached: false,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      HAEHAN_AGENT_WS_ENABLED: "true",
      HAEHAN_AGENT_SERVER: FASTAPI_URL,
      HAEHAN_PARENT_PID: String(process.pid), // 앱이 강제 종료돼도 에이전트가 고아로 남지 않게
      HAEHAN_DATA_ROOT: dataRoot,
      HAEHAN_DATA_DIR: path.join(dataRoot, "data"),
      // 등록 정보(agent_id·서버 주소)는 이 userData 전용 — 다른 프로필/점검 실행과 섞이지 않게(토큰은 Windows 자격증명 저장소)
      HAEHAN_AGENT_DESKTOP_CONFIG: path.join(agentDir, "config.json"),
      HAEHAN_AGENT_TOKEN_DIR: path.join(agentDir, "tokens"),
      PYTHONUTF8: "1",
      PYTHONIOENCODING: "utf-8",
    },
  });
  mcpAgentProc = proc;
  writePid("mcp-agent", proc.pid, path.basename(exePath));
  proc.stdout.pipe(logStream, { end: false });
  proc.stderr.pipe(logStream, { end: false });
  wireMcpAgentLifecycle(proc, () => { clearPid("mcp-agent", proc.pid); logStream.end(); });
}

// 2026-09-29 추가: 앱 내 "AI 상담"(run_claude_agent, MCP)이 실제 동작하려면
// local_agent/agent.py(--auto-connect, /api/v1/local-agents/ws 대상)가 상시 연결돼
// 있어야 한다. 이건 위 agentProc(scripts/local_agent.py, 스마트스토어 전용 구
// 에이전트, /api/v1/smartstore/agent/ws 대상)와는 완전히 별개 프로세스·별개 서버
// 엔드포인트다 — 사용자가 매번 터미널에서 수동으로 등록·기동해야 했던 걸 자동화한다.
// --auto-connect: 미등록이면 등록코드 자동 발급+등록(AUTH_ENABLED=False 로컬 개발
// 서버 전제, ai_orchestrator/gates/auth.py 확인) 후 WebSocket 기동, 이미 등록돼
// 있으면(keyring) 바로 연결 — 자체 재시도 루프 내장(5초 간격, local_agent/agent.py).
function startMcpAgent() {
  stopMcpAgent();
  mcpAgentStopRequested = false;

  if (app.isPackaged) {
    startPackagedMcpAgent();
    return;
  }

  const python = resolvePython();
  if (!python) { console.error("[mcp-agent] Python을 찾을 수 없습니다"); return; }
  const scriptDir = path.join(__dirname, "..", "..", "..");

  console.log("[mcp-agent] 시작(auto-connect):", python.cmd);
  mcpAgentProc = spawn(python.cmd, [
    ...python.prefixArgs, "-m", "local_agent.agent",
    "--auto-connect",
    "--server", FASTAPI_URL,
  ], {
    cwd: scriptDir,
    detached: false,
    windowsHide: true,
    env: { ...process.env, HAEHAN_AGENT_WS_ENABLED: "true" },
  });

  mcpAgentProc.stdout.on("data", (d) => console.log("[mcp-agent]", d.toString().trim()));
  mcpAgentProc.stderr.on("data", (d) => console.error("[mcp-agent]", d.toString().trim()));
  wireMcpAgentLifecycle(mcpAgentProc, () => {});
}

// 종료 감시·재기동(개발/설치본 공통). 60초 이상 살아 있으면 "안정적으로 떴다"로 보고 재시도 카운터를 리셋 —
// 어쩌다 한 번 크래시가 이후의 진짜 영구 실패(파이썬/exe 없음 등) 감지를 방해하지 않게 한다.
function wireMcpAgentLifecycle(proc, onExit) {
  const stableTimer = setTimeout(() => {
    if (mcpAgentProc === proc) mcpAgentRestartCount = 0;
  }, 60000);

  proc.on("exit", (code) => {
    clearTimeout(stableTimer);
    onExit();
    console.log("[mcp-agent] 종료:", code);
    if (mcpAgentProc === proc) mcpAgentProc = null;

    // 2026-09-30 추가: 이 프로세스가 죽어도 기존엔 재기동 로직이 없어 Electron을 통째로
    // 재시작해야만 MCP 파이프라인(버튼→AI 채팅→헤드리스 claude -p)이 복구됐다
    // (docs/defect_index.json — 세션 내 FastAPI 재기동 등으로 실제 재현·확인).
    // stopMcpAgent()로 의도적으로 멈춘 경우(앱 종료 등)는 재기동하지 않는다.
    if (mcpAgentStopRequested || proc.haehanStopped) return; // 의도적으로 멈춘 프로세스(이 프로세스 자체의 표지)
    if (mcpAgentRestartCount >= MCP_AGENT_MAX_RESTARTS) {
      console.error(`[mcp-agent] ${MCP_AGENT_MAX_RESTARTS}회 연속 재기동 실패 — 자동 재시도 중단`);
      return;
    }
    mcpAgentRestartCount += 1;
    const delayMs = Math.min(3000 * mcpAgentRestartCount, 15000); // 3s,6s,9s,12s,15s 백오프
    console.log(`[mcp-agent] ${delayMs}ms 후 재기동 시도 (${mcpAgentRestartCount}/${MCP_AGENT_MAX_RESTARTS})`);
    clearTimeout(mcpAgentRestartTimer);
    mcpAgentRestartTimer = setTimeout(() => {
      if (!mcpAgentStopRequested) startMcpAgent();
    }, delayMs);
  });
}

/** 에이전트 프로세스 트리를 종료하고 끝날 때까지 기다리는 Promise (앱 종료가 기다려야 고아가 안 남는다). */
function stopMcpAgent() {
  mcpAgentStopRequested = true;
  clearTimeout(mcpAgentRestartTimer);
  const proc = mcpAgentProc;
  mcpAgentProc = null;
  if (proc) proc.haehanStopped = true;
  return killTreeAndWait(proc);
}

function stopAgent() {
  const mcp = stopMcpAgent();
  const proc = agentProc;
  agentProc = null;
  return Promise.all([mcp, killTreeAndWait(proc)]);
}

module.exports = { startAgent, stopAgent };
