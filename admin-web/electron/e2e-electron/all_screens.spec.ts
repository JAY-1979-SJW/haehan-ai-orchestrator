import { test, expect } from "@playwright/test";
import type { ElectronApplication, Page, Response } from "@playwright/test";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { launchApp } from "./launch_helper";

// 전 화면 스모크 — 안전등급 A(읽기 전용·로컬) 페이지 경로를 전부 한 번씩 열어
// "화면이 뜨는가"만 본다. 기준서: C:\work\_coordination\APP_FEATURE_CHECKLIST.md
//
// 경로마다 확인하는 것:
//   1) 문서 응답 코드가 정상(< 400)이고 예기치 않게 /setup·/login 으로 튕기지 않음
//   2) Next.js 오류 화면(error.tsx "페이지 오류", global-error "앱 오류", dev 오버레이) 없음
//   3) 잡히지 않은 페이지 오류(pageerror) 0건
//   4) 백엔드(127.0.0.1:8401, 또는 Next 프록시 /api/proxy·/orchestrator) 응답 중 status >= 500 0건
//   5) 스크린샷을 test-results 에 저장
//
// 안전 장치(약화 금지):
//   - 버튼·링크를 전혀 누르지 않는다. 오직 URL 이동(GET 문서)만 한다.
//   - 로그인 이후에는 백엔드/프록시로 가는 GET/HEAD/OPTIONS 외 모든 요청을 차단(abort)한다 —
//     화면이 스스로 쓰기·발송 요청을 보내더라도 외부로 나가지 않는다. 차단 건수는 보고서에 남는다.
//   - HAEHAN_E2E_SKIP_PAID_API=1 을 앱에 넘긴다(유료 AI API 호출 경로는 실행하지 않는다는 표식).
//   - 임시 --user-data-dir 로 새 PC 상태에서 시작하므로 실제 사용자 데이터·세션을 건드리지 않는다.
//
// 실패는 경로별 테스트로 나뉘어 기록되고, 마지막 "요약" 테스트가 전체 실패 목록을 한꺼번에 출력한다.
// 앱은 포트 3000/8401/9333 을 쓰므로 다른 앱이 떠 있으면 실행하지 말 것(workers: 1 로 한 번에 하나).

type RouteSpec = {
  /** 실제 접속 경로 — (legacy) 같은 라우트 그룹 폴더는 URL 에 안 나타난다 */
  url: string;
  /** src/app 의 page.tsx 위치(점검표와 대조용) */
  source: string;
  /** 화면 설명 */
  title: string;
  /** 인증 없이 열리는 공개 화면(미들웨어 PUBLIC_PATHS) */
  isPublic?: boolean;
  /** 열린 뒤 다른 곳으로 이동하는 것이 정상인 경로(예: /setup 은 등록 후 / 로 간다) */
  redirectOk?: boolean;
};

