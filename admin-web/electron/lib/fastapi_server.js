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
const { getOrCreateJwtSecret, loadUserEnv } = require("./config");
const { writePid, clearPid, killPreviousFromPidFile } = require("./pid_guard");

const FASTAPI_PORT = parseInt(process.env.HAEHAN_PORT || "8401", 10);
const HEALTH_URL = `http://127.0.0.1:${FASTAPI_PORT}/api/v1/health`;
const HEALTH_TIMEOUT_MS = 60_000;
const HEALTH_POLL_MS = 500;

let serverProc = null;
let _ready = false;

// ── 빌드 정보(build-info.json) — 빌드 워크플로가 extraResources 로 넣는다 ────────────
// 형식: {"git_sha":"<40자 hex>","build_time":"<ISO8601 UTC>","version":"<yyyymmdd>-<sha7>"}
// 서버(/api/v1/health)가 환경변수 GIT_SHA·BUILD_TIME 을 실행 시점에 읽어 응답하므로 여기서 env 로만 넘기면 된다.
// 파일이 없거나 깨져도 시작을 막지 않는다(그냥 unknown).
const _GIT_SHA_RE = /^[0-9a-fA-F]{7,40}$/;
const _BUILD_TIME_RE = /^[0-9A-Za-z:+._ -]{1,40}$/;

function readBuildInfo() {
  try {
    const raw = fs.readFileSync(path.join(process.resourcesPath, "build-info.json"), "utf-8").replace(/^﻿/, "");
    const j = JSON.parse(raw);
    const info = {};
    if (typeof j.git_sha === "string" && _GIT_SHA_RE.test(j.git_sha.trim())) info.git_sha = j.git_sha.trim();
    if (typeof j.build_time === "string" && _BUILD_TIME_RE.test(j.build_time.trim())) info.build_time = j.build_time.trim();
    if (typeof j.version === "string" && _BUILD_TIME_RE.test(j.version.trim())) info.version = j.version.trim();
    return info;
  } catch {
    return {};
  }
}

// ── 서버 바이너리 경로 해석 ─────────────────────────────────────────────────
function resolveServerExe() {
  if (!app.isPackaged) return null; // 개발 모드: 외부 uvicorn 사용
  const exePath = path.join(process.resourcesPath, "server", "haehan-server", "haehan-server.exe");
  return fs.existsSync(exePath) ? exePath : null;
}

// ── Gmail credentials 최초 1회 시드 (userData/secrets 가 비어있을 때만) ──────────
function seedGmailSecrets() {
  const destDir = path.join(app.getPath("userData"), "secrets");
  fs.mkdirSync(destDir, { recursive: true });
  for (const name of ["gmail_credentials.json", "gmail_token.json"]) {
    const dest = path.join(destDir, name);
    if (fs.existsSync(dest)) continue;
    // 개발 repo 소스 경로 (있으면 최초 1회만 복사, 없으면 건너뜀 — OAuth 화면에서 재인가)
    // resourcesPath = <repo>/dist-electron-new/win-unpacked/resources → 3단계 위가 repo root
    const src = path.join(process.resourcesPath, "..", "..", "..", "ai_orchestrator", "storage", "secrets", name);
    if (fs.existsSync(src)) fs.copyFileSync(src, dest);
  }
}

