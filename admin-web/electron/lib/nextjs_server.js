/**
 * lib/nextjs_server.js — Next.js standalone 서버 프로세스 관리
 *
 * 패키징 환경: resources/nextjs/server.js 를 child_process.fork로 실행
 * 개발 환경:   localhost:3000 이미 실행 중 → pass. 없으면 프로젝트 내 standalone 탐색.
 *
 * L3 Connectors 계층. 업무 로직 없음.
 */
const { app } = require("electron");
const path = require("path");
const fs = require("fs");
const { fork } = require("child_process");
const http = require("http");
const { writePid, clearPid, killPreviousFromPidFile } = require("./pid_guard");

const NEXT_PORT = parseInt(process.env.NEXT_PORT || "3000", 10);
const HEALTH_URL = `http://127.0.0.1:${NEXT_PORT}`;
const HEALTH_TIMEOUT_MS = 30_000;
const HEALTH_POLL_MS = 500;

let serverProc = null;
let _ready = false;

function resolveServerJs() {
  if (app.isPackaged) {
    // wrapper.js → server.js 순으로 우선 탐색 (wrapper가 WebSocket 오류 suppress)
    const base = path.join(process.resourcesPath, "nextjs");
    const wrapper = path.join(base, "wrapper.js");
    if (fs.existsSync(wrapper)) return wrapper;
    const server = path.join(base, "server.js");
    return fs.existsSync(server) ? server : null;
  }
  // 개발 모드: admin-web/.next/standalone/wrapper.js → server.js
  const standaloneDir = path.join(__dirname, "..", "..", ".next", "standalone");
  const wrapper = path.join(standaloneDir, "wrapper.js");
  if (fs.existsSync(wrapper)) return wrapper;
  const dev = path.join(standaloneDir, "server.js");
  return fs.existsSync(dev) ? dev : null;
}

function checkHealth() {
  return new Promise((resolve) => {
    const req = http.get(HEALTH_URL, { timeout: 2000 }, (res) => {
      resolve(res.statusCode >= 200 && res.statusCode < 500);
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

async function startNextServer() {
  // 이전 실행이 남긴 '우리 Next 서버'만 PID 파일 기준으로 정리 — 이름·포트로 남의 프로세스를 죽이지 않는다(D5).
  const prev = killPreviousFromPidFile("nextjs");
  if (prev.killed) console.log("[nextjs] 이전 실행의 서버를 정리했다 (PID %d)", prev.pid);

  // 단발성 checkHealth()(2초 타임아웃) 대신 waitForServer()로 재시도한다.
  // `next dev`는 첫 요청에서 그 라우트를 온디맨드 컴파일하는데, 콜드스타트에서
  // 2초를 넘기는 경우가 흔해 한 번만 확인하면 "이미 떠 있는데도 없다"고 오판해
  // 존재하지 않는 standalone 빌드를 찾다가 "UI 서버 시작 실패"로 이어졌다
  // (2026-09-28 Electron 셸 복원 후 재현·확인).
  if (await waitForServer(HEALTH_TIMEOUT_MS)) {
    console.log("[nextjs] 서버 이미 실행 중");
    _ready = true;
    return true;
  }

  const serverJs = resolveServerJs();
  if (!serverJs) {
    console.warn("[nextjs] standalone server.js 없음 — Next.js 빌드 필요");
    return false;
  }

  console.log("[nextjs] standalone 서버 시작:", serverJs);
  const logDir = path.join(app.getPath("userData"), "logs");
  fs.mkdirSync(logDir, { recursive: true });
  const logStream = fs.createWriteStream(path.join(logDir, "nextjs.log"), { flags: "a" });

  serverProc = fork(serverJs, [], {
    silent: true,
    cwd: path.dirname(serverJs),   // standalone/ 를 cwd로 — .next/ 상대 경로 탐색에 필수
    env: {
      ...process.env,
      PORT: String(NEXT_PORT),
      HOSTNAME: "127.0.0.1",
      NODE_ENV: "production",
      // self-contained: 번들 .env.production(원격) 대신 로컬 FastAPI(8401)로 강제.
      // @next/env 는 이미 설정된 process.env 를 .env 파일로 덮어쓰지 않으므로 여기 값이 우선.
      API_BASE_URL: "http://localhost:8401",
      BACKEND_URL: "http://localhost:8401",
      FASTAPI_BASE_URL: "http://localhost:8401/api/v1",
    },
  });

  const spawnedPid = serverProc.pid;
  writePid("nextjs", spawnedPid, path.basename(process.execPath), serverJs); // fork 는 현재 실행 파일(Electron)로 뜬다
  serverProc.stdout.pipe(logStream);
  serverProc.stderr.pipe(logStream);
  serverProc.on("exit", (code) => {
    console.log("[nextjs] 서버 종료 (code=%d)", code);
    clearPid("nextjs", spawnedPid);
    serverProc = null;
    _ready = false;
  });

  const ok = await waitForServer(HEALTH_TIMEOUT_MS);
  if (!ok) console.error("[nextjs] 서버 시작 타임아웃 (30초)");
  _ready = ok;
  return ok;
}

function stopNextServer() {
  if (serverProc) {
    console.log("[nextjs] 서버 종료 요청");
    const proc = serverProc;
    proc.kill("SIGTERM");
    // exit 핸들러가 serverProc 을 null 로 정리하므로, 지연 SIGKILL 은 캡처해둔 proc 을 직접 검사한다
    // (serverProc 을 여기서 바로 null 처리하면 타임아웃이 항상 false 로 평가돼 SIGKILL 이 안 나감).
    setTimeout(() => { try { proc.kill("SIGKILL"); } catch {} }, 3000);
    serverProc = null;
  }
  _ready = false;
}

function isNextReady() { return _ready; }

module.exports = { startNextServer, stopNextServer, isNextReady, NEXT_PORT };