// 점검표 1장 "Next.js 페이지 경로" 와 1:1. 동적 경로는 안전한 샘플이 있는 것만 넣는다:
//   /assistant/tasks/[id] → mock 데이터 id "task-001" (외부 데이터 불필요, 없는 id 도 mock 대체 표시)
export const ROUTES: RouteSpec[] = [
  { url: "/", source: "page.tsx", title: "AI 콘솔(홈)", isPublic: true },
  { url: "/about", source: "about/page.tsx", title: "소개", isPublic: true },
  { url: "/login", source: "login/page.tsx", title: "로그인(웹 모드용)", isPublic: true },
  { url: "/signup", source: "signup/page.tsx", title: "가입(웹 모드용)", isPublic: true },
  { url: "/setup", source: "setup/page.tsx", title: "첫 실행 설정", isPublic: true, redirectOk: true },
  { url: "/mypage", source: "mypage/page.tsx", title: "설정(마이페이지)" },
  { url: "/ops", source: "ops/page.tsx", title: "운영센터" },
  { url: "/mail", source: "mail/page.tsx", title: "메일 비서(Gmail)" },
  { url: "/mailbox", source: "mailbox/page.tsx", title: "네이버 메일함" },
  { url: "/mailbox/bulk", source: "mailbox/bulk/page.tsx", title: "메일 대량 발송 승인서" },
  { url: "/hanafax", source: "hanafax/page.tsx", title: "하나팩스" },
  { url: "/gongmu", source: "gongmu/page.tsx", title: "건설업 공무" },
  { url: "/site-map", source: "site-map/page.tsx", title: "사이트 업무 지도" },
  { url: "/google", source: "google/page.tsx", title: "구글 허브" },
  { url: "/login-status", source: "login-status/page.tsx", title: "로그인 세션 현황" },
  { url: "/scheduled", source: "scheduled/page.tsx", title: "예약 작업" },
  { url: "/naver/blog", source: "naver/blog/page.tsx", title: "블로그 AI" },
  { url: "/naver/session", source: "naver/session/page.tsx", title: "네이버 세션" },
  { url: "/naver/keywords", source: "naver/(legacy)/keywords/page.tsx", title: "키워드·경쟁사 조사" },
  { url: "/naver/smartstore", source: "naver/(legacy)/smartstore/page.tsx", title: "스마트스토어 관리" },
  { url: "/naver/smartstore/products", source: "naver/(legacy)/smartstore/products/page.tsx", title: "상품 관리" },
  { url: "/naver/smartstore/orders", source: "naver/(legacy)/smartstore/orders/page.tsx", title: "주문/정산" },
  { url: "/naver/smartstore/settlements", source: "naver/(legacy)/smartstore/settlements/page.tsx", title: "정산 관리" },
  { url: "/naver/smartstore/reviews", source: "naver/(legacy)/smartstore/reviews/page.tsx", title: "리뷰/문의" },
  { url: "/naver/smartstore/stats", source: "naver/(legacy)/smartstore/stats/page.tsx", title: "데이터 분석" },
  { url: "/naver/smartstore/marketing", source: "naver/(legacy)/smartstore/marketing/page.tsx", title: "마케팅/혜택" },
  { url: "/assistant", source: "assistant/page.tsx", title: "어시스턴트 대시보드" },
  { url: "/assistant/approval", source: "assistant/approval/page.tsx", title: "승인 게이트" },
  { url: "/assistant/tasks", source: "assistant/(legacy)/tasks/page.tsx", title: "작업 목록" },
  { url: "/assistant/tasks/task-001", source: "assistant/(legacy)/tasks/[id]/page.tsx", title: "작업 상세(mock 샘플 id)" },
  { url: "/assistant/inbox", source: "assistant/(legacy)/inbox/page.tsx", title: "수신함" },
  { url: "/assistant/cafe", source: "assistant/(legacy)/cafe/page.tsx", title: "네이버 카페 수집(읽기)" },
  { url: "/assistant/news", source: "assistant/(legacy)/news/page.tsx", title: "뉴스(읽기)" },
  { url: "/assistant/logs", source: "assistant/(legacy)/logs/page.tsx", title: "감사 로그" },
  { url: "/assistant/storage", source: "assistant/(legacy)/storage/page.tsx", title: "저장소 상태" },
  { url: "/assistant/deployment", source: "assistant/(legacy)/deployment/page.tsx", title: "배포 현황" },
  { url: "/assistant/external-sites", source: "assistant/(legacy)/external-sites/page.tsx", title: "외부 사이트 제공자" },
];

// 앱(webview)이 실제로 쓰는 origin 은 http://127.0.0.1:3000 (lib/config.js SERVER_URL). 세션 쿠키·localStorage 는
// origin(호스트) 단위라 localhost:3000 으로 이동하면 토큰이 없어 모든 보호 경로가 /setup 으로 튕긴다.
// 그래서 고정값 대신 webview 가 열려 있는 origin 을 beforeAll 에서 읽어 쓴다.
let BASE = "http://127.0.0.1:3000";
const OUT_DIR = path.resolve(__dirname, "../test-results");
const REPORT = path.join(OUT_DIR, "all_screens_report.jsonl");

