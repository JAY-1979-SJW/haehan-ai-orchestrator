/**
 * lib/startup_log.js — 앱 시작 단계별 소요 시간 기록(userData\logs\startup.log)
 * L9 데스크톱 셸 계층. 시작이 느린 구간(서버 기동·UI 서버 기동·세션 발급)을 실측으로 찾기 위한 기록.
 * 기록 실패는 시작을 막지 않는다.
 */
const fs = require("fs");
const path = require("path");
const { app } = require("electron");

const T0 = Date.now();

function logFile() {
  const dir = path.join(app.getPath("userData"), "logs");
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, "startup.log");
}

function stage(name, detail = "") {
  const line = `${new Date().toISOString()} +${Date.now() - T0}ms ${name}${detail ? " " + detail : ""}`;
  console.log("[startup]", line);
  try {
    fs.appendFileSync(logFile(), line + "\n", "utf8");
  } catch {
    // 기록 실패는 무시 — 시작을 막지 않는다
  }
}

module.exports = { stage };
