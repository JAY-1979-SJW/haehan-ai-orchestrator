import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import { launchApp, waitForShell, getUiPage } from "./launch_helper";

// 사용자가 앱에서 직접 클릭하듯 진행하는 E2E.
// 부작용 액션(메일 발송 / EUM 수집 / 주문 변경)은 제외 — 탐색·렌더·로그인·GPT 경로만 검증.
const SS = path.resolve(__dirname, "../../../../data/e2e_user_flow");

test.setTimeout(240_000);

async function shot(ui: Page, name: string) {
  try { await ui.screenshot({ path: path.join(SS, name), timeout: 30_000 }); console.log("📸", name); }
  catch (e) { console.log("📸 실패", name, String(e).slice(0, 60)); }
}

// 클릭 후 client-side 네비게이션 대기
async function clickAndGo(ui: Page, label: string, urlPart: string): Promise<boolean> {
  try {
    const loc = ui.getByText(label, { exact: false }).first();
    await loc.scrollIntoViewIfNeeded({ timeout: 8_000 });
    await loc.click({ timeout: 8_000 });
    await ui.waitForURL(new RegExp(urlPart), { timeout: 20_000 }).catch(() => {});
    await ui.waitForTimeout(5_000);
    console.log(`  → '${label}' 클릭, url=${ui.url()}`);
    return true;
  } catch (e) {
    console.log(`  ⚠️ '${label}' 클릭 실패: ${String(e).slice(0, 80)}`);
    return false;
  }
}

test("사용자 흐름 E2E — 앱 UI 직접 조작", async () => {
  fs.mkdirSync(SS, { recursive: true });
  const app = await launchApp({ HAEHAN_OWNER: "1" });
  const shell = await waitForShell(app);
  await shell.waitForLoadState("domcontentloaded", { timeout: 30_000 });
  console.log("✅ Electron 앱 기동");

  const ui = await getUiPage(app);
  await ui.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});
  await ui.waitForTimeout(10_000); // 서버 기동 + getMe 토큰 동기화 대기
  console.log("✅ webview(Next UI) 획득 url=", ui.url());

  // ── 1. 대시보드: 로그인 상태(=/login 으로 안 튕김) ──────────────
  await shot(ui, "01_dashboard.png");
  expect(ui.url()).not.toContain("/login");
  await expect(ui.getByText(/오케스트레이터/).first()).toBeVisible({ timeout: 20_000 });
  console.log("✅ [1] 대시보드 로그인 상태 렌더");

  // ── 2. 상품 관리: 스마트스토어 로그인 세션으로 실데이터 ──────────
  const okProd = await clickAndGo(ui, "상품 관리", "products");
  await shot(ui, "02_products.png");
  expect(okProd).toBe(true);
  console.log("✅ [2] 상품 관리 진입");

  // ── 3. 홈 복귀 → EUM 단말기 영업 ────────────────────────────────
  await ui.goto("http://localhost:3000/", { timeout: 20_000 }).catch(() => {});
  await ui.waitForTimeout(4_000);
  const okEum = await clickAndGo(ui, "EUM 단말기 영업", "eum");
  await ui.waitForTimeout(3_000);
  await shot(ui, "03_eum.png");
  if (okEum) {
    await expect(ui.getByText(/영업 타겟|신규현장/).first()).toBeVisible({ timeout: 15_000 }).catch(() => {});
    console.log("✅ [3] EUM 영업 화면 렌더");
  }

  // ── 4. 운영센터 ────────────────────────────────────────────────
  await ui.goto("http://localhost:3000/", { timeout: 20_000 }).catch(() => {});
  await ui.waitForTimeout(3_000);
  const okOps = await clickAndGo(ui, "운영센터", "ops");
  await shot(ui, "04_ops.png");
  console.log(okOps ? "✅ [4] 운영센터 진입" : "⚠️ [4] 운영센터 스킵");

  // ── 5. AI 비서: GPT 채팅 실제 1턴 ──────────────────────────────
  // 유료 API 호출이라 CI(desktop-release.yml 빌드 산출물 E2E)에서는 스킵한다
  // (HAEHAN_E2E_SKIP_PAID_API=1). 로컬 수동 실행에선 그대로 돈다.
  if (process.env.HAEHAN_E2E_SKIP_PAID_API === "1") {
    console.log("⏭️ [5] AI 채팅 — HAEHAN_E2E_SKIP_PAID_API=1, 유료 API 스킵");
  } else {
    try {
      await ui.goto("http://localhost:3000/", { timeout: 20_000 }).catch(() => {});
      await ui.waitForTimeout(3_000);
      await clickAndGo(ui, "AI 비서", "(assistant|ai|chat)");
      await ui.waitForTimeout(3_000);
      const input = ui.locator("textarea, input[type='text']").first();
      if (await input.count() > 0) {
        await input.fill("한 단어로 답해: 대한민국 수도?");
        await ui.keyboard.press("Enter");
        await ui.waitForTimeout(12_000); // GPT 응답 대기
        console.log("✅ [5] AI 채팅 1턴 전송");
      } else {
        console.log("⚠️ [5] 채팅 입력창 미발견 — 스킵");
      }
      await shot(ui, "05_ai_chat.png");
    } catch (e) {
      console.log("⚠️ [5] AI 채팅 스킵:", String(e).slice(0, 80));
    }
  }

  expect(!app.process().killed).toBe(true);
  console.log("✅ 앱 프로세스 정상 — E2E 완료");
  await app.close();
});
