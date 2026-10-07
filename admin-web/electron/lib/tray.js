/**
 * lib/tray.js — 시스템 트레이 (이벤트 발행자)
 *
 * 통신 분리: sibling 모듈(mainWindow/youtube)을 직접 import 하지 않는다.
 * 트레이 동작은 버스 이벤트로만 발행하고, 구독(실제 처리)은 컴포지션 루트(main.js)가 한다.
 *   - 열기/클릭/더블클릭 → EVENTS.SHOW_WINDOW
 *   - YouTube 재연결      → EVENTS.YOUTUBE_RECONNECT
 *   - 자동시작 토글       → EVENTS.TOGGLE_AUTO_LAUNCH
 *   - 구글 계정 로그인    → EVENTS.BROWSER_GOOGLE_SIGNIN
 *   - 종료는 electron app API 직접 호출(프레임워크, sibling 모듈 아님)
 */
const { app, Tray, Menu } = require("electron");
const path = require("path");
const fs = require("fs");
const { bus, EVENTS } = require("./bus");
const { loadConfig } = require("./config");

let tray = null;
// 내 Chrome 세션 사용 가능 여부 — cdp_manager 를 직접 import 하지 않게 main(컴포지션 루트)이 넣어 준다.
// Chrome 136 이상은 기본 프로필 원격 연결을 막아 이 옵션이 동작하지 않으므로 회색(선택 불가)으로 보여 준다.
let systemChromeSupported = true;

function setSystemChromeSupport(supported) {
  systemChromeSupported = !!supported;
}

function _buildMenu(autoLaunch) {
  const useSystemChrome = !!(loadConfig().useSystemChromeProfile);
  return Menu.buildFromTemplate([
    { label: "열기", click: () => bus.emit(EVENTS.SHOW_WINDOW) },
    { label: "YouTube 계정 재연결", click: () => bus.emit(EVENTS.YOUTUBE_RECONNECT) },
    { type: "separator" },
    { label: "앱 브라우저에 구글 계정 로그인 (비밀번호 자동 입력)", click: () => bus.emit(EVENTS.BROWSER_GOOGLE_SIGNIN) },
    {
      label: systemChromeSupported ? "내 Chrome 세션 사용 (로그인 유지)" : "내 Chrome 세션 사용 (이 Chrome 버전에서는 불가)",
      type: "checkbox",
      checked: useSystemChrome && systemChromeSupported,
      enabled: systemChromeSupported,
      click: () => bus.emit(EVENTS.TOGGLE_SYSTEM_CHROME),
    },
    {
      label: "Windows 시작 시 자동 실행",
      type: "checkbox",
      checked: autoLaunch,
      click: () => bus.emit(EVENTS.TOGGLE_AUTO_LAUNCH),
    },
    { type: "separator" },
    { label: "Claude 연결", click: () => bus.emit(EVENTS.CLAUDE_CONNECT) },
    { label: "Claude 연결 해제", click: () => bus.emit(EVENTS.CLAUDE_DISCONNECT) },
    { type: "separator" },
    { label: "종료", click: () => app.quit() },
  ]);
}

function createTray(autoLaunch = false) {
  const iconPath = path.join(__dirname, "..", "icon.png");
  if (!fs.existsSync(iconPath)) return null;

  tray = new Tray(iconPath);
  tray.setToolTip("Haehan AI");
  tray.setContextMenu(_buildMenu(autoLaunch));

  tray.on("click", () => bus.emit(EVENTS.SHOW_WINDOW));
  tray.on("double-click", () => bus.emit(EVENTS.SHOW_WINDOW));
  return tray;
}

/** 자동실행 상태가 바뀔 때 트레이 메뉴 체크 상태 갱신 */
function updateAutoLaunchCheck(autoLaunch) {
  if (tray) tray.setContextMenu(_buildMenu(autoLaunch));
}

function hasTray() { return tray !== null; }

module.exports = { createTray, updateAutoLaunchCheck, hasTray, setSystemChromeSupport };
