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
const { writePid, clearPid, killPreviousFromPidFile, killTreeAndWait } = require("./pid_guard");

const NEXT_PORT = parseInt(process.env.NEXT_PORT || "3000", 10);
const HEALTH_URL = `http://127.0.0.1:${NEXT_PORT}`;
const HEALTH_TIMEOUT_MS = 30_000;
const HEALTH_POLL_MS = 500;

let serverProc = null;
let _ready = false;
let _lastError = "";

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
  // 단, 설치본(번들 server.js 있음)은 이미 떠 있는 서버를 30초 동안 기다릴 이유가 없다 — 처음 켤 때 매번
  // 30초를 그냥 기다린 뒤에야 자기 서버를 띄워 앱 시작이 31초 걸렸다(2026-10-08 E2E 시작 기록 실측).
  // 번들 서버가 있으면 한 번만 확인하고 바로 띄우고, 오래 기다리는 건 `next dev` 를 쓰는 개발 모드에서만.
  _lastError = "";
  const serverJs = resolveServerJs();
  if (serverJs && app.isPackaged) {
    // 설치본: 포트 3000 에 떠 있는 서버는 내가 띄운 것이 아니다(Next 는 health 신원이 없다) — 재사용하지 않는다.
    // 직전 실행의 서버가 막 끝나는 중일 수 있어 잠시 기다리고, 계속 점유돼 있으면 명확히 실패한다.
    const deadline = Date.now() + 10_000;
    while ((await checkHealth()) && Date.now() < deadline) await new Promise((r) => setTimeout(r, HEALTH_POLL_MS));
    if (await checkHealth()) {
      _lastError = `포트 ${NEXT_PORT} 을(를) 다른 프로그램(또는 이전 Haehan AI)이 사용 중입니다. 실행 중인 Haehan AI 를 모두 종료한 뒤 다시 시작하세요.`;
      console.error("[nextjs]", _lastError);
      _ready = false;
      return false;
    }
  }
  const alreadyUp = serverJs ? (app.isPackaged ? false : await checkHealth()) : await waitForServer(HEALTH_TIMEOUT_MS);
  if (alreadyUp) {
    console.log("[nextjs] 서버 이미 실행 중");
    _ready = true;
    return true;
  }

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
    // 앱 본체가 강제 종료돼도 고아로 남지 않게 부모 감시를 먼저 로드한다
    execArgv: ["--require", path.join(__dirname, "parent_watch.js")],
    cwd: path.dirname(serverJs),   // standalone/ 를 cwd로 — .next/ 상대 경로 탐색에 필수
    env: {
      ...process.env,
      PORT: String(NEXT_PORT),
      HOSTNAME: "127.0.0.1",
      NODE_ENV: "production",
      HAEHAN_PARENT_PID: String(process.pid),
      // 데스크톱 표지 — Next 미들웨어가 로그인 대신 /setup(첫 실행 등록·자동 세션)으로 보낸다
      HAEHAN_DESKTOP: "1",
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
  const proc = serverProc;
  _ready = false;
  if (!proc) return Promise.resolve();
  console.log("[nextjs] 서버 종료 요청");
  return killTreeAndWait(proc);
}

function getNextLastError() { return _lastError; }

function isNextReady() { return _ready; }

module.exports = { startNextServer, stopNextServer, getNextLastError, isNextReady, NEXT_PORT };
