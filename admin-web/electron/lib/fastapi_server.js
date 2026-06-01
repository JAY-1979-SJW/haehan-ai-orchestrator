/**
 * lib/fastapi_server.js — 번들 FastAPI 서버 프로세스 관리
 *
 * 패키징 환경: resources/server/haehan-server.exe 를 자동 실행
 * 개발 환경:   이미 uvicorn이 외부에서 실행 중 → 자동 실행 생략
 *
 * L3 Connectors 계층 (저수준 프로세스 IO). 업무 로직 없음.
 */
const { app } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const http = require("http");

const FASTAPI_PORT = parseInt(process.env.HAEHAN_PORT || "8401", 10);
const HEALTH_URL = `http://127.0.0.1:${FASTAPI_PORT}/api/v1/health`;
const HEALTH_TIMEOUT_MS = 60_000;
const HEALTH_POLL_MS = 500;

let serverProc = null;
let _ready = false;

// ── 서버 바이너리 경로 해석 ─────────────────────────────────────────────────
function resolveServerExe() {
  if (!app.isPackaged) return null; // 개발 모드: 외부 uvicorn 사용
  const exePath = path.join(process.resourcesPath, "server", "haehan-server", "haehan-server.exe");
  return fs.existsSync(exePath) ? exePath : null;
}

// ── 헬스체크 ─────────────────────────────────────────────────────────────────
function checkHealth() {
  return new Promise((resolve) => {
    const req = http.get(HEALTH_URL, { timeout: 2000 }, (res) => {
      resolve(res.statusCode >= 200 && res.statusCode < 400);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

async function waitForServer(timeoutMs = HEALTH_TIMEOUT_MS) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await checkHealth()) return true;
    await new Promise((r) => setTimeout(r, HEALTH_POLL_MS));
  }
  return false;
}

// ── 공개 API ─────────────────────────────────────────────────────────────────

/**
 * FastAPI 서버 시작.
 * @returns {Promise<boolean>} 서버 준비 완료 여부
 */
async function startFastAPIServer() {
  // 1. 이미 실행 중이면 헬스체크만
  if (await checkHealth()) {
    console.log("[fastapi] 서버 이미 실행 중 (외부 또는 재시작)");
    _ready = true;
    return true;
  }

  // 2. 개발 모드: 번들 없음 → 외부 uvicorn 대기
  const exePath = resolveServerExe();
  if (!exePath) {
    console.log("[fastapi] 개발 모드 — 외부 uvicorn 대기 중...");
    const ok = await waitForServer(10_000);
    _ready = ok;
    return ok;
  }

  // 3. 번들 EXE 실행
  console.log("[fastapi] 번들 서버 시작:", exePath);
  const logDir = path.join(app.getPath("userData"), "logs");
  fs.mkdirSync(logDir, { recursive: true });
  const logStream = fs.createWriteStream(path.join(logDir, "fastapi.log"), { flags: "a" });

  serverProc = spawn(exePath, [], {
    cwd: path.dirname(exePath),
    detached: false,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      HAEHAN_PORT: String(FASTAPI_PORT),
      HAEHAN_HOST: "127.0.0.1",
      // 프로젝트 data/ 경로 — licenses.json, grant_radar 등 영속 데이터 공유
      HAEHAN_DATA_DIR: path.join(process.resourcesPath, "..", "..", "..", "data"),
    },
  });

  serverProc.stdout.pipe(logStream);
  serverProc.stderr.pipe(logStream);
  serverProc.on("exit", (code) => {
    console.log("[fastapi] 서버 종료 (code=%d)", code);
    serverProc = null;
    _ready = false;
  });

  // 4. 준비 대기
  const ok = await waitForServer(HEALTH_TIMEOUT_MS);
  if (!ok) console.error("[fastapi] 서버 시작 타임아웃 (60초)");
  _ready = ok;
  return ok;
}

/**
 * FastAPI 서버 정지.
 */
function stopFastAPIServer() {
  if (serverProc) {
    console.log("[fastapi] 서버 종료 요청");
    serverProc.kill("SIGTERM");
    setTimeout(() => { if (serverProc) serverProc.kill("SIGKILL"); }, 3000);
    serverProc = null;
  }
  _ready = false;
}

function isFastAPIReady() {
  return _ready;
}

module.exports = { startFastAPIServer, stopFastAPIServer, isFastAPIReady, FASTAPI_PORT };
