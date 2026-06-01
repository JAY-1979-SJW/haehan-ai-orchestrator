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