// 화면이 오류 상태일 때 나타나는 문구(error.tsx / global-error.tsx / not-found.tsx / Next dev 오버레이)
const ERROR_TEXT =
  /페이지 오류|앱 오류|페이지를 찾을 수 없습니다|Application error|Unhandled Runtime Error|This page could not be found|Internal Server Error|Server Error/;

const BACKEND_URL = /(127\.0\.0\.1|localhost):8401|\/api\/proxy\/|\/orchestrator\//;

type Row = {
  url: string;
  ok: boolean;
  failures: string[];
  blockedWrites: number;
  finalUrl: string;
};

async function getUiPage(app: ElectronApplication): Promise<Page> {
  for (let i = 0; i < 120; i++) {
    for (const p of app.windows() as Page[]) {
      let u = "";
      try { u = p.url(); } catch { /* 닫힌 창 */ }
      if (/(localhost|127\.0\.0\.1):3000/.test(u)) return p;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("webview(Next UI) 페이지를 찾지 못함 — userData\\logs\\startup.log·fastapi.log 확인");
}

// 실패한 테스트가 있으면 Playwright 가 워커를 새로 띄우고 beforeAll 을 다시 돈다 — 보고서는 그 사이에도 남아야 하므로
// 메인 프로세스(워커 번호 없음)에서 실행 시작 때 한 번만 비운다.
if (process.env.TEST_WORKER_INDEX === undefined) {
  fs.rmSync(REPORT, { force: true });
}

function appendRow(row: Row) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.appendFileSync(REPORT, JSON.stringify(row) + "\n", "utf8");
}

test.describe("전 화면 스모크(안전등급 A, 읽기 전용)", () => {
  test.setTimeout(180_000);

  let app: ElectronApplication;
  let ui: Page;
  let tmpUserData: string;
  // 현재 점검 중인 경로에서 모은 관찰값 — 경로 테스트마다 비운다
  let pageErrors: string[] = [];
  let serverErrors: string[] = [];
  let blockedWrites = 0;

  test.beforeAll(async () => {
    test.setTimeout(600_000);
    // 새 PC 첫 설치와 같은 상태: 빈 userData(실제 사용자 DB·서버는 건드리지 않음)
    tmpUserData = fs.mkdtempSync(path.join(os.tmpdir(), "haehan-e2e-allscreens-"));
    app = await launchApp(
      { HAEHAN_E2E_SKIP_PAID_API: "1" },
      [`--user-data-dir=${tmpUserData}`]
    );
    ui = await getUiPage(app);
    await ui.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});
    BASE = new URL(ui.url()).origin;

    // 첫 실행이면 /setup — 이름·이메일만 입력(fresh_install_signup.spec.ts 와 같은 선택자)
    await ui.waitForURL(/\/setup/, { timeout: 30_000 }).catch(() => {});
    if (/\/setup/.test(ui.url())) {
      await ui.locator("#setup-name").fill("Smoke Tester");
      await ui.locator("#setup-email").fill("smoke-tester@e2e.test");
      await ui.locator("#setup-submit").click();
      await expect(ui).toHaveURL(/^(?!.*\/(setup|login)).*$/, { timeout: 30_000 });
    }

    // 안전 장치: 이후 백엔드/프록시로 나가는 쓰기성 요청(POST/PUT/DELETE/PATCH)은 전부 차단
    await ui.route("**/*", async (route) => {
      const req = route.request();
      const m = req.method();
      if (BACKEND_URL.test(req.url()) && m !== "GET" && m !== "HEAD" && m !== "OPTIONS") {
        blockedWrites++;
        await route.abort("blockedbyclient");
        return;
      }
      await route.continue();
    });

    ui.on("pageerror", (err) => pageErrors.push(`${err.name}: ${err.message}`.slice(0, 300)));
    ui.on("response", (res: Response) => {
      const u = res.url();
      if (BACKEND_URL.test(u) && res.status() >= 500) {
        serverErrors.push(`${res.status()} ${res.request().method()} ${u}`.slice(0, 300));
      }
    });
  });

  test.afterAll(async () => {
    try { await app?.close(); } catch { /* 이미 종료 */ }
    if (tmpUserData) fs.rmSync(tmpUserData, { recursive: true, force: true });
  });

  for (const r of ROUTES) {
    test(`화면 ${r.url} — ${r.title}`, async ({}, testInfo) => {
      pageErrors = [];
      serverErrors = [];
      blockedWrites = 0;
      const failures: string[] = [];

      let status = 0;
      try {
        const res = await ui.goto(BASE + r.url, { waitUntil: "domcontentloaded", timeout: 45_000 });
        status = res?.status() ?? 0;
      } catch (e) {
        failures.push(`이동 실패: ${(e as Error).message.split("\n")[0]}`);
      }
      // 클라이언트 렌더·초기 API 호출이 끝나길 기다린다(끝나지 않는 폴링 화면이 있어 상한을 둔다)
      await ui.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
      await ui.waitForTimeout(1_500);

      const finalUrl = ui.url();
      if (status >= 400) failures.push(`문서 응답 코드 ${status}`);
      if (status === 0 && failures.length === 0) failures.push("문서 응답 없음");

      // 예기치 않은 로그인/설정 화면으로 튕김(세션 풀림)
      if (!r.redirectOk && r.url !== "/login" && r.url !== "/signup" && /\/(setup|login)(\?|$|\/)/.test(finalUrl)) {
        failures.push(`로그인/설정 화면으로 튕김: ${finalUrl}`);
      }

      // 오류 화면 문구 / Next dev 오류 오버레이
      const bodyText = (await ui.locator("body").innerText({ timeout: 5_000 }).catch(() => "")) || "";
      const hit = bodyText.match(ERROR_TEXT);
      if (hit) failures.push(`오류 화면 문구 발견: "${hit[0]}"`);
      if ((await ui.locator("nextjs-portal").count().catch(() => 0)) > 0) {
        failures.push("Next.js 오류 오버레이(nextjs-portal) 표시됨");
      }
      if (bodyText.trim().length === 0) failures.push("화면이 비어 있음(본문 텍스트 0)");

      for (const e of pageErrors) failures.push(`pageerror: ${e}`);
      for (const e of serverErrors) failures.push(`백엔드 5xx: ${e}`);

      const shot = testInfo.outputPath(`screen_${r.url.replace(/[^a-zA-Z0-9]+/g, "_") || "root"}.png`);
      await ui.screenshot({ path: shot, fullPage: false, timeout: 30_000 }).catch(() => {});
      await testInfo.attach("screenshot", { path: shot, contentType: "image/png" }).catch(() => {});

      appendRow({ url: r.url, ok: failures.length === 0, failures, blockedWrites, finalUrl });
      if (blockedWrites > 0) {
        console.log(`[all_screens] ${r.url}: 화면이 스스로 보낸 쓰기 요청 ${blockedWrites}건 차단함`);
      }

      expect(failures, `${r.url} 실패 항목`).toEqual([]);
    });
  }

  test("요약 — 전체 실패 목록", async () => {
    const rows: Row[] = fs.existsSync(REPORT)
      ? fs.readFileSync(REPORT, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l))
      : [];
    const bad = rows.filter((r) => !r.ok);
    const lines = [
      `[all_screens] 점검 ${rows.length}/${ROUTES.length}개 경로, 실패 ${bad.length}개`,
      ...bad.map((r) => `  - ${r.url}\n      ${r.failures.join("\n      ")}`),
    ];
    console.log(lines.join("\n"));
    const seen = new Set(rows.map((r) => r.url));
    const missing = ROUTES.filter((r) => !seen.has(r.url)).map((r) => r.url);
    expect({ failed: bad.map((r) => r.url), notRun: missing }).toEqual({ failed: [], notRun: [] });
  });
});
