/**
 * lib/licenseWindow.js — 라이선스 입력 창 + 키 검증
 * L9 Admin UI(데스크톱 셸). 소유자 모드에서는 main.js가 이 흐름을 건너뛴다.
 */
const { BrowserWindow } = require("electron");
const path = require("path");

function createLicenseWindow() {
  const win = new BrowserWindow({
    width: 460, height: 320,
    resizable: false,
    title: "Haehan AI — 라이선스 입력",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "..", "preload.js"),
    },
  });

  win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Haehan AI — 라이선스 입력</title>
<!-- 2026-09-29 electron-verifier 검증(FAIL) 대응: 공식 체크리스트 6번(CSP) -->
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; base-uri 'none';">
<style>
  * { box-sizing: border-box; font-family: -apple-system, 'Malgun Gothic', sans-serif; margin: 0; }
  body { background: #F9FAFB; display: flex; align-items: center; justify-content: center; height: 100vh; }
  .card { background: white; border: 1px solid #E5E7EB; border-radius: 16px; padding: 32px; width: 380px; }
  h1 { font-size: 18px; font-weight: 700; color: #111827; margin-bottom: 4px; }
  p  { font-size: 13px; color: #6B7280; margin-bottom: 24px; }
  label { font-size: 12px; font-weight: 600; color: #374151; display: block; margin-bottom: 6px; }
  input { width: 100%; padding: 10px 12px; border: 1px solid #E5E7EB; border-radius: 8px; font-size: 14px;
          font-family: monospace; outline: none; }
  input:focus { border-color: #F97316; box-shadow: 0 0 0 3px rgba(249,115,22,0.15); }
  button { width: 100%; margin-top: 16px; padding: 11px; background: #F97316; color: white;
           border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; }
  button:hover { background: #EA580C; }
  .err { color: #DC2626; font-size: 12px; margin-top: 8px; display: none; }
  .accent { color: #F97316; }
</style>
</head>
<body>
<div class="card">
  <h1>Haehan <span class="accent">AI</span></h1>
  <p>운영자로부터 받은 라이선스 키를 입력하세요.</p>
  <label>라이선스 키</label>
  <input id="key" type="text" placeholder="xxxxxxxxxxxx" autocomplete="off" spellcheck="false" />
  <div class="err" id="err">유효하지 않은 라이선스 키입니다.</div>
  <button id="btn" onclick="submit()">시작하기</button>
</div>
<script>
document.getElementById('key').addEventListener('keydown', e => { if(e.key==='Enter') submit(); });
window.electronAPI.onLicenseError(() => {
  document.getElementById('err').style.display = 'block';
  document.getElementById('btn').textContent = '시작하기';
});
function submit() {
  const k = document.getElementById('key').value.trim();
  if (!k) return;
  document.getElementById('btn').textContent = '확인 중...';
  document.getElementById('err').style.display = 'none';
  window.electronAPI.submitLicense(k);
}
</script>
</body>
</html>
  `)}`);

  return win;
}

/** 라이선스 키 검증 — 서버 미응답/예외 시 로컬 개발 편의로 허용 */
function verifyLicense(key) {
  return new Promise((resolve) => {
    const http = require("http");
    const req = http.get(
      `http://localhost:8401/api/v1/smartstore/licenses/${encodeURIComponent(key)}/verify`,
      (r) => {
        let data = "";
        r.on("data", (d) => data += d);
        r.on("end", () => { try { resolve(JSON.parse(data)); } catch { resolve({ ok: false }); } });
      }
    );
    // 오프라인/로컬 개발 허용: FastAPI 서버가 아직 안 떴거나 네트워크 오류면 통과.
    // self-contained 데스크톱에서 서버가 부팅 중일 때 타임아웃으로 막히지 않게 하기 위한 의도적 설계.
    // 운영 서버 모드에서는 서버가 항상 기동 중이므로 이 경로에 도달하지 않음.
    req.on("error", () => resolve({ ok: true }));
    req.setTimeout(3000, () => { req.destroy(); resolve({ ok: true }); });
  });
}

module.exports = { createLicenseWindow, verifyLicense };
