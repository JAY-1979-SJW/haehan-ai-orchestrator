/**
 * lib/pid_guard.js — 자기가 띄운 자식 서버의 PID 기록과, 이전 실행이 남긴 자기 서버만 정리하는 도우미
 *
 * 왜: Electron 이 강제 종료·크래시하면 자식(haehan-server.exe, Next)은 Windows 에서 같이 죽지 않고 남는다. 다음 실행이
 * "이미 떠 있으면 재사용"하면 이전 실행의 환경(APPROVAL_PROXY_SECRET 등)을 가진 서버가 새 실행과 어긋난다
 * (DESKTOP_RUNTIME_AUDIT D5). 그래서 시작할 때 **우리가 기록해 둔 PID** 의 이전 자식만 종료하고 새로 띄운다.
 *
 * 원칙: 이름이나 포트로 남의 프로세스를 죽이지 않는다. PID 파일에 적힌 PID 가 (1) 아직 살아 있고 (2) 그 PID 의
 * 실행 파일 이름이 기록해 둔 이름과 같을 때만 종료한다(PID 가 재사용돼 다른 프로그램이 됐으면 건드리지 않는다).
 * 자기 자신(process.pid)은 절대 종료하지 않는다.
 */
const { app } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawnSync } = require("child_process");

function pidFilePath(name) {
  return path.join(app.getPath("userData"), "run", `${name}.pid`);
}

function writePid(name, pid, image, cmdIncludes) {
  try {
    const p = pidFilePath(name);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    const tmp = p + ".tmp";
    fs.writeFileSync(tmp, JSON.stringify({ pid, image, cmdIncludes: cmdIncludes || null, startedAt: new Date().toISOString() }));
    fs.renameSync(tmp, p); // 원자적 쓰기
  } catch (e) {
    console.warn("[pid_guard] PID 기록 실패(다음 실행의 정리 대상에서 빠짐):", e.message);
  }
}

/** 기록된 PID 가 pid 와 같거나(또는 pid 미지정) 이면 PID 파일을 지운다. */
function clearPid(name, pid) {
  try {
    const p = pidFilePath(name);
    if (!fs.existsSync(p)) return;
    if (pid !== undefined) {
      const rec = JSON.parse(fs.readFileSync(p, "utf-8"));
      if (rec.pid !== pid) return; // 이미 새 서버가 다른 PID 로 기록했다
    }
    fs.unlinkSync(p);
  } catch {}
}

function _sleepSync(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function _commandLine(pid) {
  try {
    if (process.platform === "win32") {
      const r = spawnSync(
        "powershell",
        ["-NoProfile", "-NonInteractive", "-Command", `(Get-CimInstance Win32_Process -Filter 'ProcessId=${Number(pid)}').CommandLine`],
        { encoding: "utf-8", windowsHide: true, timeout: 10000 }
      );
      return r.status === 0 ? (r.stdout || "").trim() : "";
    }
    const r = spawnSync("ps", ["-p", String(pid), "-o", "args="], { encoding: "utf-8" });
    return r.status === 0 ? (r.stdout || "").trim() : "";
  } catch {
    return "";
  }
}

/**
 * pid 가 살아 있고 실행 파일 이름이 image 와 같은가(+ cmdIncludes 가 있으면 명령줄에도 들어 있는가).
 * 확신할 수 없으면 false(=건드리지 않는다). Next 서버는 Electron 실행 파일로 fork 되어 이름만으로는 우리 앱의
 * 다른 프로세스(렌더러·GPU)와 구분되지 않으므로 server.js 경로를 명령줄로 한 번 더 확인한다.
 */
function isProcessWithImage(pid, image, cmdIncludes) {
  try {
    process.kill(pid, 0);
  } catch {
    return false;
  }
  try {
    if (cmdIncludes && !_commandLine(pid).toLowerCase().includes(String(cmdIncludes).toLowerCase())) return false;
    if (process.platform === "win32") {
      const r = spawnSync("tasklist", ["/FI", `PID eq ${pid}`, "/FO", "CSV", "/NH"], { encoding: "utf-8", windowsHide: true });
      if (r.status !== 0) return false;
      const first = (r.stdout || "").trim().split("\n")[0] || "";
      const m = first.match(/^"([^"]+)"/);
      return !!m && m[1].toLowerCase() === String(image).toLowerCase();
    }
    const r = spawnSync("ps", ["-p", String(pid), "-o", "comm="], { encoding: "utf-8" });
    return r.status === 0 && path.basename((r.stdout || "").trim()) === path.basename(String(image));
  } catch {
    return false;
  }
}

function _isAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/**
 * 이전 실행이 남긴 자기 서버를 종료한다. 반환: { killed: boolean, pid?: number, reason?: string }
 * PID 파일이 없으면 아무것도 하지 않는다(외부에서 직접 띄운 개발용 서버 등은 그대로 재사용).
 */
function killPreviousFromPidFile(name) {
  const p = pidFilePath(name);
  let rec;
  try {
    rec = JSON.parse(fs.readFileSync(p, "utf-8"));
  } catch {
    return { killed: false, reason: "no-pid-file" };
  }
  const pid = Number(rec && rec.pid);
  if (!Number.isInteger(pid) || pid <= 0 || pid === process.pid) {
    clearPid(name);
    return { killed: false, reason: "invalid-pid" };
  }
  if (!isProcessWithImage(pid, rec.image, rec.cmdIncludes)) {
    clearPid(name); // 이미 죽었거나 PID 가 재사용됨 — 남의 프로세스는 건드리지 않는다
    return { killed: false, reason: "not-our-process" };
  }
  console.warn(`[pid_guard] 이전 실행이 남긴 ${name}(PID ${pid}) 종료`);
  try {
    process.kill(pid, "SIGTERM");
  } catch {}
  for (let i = 0; i < 25 && _isAlive(pid); i++) _sleepSync(200); // 최대 5초
  if (_isAlive(pid)) {
    try {
      process.kill(pid, "SIGKILL");
    } catch {}
    for (let i = 0; i < 10 && _isAlive(pid); i++) _sleepSync(200);
  }
  clearPid(name);
  return { killed: !_isAlive(pid), pid };
}

module.exports = { pidFilePath, writePid, clearPid, isProcessWithImage, killPreviousFromPidFile };
