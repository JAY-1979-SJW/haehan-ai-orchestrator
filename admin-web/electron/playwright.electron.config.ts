import { defineConfig } from "@playwright/test";

// Electron 실행 경로는 여기서 지정하지 않는다 — `use.executablePath`는 Playwright
// 타입에 없는 옵션이라 tsc 오류였다(2026-09-28 발견). 각 테스트가
// e2e-electron/launch_helper.ts의 launchApp()으로 electron.launch()에 직접 넘긴다
// (패키징 exe가 있으면 그걸, 없으면 로컬 electron 모듈로 dev 모드).
export default defineConfig({
  testDir: "./e2e-electron",
  timeout: 60_000,
  use: {
    // 스크린샷 실패 시 자동 저장
    screenshot: "on",
    video: "off",
  },
  reporter: [["list"], ["html", { open: "never" }]],
});
