/**
 * webview_preload.js — <webview>(Next.js UI) 컨텍스트에 로컬 설정 브리지 노출.
 * L9/L3. 사이트 선택·설정 4개만 노출(파일/셸/임의 IPC 미노출).
 * 화면 → window.haehanLocal.* → ipcRenderer.invoke → main → lib/config.js → config.json(로컬)
 * 민감값(비번/토큰)은 config.js _stripSensitive 가 저장 차단.
 */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("haehanLocal", {
  getEnabledSites: () => ipcRenderer.invoke("local-config:get-enabled-sites"),
  setEnabledSites: (ids) => ipcRenderer.invoke("local-config:set-enabled-sites", ids),
  getSiteSettings: (siteId) => ipcRenderer.invoke("local-config:get-site-settings", siteId),
  setSiteSettings: (siteId, settings) => ipcRenderer.invoke("local-config:set-site-settings", siteId, settings),
});

// ── 상시 로그인: 저장된 세션 토큰을 localStorage 에 항상 동기화 ────────────────────
// userData(config.json)의 auth_token 을 webview localStorage(haehan_ai_token)에 넣어
// getMe 가 토큰을 인지하게 한다. "없을 때만" 넣으면 옛 토큰(서버 재빌드로 user id 변경 등)이
// 남아 401→로그인화면으로 막히므로, config 값과 다르면 항상 덮어써서 동기화한다.
// localStorage 는 origin 단위 저장이라 isolated preload 에서 set 해도 페이지가 읽는다.
ipcRenderer.invoke("local-config:get-auth-token").then((token) => {
  try {
    if (token) {
      if (window.localStorage.getItem("haehan_ai_token") !== token) {
        window.localStorage.setItem("haehan_ai_token", token);
      }
    }
  } catch (_) { /* storage 접근 불가 시 무시 */ }
}).catch(() => {});
