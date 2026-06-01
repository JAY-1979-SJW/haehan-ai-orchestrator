/**
 * nextjs_wrapper.js — Next.js standalone 서버 래퍼
 *
 * 빌드 시 standalone/ 디렉터리에 복사되어 server.js 대신 fork 대상이 됨.
 *
 * 목적: Next.js 14 App Router standalone + Electron 조합에서 발생하는
 * WebSocket 업그레이드 요청 시 res.setHeader.bind() TypeError를 suppress.
 * (res가 ServerResponse가 아닌 Socket 객체로 전달되는 Next.js 14 버그)
 * HTTP 응답과 UI 렌더링은 정상 동작함.
 */
process.on("uncaughtException", (err) => {
  if (
    err?.message?.includes("reading 'bind'") &&
    err?.stack?.includes("handleRequestImpl")
  ) {
    // Next.js 14 standalone + Electron WebSocket upgrade 충돌 — 무시
    return;
  }
  // 그 외 예외는 정상적으로 재throw
  throw err;
});

require("./server.js");
