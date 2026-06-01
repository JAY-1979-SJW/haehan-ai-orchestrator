/**
 * lib/remote_config.js — 원격 서버에서 환경변수를 fetch해 로컬 FastAPI에 주입
 *
 * 흐름:
 *   1. haehan-ai.kr/api/v1/config/desktop-env  (x-license-key 인증)
 *   2. 로컬 FastAPI POST /api/v1/config/reload  (env dict 전달)
 *
 * L3 Connectors 계층. 업무 로직 없음.
 */
const https = require("https");
const http = require("http");

const REMOTE_BASE = process.env.HAEHAN_REMOTE_URL || "https://haehan-ai.kr/orchestrator";
const LOCAL_FASTAPI = `http://127.0.0.1:${process.env.HAEHAN_PORT || "8401"}`;

function httpsGet(url, headers) {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith("https") ? https : http;
    const req = mod.get(url, { headers, timeout: 10000 }, (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => {
        try { resolve({ status: res.statusCode, body: JSON.parse(data) }); }
        catch { resolve({ status: res.statusCode, body: data }); }
      });
    });
    req.on("error", reject);
    req.on("timeout", () => { req.destroy(); reject(new Error("timeout")); });
  });
}

function httpPost(url, payload) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(payload);
    const opts = {
      method: "POST",
      headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) },
      timeout: 5000,
    };
    const req = http.request(url, opts, (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => {
        try { resolve({ status: res.statusCode, body: JSON.parse(data) }); }
        catch { resolve({ status: res.statusCode, body: data }); }
      });
    });
    req.on("error", reject);
    req.on("timeout", () => { req.destroy(); reject(new Error("timeout")); });
    req.write(body);
    req.end();
  });
}

/**
 * 원격 서버에서 env를 받아 로컬 FastAPI에 주입.
 * @param {string} licenseKey
 * @returns {Promise<{ok: boolean, applied: number, reason?: string}>}
 */
async function fetchAndApplyRemoteConfig(licenseKey) {
  if (!licenseKey) {
    console.log("[remote-config] 라이선스 키 없음 — 건너뜀");
    return { ok: false, applied: 0, reason: "no_license" };
  }

  // 1. 원격 서버에서 env fetch
  let envResult;
  try {
    envResult = await httpsGet(`${REMOTE_BASE}/api/v1/config/desktop-env`, {
      "x-license-key": licenseKey,
    });
  } catch (e) {
    console.warn("[remote-config] 원격 서버 fetch 실패 (오프라인?):", e.message);
    return { ok: false, applied: 0, reason: "fetch_failed" };
  }

  if (envResult.status !== 200 || !envResult.body?.env) {
    console.warn("[remote-config] 원격 서버 응답 오류:", envResult.status);
    return { ok: false, applied: 0, reason: `remote_${envResult.status}` };
  }

  // 2. 로컬 FastAPI에 주입
  try {
    const reloadResult = await httpPost(`${LOCAL_FASTAPI}/api/v1/config/reload`, {
      env: envResult.body.env,
    });
    const applied = reloadResult.body?.applied ?? 0;
    console.log("[remote-config] 환경변수 %d개 적용 완료", applied);
    return { ok: true, applied };
  } catch (e) {
    console.warn("[remote-config] 로컬 FastAPI reload 실패:", e.message);
    return { ok: false, applied: 0, reason: "reload_failed" };
  }
}

module.exports = { fetchAndApplyRemoteConfig };
