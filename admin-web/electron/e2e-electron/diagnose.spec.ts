import { test } from "@playwright/test";
import type { Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import { launchApp } from "./launch_helper";

// 실제 앱 webview 를 백그라운드로 띄워 오류를 계측한다(콘솔/네트워크/DOM + 스크린샷).
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
  // 2026-09-29: GCP 상태 버그(web_connector.py Playwright leak, defect_index #91)의 실제
  // 노출 문구 "It looks like you are using Playwright Sync API inside the asyncio loop.
  // Please use the Async API instead."는 오류/실패/에러/error/failed 어느 키워드도 안 담고
  // 있어서 기존 정규식으로는 못 잡혔다 — 백엔드 내부 예외/트레이스백이 그대로 화면에 샌
  // 케이스를 잡기 위해 asyncio/Traceback/Exception/raise 계열 키워드 추가.
  return ui.evaluate(`(() => {
    const hits = [];
    document.querySelectorAll('*').forEach(e => {
      const t = (e.childElementCount === 0 ? (e.innerText || '') : '').trim();
      if (t && /오류|실패|에러|error|failed|unavailable|연결.*실패|로그인 필요|문제|Backend|asyncio|Traceback|Exception|raise |playwright sync api/i.test(t) && t.length < 200) hits.push(t);
    });
    return [...new Set(hits)].slice(0, 15);
  })()`) as Promise<string[]>;
}

test("앱 webview 오류 진단", async () => {
  fs.mkdirSync(SS, { recursive: true });
  const app = await launchApp({ HAEHAN_OWNER: "1" });
  const consoleErrs: string[] = [];
  const failed: string[] = [];

  const ui = await getUiPage(app);
  ui.on("console", (m) => { if (m.type() === "error") consoleErrs.push(`ERR ${m.text().slice(0, 180)}`); });
  ui.on("response", (r) => { try { if (r.status() >= 400) failed.push(`${r.status()} ${r.request().method()} ${r.url().split(":3000")[1]?.slice(0, 80) ?? r.url().slice(0, 80)}`); } catch { /* */ } });
  ui.on("pageerror", (e) => consoleErrs.push(`PAGEERR ${String(e).slice(0, 180)}`));

  await ui.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});
  await ui.waitForTimeout(12_000);

  // 2026-09-29: mail/google 신설 페이지 추가(admin-web 메뉴 도메인 분리, 커밋 f85f32b8 전후).
  // clickQueryButtons: true인 페이지는 로드만이 아니라 "조회" 버튼까지 실제로 눌러본다 —
  // GCP 상태 버그(web_connector.py Playwright 인스턴스 leak, defect_index #91)가 페이지
  // 로드만으로는 안 보이고 버튼을 눌러야만 드러났던 사례 반영.
  const steps: { name: string; url: string; clickQueryButtons?: boolean }[] = [
    { name: "dashboard", url: "http://localhost:3000/" },
    { name: "smartstore_products", url: "http://localhost:3000/naver/smartstore/products" },
    { name: "smartstore_home", url: "http://localhost:3000/naver/smartstore" },
    { name: "ops", url: "http://localhost:3000/ops" },
    { name: "mail", url: "http://localhost:3000/mail", clickQueryButtons: true },
    { name: "google", url: "http://localhost:3000/google", clickQueryButtons: true },
  ];
  for (const s of steps) {
    await ui.goto(s.url, { timeout: 25_000 }).catch(() => {});
    await ui.waitForTimeout(7_000);

    if (s.clickQueryButtons) {
      // 화면에 보이는 "조회" 버튼을 전부 순서대로 클릭 — 버튼 뒤 실제 API 호출까지 검증.
      const buttons = ui.getByRole("button", { name: "조회" });
      const count = await buttons.count().catch(() => 0);
      console.log(`  [${s.name}] "조회" 버튼 ${count}개 발견 — 순차 클릭`);
      for (let i = 0; i < count; i++) {
        try {
          await buttons.nth(i).click({ timeout: 8_000 });
          await ui.waitForTimeout(9_000); // CDP/API 호출 완료 대기(GCP 등은 7~10초)
        } catch (e) {
          console.log(`    ⚠️ 버튼[${i}] 클릭 실패: ${String(e).slice(0, 80)}`);
        }
      }
    }

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
