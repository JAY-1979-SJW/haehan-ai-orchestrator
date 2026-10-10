import { _electron as electron, chromium } from "@playwright/test";
import type { ElectronApplication, Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

// 패키징 exe가 있으면 그걸 쓰고(배포본 검증), 없으면 로컬 electron 모듈로
// `electron .` 방식 개발 모드를 대신 띄운다.
// (2026-09-28: PyInstaller 빌드/인스톨러 파이프라인을 복원하지 않아 패키징 exe가
// 없는 상태에서도 e2e를 돌릴 수 있게 — Playwright 공식 문서: executablePath 생략 시
// node_modules/.bin/electron을 쓰고, args로 앱 진입점을 넘긴다.)
const PACKAGED_EXE = path.resolve(
  __dirname,
  "../../../dist-installer/win-unpacked/Haehan AI.exe"
);
const DEV_ROOT = path.resolve(__dirname, ".."); // admin-web/electron

// CI에서는 빌드 산출물(portable 압축 해제본 또는 --dir unpacked)의 실제 경로를
// 환경변수로 넘긴다 — dist 폴더 이름(dist-electron-new)·버전별 하위 경로가 매
// 빌드 달라져서 상대경로 하나로는 못 맞춘다.
const EXE_FROM_ENV = process.env.HAEHAN_E2E_EXE_PATH;

export function launchApp(
  extraEnv: Record<string, string> = {},
  extraArgs: string[] = []
) {
  // process.env 값은 string | undefined라 Playwright의 env({[key: string]: string})
  // 타입과 안 맞는다 — undefined 항목을 걸러낸다.
  const env: Record<string, string> = {};
  // HAEHAN_E2E=1: 시작 실패 시 사람이 닫아야 하는 오류 창 대신 바로 종료(main.js failStartup)
  for (const [k, v] of Object.entries({ ...process.env, HAEHAN_E2E: "1", ...extraEnv })) {
    if (v !== undefined) env[k] = v;
  }
  const packagedExe = EXE_FROM_ENV && fs.existsSync(EXE_FROM_ENV) ? EXE_FROM_ENV : PACKAGED_EXE;
  if (fs.existsSync(packagedExe)) {
    return electron.launch({ executablePath: packagedExe, args: extraArgs, env });
  }
  console.log("[e2e] 패키징 exe 없음 — 개발 모드(electron .)로 대체:", DEV_ROOT);
  return electron.launch({ args: [".", ...extraArgs], cwd: DEV_ROOT, env });
}

// 메인 창은 먼저 대기 화면으로 뜨고, 서버가 준비되면 shell.html(본 화면)로 바뀐다 — 본 화면이 될 때까지 기다린다.
export async function waitForShell(app: ElectronApplication, timeoutMs = 180_000): Promise<Page> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const p of app.windows()) {
      let u = "";
      try { u = p.url(); } catch { /* 닫힌 창 */ }
      if (u.includes("shell.html")) return p;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("본 화면(shell.html)이 열리지 않음 — userData\\logs\\startup.log·fastapi.log 확인");
}

// webview(Next UI) 콘텐츠의 실제 상호작용 가능한 Page.
// <webview> 태그(main.js:75 getType()==="webview", lib/mainWindow.js webviewTag:true)가 만드는
// guest webContents 는 electronApp.windows() 에 안 잡힌다(2026-10-10, app.spec.ts만 통과하고
// fresh_install_signup/user_flow/agent_employee_eval 의 getUiPage()가 app.windows() 로 찾다가
// 90초 타임아웃하던 결함 — app.spec.ts 는 webview 를 찾지 않고 메인 창 DOM 에서 <webview> 존재만
// 확인해서 통과했다). main.js 가 이미 ready 이전에 `remote-debugging-port=9333`(앱 자신의 창·webview
// 전용, 9222는 사용자 Chrome 자동화용이라 겹치지 않게 분리됨)을 열어 두므로, 그 CDP 로 연결해
// 실제 webview 페이지를 찾는다.
export async function getUiPage(app: ElectronApplication, timeoutMs = 90_000): Promise<Page> {
  await waitForShell(app); // shell.html 이 뜬 뒤에야 그 안의 <webview> 가 생성된다
  const browser = await chromium.connectOverCDP("http://127.0.0.1:9333");
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const ctx of browser.contexts()) {
      for (const p of ctx.pages()) {
        let u = "";
        try { u = p.url(); } catch { /* 닫힌 페이지 */ }
        if (/(localhost|127\.0\.0\.1):3000/.test(u)) return p;
      }
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("webview(Next UI) 페이지를 찾지 못함 (CDP 9333 로도 못 찾음)");
}
