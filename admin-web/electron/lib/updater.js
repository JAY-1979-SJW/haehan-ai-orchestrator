/**
 * lib/updater.js — 설치형(NSIS) 앱 자동 업데이트(electron-updater)
 * L9 데스크톱 셸 계층.
 *
 * - 출처: 설치 파일은 공개 저장소(GitHub)에 올리지 않는다(대표님 결정 2026-10-08). 배포는 NAS 이고,
 *   업데이트 주소(latest.yml·설치 파일이 있는 HTTP 폴더)는 config.json 의 update_url 또는 환경변수
 *   HAEHAN_UPDATE_URL 로 받는다. 주소가 없으면 자동 업데이트는 꺼진다(수동 설치로 갱신).
 * - 시작을 막지 않는다: 본 화면이 뜬 뒤 지연 확인, 이후 6시간마다 다시 확인.
 * - 새 버전은 백그라운드로 내려받고, 다 받으면 "지금 재시작" 을 묻는다. 나중을 고르면 앱 종료 시 설치된다.
 * - 끄는 경우: 개발 실행(패키징 안 됨), 포터블 exe(설치 위치가 없어 교체 불가), 자동 점검(HAEHAN_E2E=1),
 *   HAEHAN_DISABLE_UPDATE=1, 업데이트 주소 없음.
 * - 확인·다운로드 실패는 기록만 하고 무시한다(오프라인 PC 에서도 앱은 그대로 쓴다).
 */
const { app, dialog } = require("electron");
const { autoUpdater } = require("electron-updater");
const { loadConfig } = require("./config");
const { stage } = require("./startup_log");

const FIRST_CHECK_DELAY_MS = 15 * 1000;
const RECHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;

let started = false;

function updateDisabledReason() {
  if (!app.isPackaged) return "dev";
  if (process.env.PORTABLE_EXECUTABLE_DIR) return "portable";
  if (process.env.HAEHAN_E2E === "1") return "e2e";
  if (process.env.HAEHAN_DISABLE_UPDATE === "1") return "disabled-by-env";
  if (!updateUrl()) return "no-update-url";
  return "";
}

function updateUrl() {
  const fromEnv = (process.env.HAEHAN_UPDATE_URL || "").trim();
  if (fromEnv) return fromEnv;
  try {
    return String(loadConfig().update_url || "").trim();
  } catch {
    return "";
  }
}

function checkNow() {
  autoUpdater.checkForUpdates().catch((e) => stage("update-check-failed", e.message));
}

function askRestart(getWindow, version) {
  const win = getWindow();
  const opts = {
    type: "info",
    buttons: ["지금 재시작", "나중에"],
    defaultId: 0,
    cancelId: 1,
    title: "업데이트 준비 완료",
    message: `새 버전(${version})을 받았습니다.`,
    detail: "지금 재시작하면 바로 적용됩니다. 나중을 고르면 앱을 끌 때 설치됩니다.",
  };
  const shown = win ? dialog.showMessageBox(win, opts) : dialog.showMessageBox(opts);
  shown
    .then(({ response }) => {
      if (response === 0) autoUpdater.quitAndInstall(true, true);
    })
    .catch((e) => stage("update-dialog-failed", e.message));
}

/**
 * 자동 업데이트를 켠다(한 번만). getWindow: 확인 창을 붙일 본 창을 돌려주는 함수.
 */
function startAutoUpdate(getWindow) {
  if (started) return;
  started = true;
  const reason = updateDisabledReason();
  if (reason) {
    stage("update-off", reason);
    return;
  }
  autoUpdater.setFeedURL({ provider: "generic", url: updateUrl() });
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.on("update-available", (info) => stage("update-available", info.version));
  autoUpdater.on("update-not-available", () => stage("update-none"));
  autoUpdater.on("error", (e) => stage("update-error", e ? e.message : ""));
  autoUpdater.on("update-downloaded", (info) => {
    stage("update-downloaded", info.version);
    askRestart(getWindow, info.version);
  });
  setTimeout(checkNow, FIRST_CHECK_DELAY_MS);
  setInterval(checkNow, RECHECK_INTERVAL_MS).unref();
}

module.exports = { startAutoUpdate, updateDisabledReason };