// ── 영속 데이터(licenses.json, grant_radar/) 최초 1회 시드 ─────────────────────
function seedDataDir() {
  const destDir = path.join(app.getPath("userData"), "data");
  fs.mkdirSync(destDir, { recursive: true });
  // 개발 repo 소스 경로 (있으면 최초 1회만 복사, 없으면 건너뜀 — 새 설치는 빈 상태로 시작)
  const srcRoot = path.join(process.resourcesPath, "..", "..", "..", "data");
  const destLicenses = path.join(destDir, "licenses.json");
  const srcLicenses = path.join(srcRoot, "licenses.json");
  if (!fs.existsSync(destLicenses) && fs.existsSync(srcLicenses)) {
    fs.copyFileSync(srcLicenses, destLicenses);
  }
  const destGrant = path.join(destDir, "grant_radar");
  const srcGrant = path.join(srcRoot, "grant_radar");
  if (!fs.existsSync(destGrant) && fs.existsSync(srcGrant)) {
    fs.cpSync(srcGrant, destGrant, { recursive: true });
  }
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
  // 0. 이전 실행이 남긴 '우리 서버'가 있으면 먼저 종료한다(남은 서버가 이전 실행의 환경으로 재사용되는 것을 막는다).
  //    PID 파일에 기록된 PID 만 대상 — 이름·포트로 남의 프로세스를 죽이지 않는다(D5).
  const prev = killPreviousFromPidFile("fastapi");
  if (prev.killed) console.log("[fastapi] 이전 실행의 서버를 정리했다 (PID %d)", prev.pid);

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
  seedGmailSecrets();
  seedDataDir();
  console.log("[fastapi] 번들 서버 시작:", exePath);
  const logDir = path.join(app.getPath("userData"), "logs");
  fs.mkdirSync(logDir, { recursive: true });
  const logStream = fs.createWriteStream(path.join(logDir, "fastapi.log"), { flags: "a" });
  // 서버가 쓰는 모든 데이터(DB·감사/승인 기록·업무 데이터)는 사용자 프로필(userData) 아래 한 곳에 둔다.
  // 번들(설치/압축해제) 폴더에 쓰면 갱신·재실행 때 사라진다(D1). 폴더는 서버가 처음 쓰기 전에 만들어 둔다.
  const dataRoot = app.getPath("userData");
  fs.mkdirSync(path.join(dataRoot, "storage"), { recursive: true });
  const build = readBuildInfo();

  serverProc = spawn(exePath, [], {
    cwd: path.dirname(exePath),
    detached: false,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      ...loadUserEnv(), // 설정화면에서 저장한 API 키(userData/.env) — 아래 앱 고정값이 항상 우선
      HAEHAN_PORT: String(FASTAPI_PORT),
      HAEHAN_HOST: "127.0.0.1",
      // 영속 데이터 경로 — userData 기준 (설치 위치와 무관), 최초 1회 seedDataDir()로 시드.
      // HAEHAN_DATA_ROOT 가 정본(서버 ai_orchestrator.paths.runtime 과 scripts.common.app_paths 가 같이 본다).
      // HAEHAN_DATA_DIR(옛 이름)은 같은 값(root/data)으로 계속 넘긴다 — 아직 그 이름만 읽는 스크립트와 MCP 호환.
      HAEHAN_DATA_ROOT: dataRoot,
      HAEHAN_DATA_DIR: path.join(dataRoot, "data"),
      // 감사·승인 기록(audit_logs.jsonl, approval_*.jsonl …)과 DB 는 userData\storage — 번들 안이 아니다
      LOG_DIR: path.join(dataRoot, "storage"),
      // 데스크톱 로컬 모드 표지 — 첫 가입자 자동 owner 승인(AUTH_ENABLED=false + loopback)의 조건 중 하나
      HAEHAN_DESKTOP: "1",
      ...(build.git_sha ? { GIT_SHA: build.git_sha } : {}),
      ...(build.build_time ? { BUILD_TIME: build.build_time } : {}),
      // self-contained 데스크톱: 127.0.0.1 loopback 전용 + 외부 접근 차단(BrowserGate/CORS)
      // 하에서 로컬 앱을 신뢰 → Basic 인증 생략. 외부/타앱은 네트워크 계층에서 차단됨.
      AUTH_ENABLED: "false",
      // JWT_SECRET 고정 — 재시작에도 사용자 세션 토큰 유효(상시 로그인). userData 에 1회 생성·저장.
      JWT_SECRET: getOrCreateJwtSecret(),
      // Gmail OAuth2 credentials — userData 기준 (설치 위치와 무관하게 항상 유효)
      GMAIL_CREDENTIALS_PATH: path.join(app.getPath("userData"), "secrets", "gmail_credentials.json"),
      GMAIL_TOKEN_PATH: path.join(app.getPath("userData"), "secrets", "gmail_token.json"),
    },
  });

  const spawnedPid = serverProc.pid;
  writePid("fastapi", spawnedPid, path.basename(exePath)); // 다음 실행이 비정상 종료 뒤 남은 이 서버를 정리할 수 있게
  serverProc.stdout.pipe(logStream);
  serverProc.stderr.pipe(logStream);
  serverProc.on("exit", (code) => {
    console.log("[fastapi] 서버 종료 (code=%d)", code);
    clearPid("fastapi", spawnedPid);
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
    const proc = serverProc;
    proc.kill("SIGTERM");
    // exit 핸들러가 serverProc 을 null 로 정리하므로, 지연 SIGKILL 은 캡처해둔 proc 을 직접 검사한다
    // (serverProc 을 여기서 바로 null 처리하면 타임아웃이 항상 false 로 평가돼 SIGKILL 이 안 나감).
    setTimeout(() => { try { proc.kill("SIGKILL"); } catch {} }, 3000);
    serverProc = null;
  }
  _ready = false;
}

function isFastAPIReady() {
  return _ready;
}

module.exports = { startFastAPIServer, stopFastAPIServer, isFastAPIReady, readBuildInfo, FASTAPI_PORT };
