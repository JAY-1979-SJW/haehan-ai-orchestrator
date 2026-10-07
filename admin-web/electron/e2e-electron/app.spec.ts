import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import { launchApp, waitForShell } from "./launch_helper";

const SS_DIR = path.resolve(
  __dirname,
  "../../../../data/screenshots_check/electron"
);

test.setTimeout(240_000);

test("Electron 앱 기능 점검", async () => {
  fs.mkdirSync(SS_DIR, { recursive: true });

  const app = await launchApp({ HAEHAN_OWNER: "1" });

  const win = await waitForShell(app);
  await win.waitForLoadState("domcontentloaded", { timeout: 30_000 });

  // 1. webview 태그 존재
  const hasWebview = await win.evaluate(() => !!document.querySelector("webview"));
  expect(hasWebview).toBe(true);
  console.log("✅ webview 태그 확인");

  // 2. webview src = Next.js URL
  const src = await win.evaluate(() => (document.querySelector("webview") as any)?.src ?? "");
  expect(src).toMatch(/localhost|127\.0\.0\.1/);
  console.log("✅ webview src:", src);

  // 3. electronAPI 노출 확인
  const hasElectronAPI = await win.evaluate(() => typeof (window as any).electronAPI !== "undefined");
  console.log("electronAPI:", hasElectronAPI);

  // 4. 서버 기동 대기 후 스크린샷 (폰트 타임아웃 60s로 확장)
  await win.waitForTimeout(15_000);
  await win.screenshot({
    path: path.join(SS_DIR, "01_electron_launch.png"),
    timeout: 60_000,
  });
  console.log("✅ 스크린샷 저장:", SS_DIR);

  // 5. 앱 살아있음
  expect(!app.process().killed).toBe(true);
  console.log("✅ 앱 프로세스 정상");

  await app.close();
});
