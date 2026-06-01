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

const NEXT_PORT = parseInt(process.env.NEXT_PORT || "3000", 10);
const HEALTH_URL = `http://127.0.0.1:${NEXT_PORT}`;
const HEALTH_TIMEOUT_MS = 30_000;
const HEALTH_POLL_MS = 500;

let serverProc = null;
let _ready = false;

function resolveServerJs() {
  if (app.isPackaged) {
    const p = path.join(process.resourcesPath, "nextjs", "server.js");
    return fs.existsSync(p) ? p : null;
  }
  // 개발 모드: admin-web/.next/standalone/server.js
  const dev = path.join(__dirname, "..", "..", ".next", "standalone", "server.js");
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
  if (await checkHealth()) {
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
    env: {
      ...process.env,
      PORT: String(NEXT_PORT),
      HOSTNAME: "127.0.0.1",
      NODE_ENV: "production",
    },
  });

  serverProc.stdout.pipe(logStream);
  serverProc.stderr.pipe(logStream);
  serverProc.on("exit", (code) => {
    console.log("[nextjs] 서버 종료 (code=%d)", code);
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
    serverProc.kill("SIGTERM");
    setTimeout(() => { if (serverProc) serverProc.kill("SIGKILL"); }, 3000);
    serverProc = null;
  }
  _ready = false;
}

function isNextReady() { return _ready; }

module.exports = { startNextServer, stopNextServer, isNextReady, NEXT_PORT };
