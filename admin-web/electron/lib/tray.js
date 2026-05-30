/**
 * lib/tray.js — 시스템 트레이
 * 트레이 버그 수정: '열기'·더블클릭 모두 showMainWindow()로 위임 →
 * 창이 숨김/최소화/파괴 어떤 상태든 확실히 앞으로 표시한다.
 */
const { app, Tray, Menu } = require("electron");
const path = require("path");
const fs = require("fs");
const { loadConfig } = require("./config");
const { showMainWindow } = require("./mainWindow");
const { ensureYouTubeAuth } = require("./youtube");

let tray = null;

function createTray() {
  const iconPath = path.join(__dirname, "..", "icon.png");
  if (!fs.existsSync(iconPath)) return null;

  tray = new Tray(iconPath);
  tray.setToolTip("Haehan AI");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "열기", click: () => showMainWindow() },
    { label: "YouTube 계정 재연결", click: () => ensureYouTubeAuth(loadConfig().license_key || "") },
    { type: "separator" },
    { label: "종료", click: () => app.quit() },
  ]));

  tray.on("click", () => showMainWindow());
  tray.on("double-click", () => showMainWindow());
  return tray;
}

function hasTray() { return tray !== null; }

module.exports = { createTray, hasTray };
