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

// 2026-09-29 추가: 앱 내 "AI 상담"(run_claude_agent, MCP)이 실제 동작하려면
// core/agent_runtime/agent.py(--auto-connect, /api/v1/local-agents/ws 대상)가 상시 연결돼
// 있어야 한다. 이건 위 agentProc(core/agent_runtime/runtime/local_agent.py, 스마트스토어 전용 구
// 에이전트, /api/v1/smartstore/agent/ws 대상)와는 완전히 별개 프로세스·별개 서버
// 엔드포인트다 — 사용자가 매번 터미널에서 수동으로 등록·기동해야 했던 걸 자동화한다.
// --auto-connect: 미등록이면 등록코드 자동 발급+등록(AUTH_ENABLED=False 로컬 개발
// 서버 전제, tools/gates/auth.py 확인) 후 WebSocket 기동, 이미 등록돼
// 있으면(keyring) 바로 연결 — 자체 재시도 루프 내장(5초 간격, core/agent_runtime/agent.py).
function startMcpAgent() {
  stopMcpAgent();
  mcpAgentStopRequested = false;

  if (app.isPackaged) {
    // 패키징 배포판에는 아직 core.agent_runtime.agent 전용 번들이 없다(별도 exe 빌드 파이프라인
    // 필요 — docs/specs/2026-09-28_cdp_universal_automation_and_mcp_trigger.md §10 참고).
    // 개발 모드에서만 자동 기동하고, 배포판은 다음 세션 후보로 남긴다.
    console.log("[mcp-agent] 패키징 빌드는 아직 미지원 — 개발 모드에서만 자동 기동");
    return;
  }

  const python = resolvePython();
  if (!python) { console.error("[mcp-agent] Python을 찾을 수 없습니다"); return; }
  const scriptDir = path.join(__dirname, "..", "..", "..");

  console.log("[mcp-agent] 시작(auto-connect):", python.cmd);
  mcpAgentProc = spawn(python.cmd, [
    ...python.prefixArgs, "-m", "core.agent_runtime.agent",
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

  const spawnedProc = mcpAgentProc;
  // 60초 이상 안 죽고 살아있으면 "안정적으로 떴다"로 보고 재시도 카운터 리셋 — 어쩌다 한 번
  // 크래시가 이후의 진짜 영구 실패(파이썬 없음 등) 감지를 방해하지 않게 함.
  const stableTimer = setTimeout(() => {
    if (mcpAgentProc === spawnedProc) mcpAgentRestartCount = 0;
  }, 60000);

  mcpAgentProc.on("exit", (code) => {
    clearTimeout(stableTimer);
    console.log("[mcp-agent] 종료:", code);
    mcpAgentProc = null;

    // 2026-09-30 추가: 이 프로세스가 죽어도 기존엔 재기동 로직이 없어 Electron을 통째로
    // 재시작해야만 MCP 파이프라인(버튼→AI 채팅→헤드리스 claude -p)이 복구됐다
    // (docs/defect_index.json — 세션 내 FastAPI 재기동 등으로 실제 재현·확인).
    // stopMcpAgent()로 의도적으로 멈춘 경우(앱 종료 등)는 재기동하지 않는다.
    if (mcpAgentStopRequested) return;
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

function stopMcpAgent() {
  mcpAgentStopRequested = true;
  clearTimeout(mcpAgentRestartTimer);
  if (!mcpAgentProc) return;
  const pid = mcpAgentProc.pid;
  try {
    if (process.platform === "win32" && pid) {
      execSync(`taskkill /pid ${pid} /T /F`, { stdio: "ignore" });
    } else {
      mcpAgentProc.kill();
    }
  } catch {
    try { mcpAgentProc.kill(); } catch {}
  }
  mcpAgentProc = null;
}

function stopAgent() {
  stopMcpAgent();
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
