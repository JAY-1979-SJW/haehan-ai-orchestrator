# 기준서 — P1-3: 화면↔로컬설정 IPC 브리지

Status: DRAFT (승인 대기 — 코드 전 설계)
작성일: 2026-06-02
근거: preload.js, shell.html, mainWindow.js, lib/config.js 실측
전제: P1-1(카탈로그 API)·P1-2(config.js 로컬 헬퍼) 완료

---

## 1. 문제

UI는 3중 컨텍스트로 분리돼 있다:
```
[Electron main]  ← config.js(getEnabledSites/setSiteSettings 등) 여기 있음
   └─ shell.html (BrowserWindow renderer, preload.js → window.electronAPI)
        └─ <webview src="http://localhost:3000/">  ← Next.js UI (별도 웹 컨텍스트)
```
- **Next.js UI는 `<webview>` 안 별도 컨텍스트** → 현재 preload(electronAPI)가 닿지 않음.
- 따라서 Next.js 화면에서 로컬 config.js를 직접 호출 불가 → **webview 전용 브리지 필요.**

---

## 2. 목표 통신 경로

```
Next.js UI (webview)
  → window.haehanLocal.getEnabledSites()            [webview preload, contextBridge]
  → ipcRenderer.invoke("local-config:get-enabled-sites")
  → ipcMain.handle (main.js)
  → config.js (P1-2 헬퍼)
  → config.json (로컬)   ← 서버 전송 없음(순수 로컬 유지)
```

- `invoke`/`handle` 사용(비동기, 값 반환). 기존 `send`(단방향)와 구분.

---

## 3. 변경 범위 (4곳)

### 3-1. 신규 `electron/webview_preload.js` (L9/L3)
webview 컨텍스트에 최소 API만 노출:
```js
const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("haehanLocal", {
  getEnabledSites:  ()            => ipcRenderer.invoke("local-config:get-enabled-sites"),
  setEnabledSites:  (ids)         => ipcRenderer.invoke("local-config:set-enabled-sites", ids),
  getSiteSettings:  (siteId)      => ipcRenderer.invoke("local-config:get-site-settings", siteId),
  setSiteSettings:  (siteId, s)   => ipcRenderer.invoke("local-config:set-site-settings", siteId, s),
});
```
- 오직 사이트 설정 get/set만. 임의 파일·임의 IPC 노출 금지.

### 3-2. `electron/shell.html` — webview에 preload 부착
- `<webview>` 에 `preload="file://<절대경로>/webview_preload.js"` 추가.
- 절대경로는 createMainWindow가 쿼리(`?preload=`)로 전달 → shell.html이 webview attribute로 설정.
- (contextIsolation·nodeIntegration off 기본 유지)

### 3-3. `electron/lib/mainWindow.js` — preload 경로 전달
- shellUrl에 `preload` 파라미터(=`path.join(__dirname,"..","webview_preload.js")`) 추가.

### 3-4. `electron/main.js` — ipcMain.handle 4개
```js
const { getEnabledSites, setEnabledSites, getSiteSettings, setSiteSettings } = require("./lib/config");
ipcMain.handle("local-config:get-enabled-sites", () => getEnabledSites());
ipcMain.handle("local-config:set-enabled-sites", (_e, ids) => setEnabledSites(ids).enabled_sites);
ipcMain.handle("local-config:get-site-settings", (_e, id) => getSiteSettings(id));
ipcMain.handle("local-config:set-site-settings", (_e, id, s) => { setSiteSettings(id, s); return getSiteSettings(id); });
```
- config.js가 민감키 차단을 이미 수행(P1-2). main은 호출만.

### 3-5. (P1-3 화면에서 쓸) Next.js 클라이언트 헬퍼 — 다음 단계용
- `admin-web/src/lib/localConfig.ts`: `window.haehanLocal` 가드 래퍼(Electron 아니면 no-op).
- 화면 자체(토글 UI)는 P1-3 본구현에서. 이 기준서는 **브리지까지**.

---

## 4. 보안 검토

> **확정(2026-06-02): 원격 화면 기능 보류.** webview는 **로컬 UI만** 로드한다.
> 따라서 "원격 화면이 브리지에 접근" 위험은 현 단계에서 해당 없음 → 설계 단순화.

| 항목 | 내용 |
|------|------|
| 노출 범위 | 사이트 설정 get/set 4개만. 파일시스템·셸·임의 IPC 미노출 |
| contextIsolation | webview preload는 contextBridge만 사용(노드 직접 노출 X) |
| 민감값 | config.js `_stripSensitive`가 차단 — 브리지로도 비번/토큰 저장 불가 |
| 화면 출처 | **로컬 전용**(localhost / 번들). 원격 UI 보류 → 브리지는 로컬 콘텐츠만 상대 |
| 레이어 | preload/main(L9/L10), config(L10) — 위반 없음 |

---

## 5. 단계 + 드라이런/검증

1. webview_preload.js + main.handle + shell.html/mainWindow preload 부착
2. 드라이런: ipcMain.handle 핸들러를 config.js 헬퍼와 연결만 하고, main 로드 무결성 확인
3. 검증(기능): Electron 없이 핸들러 함수가 config.js를 올바로 호출하는지 스텁 테스트 (P1-2 방식)
4. 실앱 검증: 앱 실행 → webview에서 `window.haehanLocal.getEnabledSites()` 호출 → 값 왕복 확인
   (실앱 검증은 앱 재빌드/실행 필요 — 별도 단계)

---

## 6. 범위 / 다음
- 이 기준서 = **브리지(데이터 통로)까지.** 사이트 선택 토글 **화면**은 P1-3 본구현.
- 이후 P1-4(local-agent가 enabled_sites만 활성), P1-5(E2E).

---

## 결정 필요
- 이 브리지 설계로 구현 진행할지?
- webview preload 부착 방식: (a) shell.html에서 attribute 설정(권장) vs (b) mainWindow에서 webview 생성 시 주입 — 현재 webview는 shell.html 내 태그라 (a)가 자연스러움.
