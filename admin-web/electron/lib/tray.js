/**
 * lib/tray.js — 시스템 트레이 (이벤트 발행자)
 *
 * 통신 분리: sibling 모듈(mainWindow/youtube)을 직접 import 하지 않는다.
 * 트레이 동작은 버스 이벤트로만 발행하고, 구독(실제 처리)은 컴포지션 루트(main.js)가 한다.
 *   - 열기/클릭/더블클릭 → EVENTS.SHOW_WINDOW
 *   - YouTube 재연결      → EVENTS.YOUTUBE_RECONNECT
 *   - 자동시작 토글       → EVENTS.TOGGLE_AUTO_LAUNCH
 *   - 종료는 electron app API 직접 호출(프레임워크, sibling 모듈 아님)
 */
const { app, Tray, Menu } = require("electron");
const path = require("path");
const fs = require("fs");
const { bus, EVENTS } = require("./bus");

let tray = null;

function _buildMenu(autoLaunch) {
  return Menu.buildFromTemplate([
    { label: "열기", click: () => bus.emit(EVENTS.SHOW_WINDOW) },
    { label: "YouTube 계정 재연결", click: () => bus.emit(EVENTS.YOUTUBE_RECONNECT) },
    { type: "separator" },
    {
      label: "Windows 시작 시 자동 실행",
      type: "checkbox",
      checked: autoLaunch,
      click: () => bus.emit(EVENTS.TOGGLE_AUTO_LAUNCH),
    },
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

module.exports = { createTray, updateAutoLaunchCheck, hasTray };
