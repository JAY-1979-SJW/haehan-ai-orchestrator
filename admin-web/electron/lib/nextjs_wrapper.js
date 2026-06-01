/**
 * nextjs_wrapper.js — Next.js standalone 서버 래퍼
 *
 * 빌드 시 standalone/ 디렉터리에 복사되어 server.js 대신 fork 대상이 됨.
 *
 * 목적: Next.js 14 App Router standalone + Electron 조합에서, webview의
 * WebSocket upgrade 요청 시 base-server.js의 res.setHeader.bind() 에서
 * TypeError가 발생한다. (res가 ServerResponse가 아닌 Socket으로 전달되는
 * Next.js 14 버그) Next.js가 이 예외를 내부 try/catch로 잡은 뒤 자체
 * 로거(Log.error)로 console.error/stderr에 출력하기만 하므로, process의
 * uncaughtException/unhandledRejection 핸들러로는 잡히지 않는다.
 * 실제 HTTP 응답·UI 렌더링은 정상이며 로그만 오염되므로, 해당 출력만 필터.
 */

// 이 특정 오류 출력인지 판별 (write가 여러 줄로 쪼개질 수 있어 OR 매칭)
function isUpgradeBindNoise(text) {
  return (
    typeof text === "string" &&
    (text.includes("reading 'bind'") || text.includes("handleRequestImpl"))
  );
}

// 1) console.error 경로 (Log.error 가 에러 객체/포맷 문자열을 넘김)
const origConsoleError = console.error.bind(console);
console.error = (...args) => {
  try {
    const s = args.map((a) => (a && a.stack ? a.stack : String(a))).join(" ");
    if (isUpgradeBindNoise(s)) return;
  } catch {
    /* 판별 실패 시 정상 출력 */
  }
  origConsoleError(...args);
};

// 2) stderr 직접 쓰기 경로
const origStderrWrite = process.stderr.write.bind(process.stderr);
process.stderr.write = (chunk, ...rest) => {
  try {
    if (isUpgradeBindNoise(chunk.toString())) return true;
  } catch {
    /* 무시하고 정상 출력 */
  }
  return origStderrWrite(chunk, ...rest);
};

// 3) 혹시 비동기 거부/동기 예외로 새는 경우도 방어
function isUpgradeBindError(err) {
  return (
    err &&
    typeof err.message === "string" &&
    err.message.includes("reading 'bind'") &&
    typeof err.stack === "string" &&
    err.stack.includes("handleRequestImpl")
  );
}
process.on("uncaughtException", (err) => {
  if (isUpgradeBindError(err)) return;
  throw err;
});
process.on("unhandledRejection", (reason) => {
  if (isUpgradeBindError(reason)) return;
  throw reason;
});

require("./server.js");
