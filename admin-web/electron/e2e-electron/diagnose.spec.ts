import { test, _electron as electron } from "@playwright/test";
import type { Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

// 실제 앱 webview 를 백그라운드로 띄워 오류를 계측한다(콘솔/네트워크/DOM + 스크린샷).
const EXE = path.resolve(__dirname, "../../../dist-installer/win-unpacked/Haehan AI.exe");
const SS = path.resolve(__dirname, "../../../../data/diagnose");

test.setTimeout(240_000);

async function getUiPage(app: any): Promise<Page> {
  for (let i = 0; i < 90; i++) {
    for (const p of app.windows() as Page[]) {
      let u = ""; try { u = p.url(); } catch { /* */ }
      if (/(localhost|127\.0\.0\.1):3000/.test(u)) return p;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("webview 미발견");
}

async function domErrors(ui: Page): Promise<string[]> {
  return ui.evaluate(`(() => {
    const hits = [];
    document.querySelectorAll('*').forEach(e => {
      const t = (e.childElementCount === 0 ? (e.innerText || '') : '').trim();
      if (t && /오류|실패|에러|error|failed|unavailable|연결.*실패|로그인 필요|문제|Backend/i.test(t) && t.length < 140) hits.push(t);
    });
    return [...new Set(hits)].slice(0, 15);
  })()`) as Promise<string[]>;
}

test("앱 webview 오류 진단", async () => {
  fs.mkdirSync(SS, { recursive: true });
  const app = await electron.launch({ executablePath: EXE, env: { ...process.env, HAEHAN_OWNER: "1" } });
  const consoleErrs: string[] = [];
  const failed: string[] = [];

  const ui = await getUiPage(app);
  ui.on("console", (m) => { if (m.type() === "error") consoleErrs.push(`ERR ${m.text().slice(0, 180)}`); });
  ui.on("response", (r) => { try { if (r.status() >= 400) failed.push(`${r.status()} ${r.request().method()} ${r.url().split(":3000")[1]?.slice(0, 80) ?? r.url().slice(0, 80)}`); } catch { /* */ } });
  ui.on("pageerror", (e) => consoleErrs.push(`PAGEERR ${String(e).slice(0, 180)}`));

  await ui.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});
  await ui.waitForTimeout(12_000);

  const steps = [
    { name: "dashboard", url: "http://localhost:3000/" },
    { name: "smartstore_products", url: "http://localhost:3000/naver/smartstore/products" },
    { name: "smartstore_home", url: "http://localhost:3000/naver/smartstore" },
    { name: "ops", url: "http://localhost:3000/ops" },
  ];
  for (const s of steps) {
    await ui.goto(s.url, { timeout: 25_000 }).catch(() => {});
    await ui.waitForTimeout(7_000);
    const de = await domErrors(ui).catch(() => []);
    await ui.screenshot({ path: path.join(SS, `${s.name}.png`), timeout: 30_000 }).catch(() => {});
    console.log(`\n=== [${s.name}] url=${ui.url()} ===`);
    console.log("  로그인튕김:", ui.url().includes("/login"));
    console.log("  DOM오류문구:", JSON.stringify(de));
  }

  console.log("\n========== 콘솔 에러 ==========");
  for (const e of consoleErrs.slice(0, 25)) console.log("  ", e);
  console.log("========== 실패 네트워크(4xx/5xx) ==========");
  for (const f of failed.slice(0, 30)) console.log("  ", f);
  console.log("\n스크린샷:", SS);
  await app.close();
});
