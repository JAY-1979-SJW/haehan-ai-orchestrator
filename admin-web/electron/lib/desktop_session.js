/**
 * lib/desktop_session.js — 시작할 때마다 데스크톱 자동 세션 토큰을 새로 받는다 (대표님 결정 B안)
 *
 * 흐름: 서버가 뜨면 POST /api/v1/auth/desktop-session(헤더 X-Haehan-Desktop: 1)으로 등록된 owner 의 새 토큰을 받아
 * config.json 의 auth_token 에 원자적으로 보관한다. webview_preload 가 이 값을 페이지 쿠키·localStorage 에 넣는다
 * (30일 만료를 신경 쓸 필요가 없다).
 *   200            → 토큰 저장
 *   409 needs_setup → 사용자가 한 명도 없음(새 설치·DB 초기화) → 옛 토큰을 지운다(남기면 페이지가 옛 토큰으로 막힌다).
 *                     Next 가 /setup(이름·이메일 등록)으로 보낸다.
 *   그 밖(서버 모드 404·네트워크 실패·409 no_active_owner) → 기존 토큰을 그대로 둔다(시작을 막지 않는다).
 * 서버(백엔드)가 데스크톱 모드(AUTH_ENABLED=false + HAEHAN_DESKTOP=1 + loopback)에서만 응답한다.
 */
const http = require("http");
const { getAuthToken, setAuthToken } = require("./config");

function postDesktopSession(port, timeoutMs = 5000) {
  return new Promise((resolve) => {
    const req = http.request(
      {
        host: "127.0.0.1",
        port,
        path: "/api/v1/auth/desktop-session",
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Haehan-Desktop": "1", "Content-Length": 2 },
        timeout: timeoutMs,
      },
      (res) => {
        let body = "";
        res.setEncoding("utf8");
        res.on("data", (c) => {
          body += c;
          if (body.length > 65536) req.destroy(); // 비정상적으로 큰 응답 방어
        });
        res.on("end", () => {
          let json = null;
          try {
            json = JSON.parse(body);
          } catch {}
          resolve({ status: res.statusCode, json });
        });
      }
    );
    req.on("error", () => resolve({ status: 0, json: null }));
    req.on("timeout", () => {
      req.destroy();
      resolve({ status: 0, json: null });
    });
    req.end("{}");
  });
}

/** 반환: "refreshed" | "needs_setup" | "kept" (서버 모드·실패 등 — 기존 토큰 유지) */
async function refreshDesktopSession(port) {
  const { status, json } = await postDesktopSession(port);
  try {
    if (status === 200 && json && typeof json.token === "string" && json.token) {
      setAuthToken(json.token);
      return "refreshed";
    }
    if (status === 409 && json && json.detail === "needs_setup") {
      if (getAuthToken()) setAuthToken("");
      return "needs_setup";
    }
  } catch (e) {
    console.warn("[desktop-session] 토큰 저장 실패(기존 값 유지):", e.message);
  }
  return "kept";
}

module.exports = { refreshDesktopSession, postDesktopSession };
