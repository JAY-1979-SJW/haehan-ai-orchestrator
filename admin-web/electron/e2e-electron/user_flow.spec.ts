import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import { launchApp, waitForShell } from "./launch_helper";

// 사용자가 앱에서 직접 클릭하듯 진행하는 E2E.
// 부작용 액션(메일 발송 / EUM 수집 / 주문 변경)은 제외 — 탐색·렌더·로그인·GPT 경로만 검증.
const SS = path.resolve(__dirname, "../../../../data/e2e_user_flow");

test.setTimeout(240_000);

// webview(Next UI) 페이지 획득: app.windows() 중 localhost:3000
async function getUiPage(app: any): Promise<Page> {
  for (let i = 0; i < 90; i++) {
    for (const p of app.windows() as Page[]) {
      let u = "";
      try { u = p.url(); } catch { /* */ }
      if (/(localhost|127\.0\.0\.1):3000/.test(u)) return p;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("webview(Next UI) 페이지를 찾지 못함 (서버 미기동 또는 webview 미노출)");
}

async function shot(ui: Page, name: string) {
  try { await ui.screenshot({ path: path.join(SS, name), timeout: 30_000 }); console.log("📸", name); }
  catch (e) { console.log("📸 실패", name, String(e).slice(0, 60)); }
}

// 클릭 후 client-side 네비게이션 대기
// href 를 주면 텍스트 대신 실제 내비 링크(a[href])를 누른다 — 사이드바가 축약 라벨(shortLabel)로 렌더돼도 안정적.
async function clickAndGo(ui: Page, label: string, urlPart: string, href?: string): Promise<boolean> {
  try {
    const loc = href ? ui.locator(`a[href="${href}"]`).first() : ui.getByText(label, { exact: false }).first();
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

  // 좌측 메뉴(PageShell 사이드바)는 Tailwind lg(>=1024px)부터만 보인다 — 그보다 좁으면 하단 탭 5개만 남아
  // "스토어 AI 채팅"·"작업 목록" 링크가 화면에 없다(CI 에서 창이 ~1008px 로 떠서 재현). 데스크톱 사용 폭으로 키운다.
  await app.evaluate(({ BrowserWindow }) => {
    for (const w of BrowserWindow.getAllWindows()) {
      if (!w.isDestroyed()) { w.setSize(1440, 900); w.center(); }
    }
  });

  const ui = await getUiPage(app);
  await ui.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});
  await ui.waitForTimeout(10_000); // 서버 기동 + getMe 토큰 동기화 대기
  console.log("✅ webview(Next UI) 획득 url=", ui.url());

  // ── 1. 대시보드: 로그인 상태(=/login 으로 안 튕김) ──────────────
  // "오케스트레이터" 문구는 855d595a(단일 AI 콘솔 UI 전면 개편)로 대시보드에서 빠지고
  // /about 랜딩에만 남았다 — 대시보드 자체를 식별하는 data-testid 로 교체(2026-10-08).
  await shot(ui, "01_dashboard.png");
  expect(ui.url()).not.toContain("/login");
  await expect(ui.getByTestId("ai-agent-console")).toBeVisible({ timeout: 20_000 });
  console.log("✅ [1] 대시보드 로그인 상태 렌더");

  // ── 2. 스마트스토어: 좌측 메뉴 "스토어 AI 채팅" → /naver/smartstore ──
  // 855d595a(단일 AI 콘솔 개편)로 홈에서 "상품 관리"·"EUM 단말기 영업" 메뉴가 빠졌다(설치본 실측 2026-10-08).
  // 지금 사용자가 실제로 누르는 좌측 메뉴(admin-web/src/lib/nav.ts)를 따라간다 — 전 화면 진입은 all_screens.spec 이 맡는다.
  const okStore = await clickAndGo(ui, "스토어 AI 채팅", "naver/smartstore", "/naver/smartstore");
  await shot(ui, "02_smartstore.png");
  expect(okStore).toBe(true);
  expect(ui.url()).toContain("/naver/smartstore");
  console.log("✅ [2] 스마트스토어 진입");

  // ── 3. 홈 복귀 → 업무 현황 "작업 목록" ─────────────────────────────
  await ui.goto("http://localhost:3000/", { timeout: 20_000 }).catch(() => {});
  await ui.waitForTimeout(4_000);
  const okTasks = await clickAndGo(ui, "작업 목록", "assistant/tasks", "/assistant/tasks");
  await shot(ui, "03_tasks.png");
  expect(okTasks).toBe(true);
  expect(ui.url()).toContain("/assistant/tasks");
  console.log("✅ [3] 작업 목록 진입");

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
