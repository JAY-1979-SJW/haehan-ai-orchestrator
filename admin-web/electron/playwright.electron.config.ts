import { defineConfig } from "@playwright/test";

// Electron 실행 경로는 여기서 지정하지 않는다 — `use.executablePath`는 Playwright
// 타입에 없는 옵션이라 tsc 오류였다(2026-09-28 발견). 각 테스트가
// e2e-electron/launch_helper.ts의 launchApp()으로 electron.launch()에 직접 넘긴다
// (패키징 exe가 있으면 그걸, 없으면 로컬 electron 모듈로 dev 모드).
export default defineConfig({
  testDir: "./e2e-electron",
  timeout: 60_000,
  // 앱이 고정 포트(FastAPI 8401·Next 3000·앱 디버그 9333)를 쓰므로 동시에 두 개를 띄우면 서로 포트를 못 잡아
  // 두 번째 앱의 실행 대기가 시간 초과된다(2026-10-08 E2E 실측: 9333 bind 실패) — 한 번에 하나씩 실행.
  workers: 1,
  fullyParallel: false,
  use: {
    // 스크린샷 실패 시 자동 저장
    screenshot: "on",
    video: "off",
    // CI(desktop-release.yml)가 실패 시 trace를 artifact로 올린다 — 로컬 실행 땐 그냥 무시.
    trace: "retain-on-failure",
  },
  reporter: [["list"], ["html", { open: "never" }]],
});
