import { defineConfig } from "@playwright/test";
import path from "path";

const EXE = path.resolve(
  __dirname,
  "../../dist-installer/win-unpacked/Haehan AI.exe"
);

export default defineConfig({
  testDir: "./e2e-electron",
  timeout: 60_000,
  use: {
    // Electron 앱 직접 실행
    executablePath: EXE,
    // 스크린샷 실패 시 자동 저장
    screenshot: "on",
    video: "off",
  },
  reporter: [["list"], ["html", { open: "never" }]],
});
