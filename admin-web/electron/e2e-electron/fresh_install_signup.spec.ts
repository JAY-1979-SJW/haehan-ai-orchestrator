import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { launchApp, getUiPage } from "./launch_helper";

// 새 PC 첫 설치 시나리오(데스크톱, B안 — 대표님 결정 2026-10-07):
// 데스크톱은 비밀번호 로그인 화면이 없다. 첫 실행 때 /setup에서 이름·이메일만
// 입력하면 바로 메인 화면으로 가고(로그인 화면 없음), 그 뒤로는 재실행해도 다시
// 묻지 않고 자동 로그인된다. W4(stage/desktop-session)가 구현 중이라 이 브랜치
// (PR 2 기준)에는 아직 /setup·자동 로그인 로직이 없다 — 병합 전까지 전체 시나리오를
// SKIP_PENDING_FEATURES로 "대기" 표시해 둔다. 병합되면 이 상수를 false로 바꾼다.
//
// 선택자는 W4 확인(2026-10-07, stage/desktop-runtime-fixes 847251f8) 기준 실제 값:
// 이름 input#setup-name(name="name", data-testid="setup-name"), 이메일
// input#setup-email(name="email", type=email, data-testid="setup-email"), 제출
// button#setup-submit(type=submit, data-testid="setup-submit", 텍스트 "시작하기"),
// 오류 [data-testid="setup-error"](role=alert). 비밀번호 입력란 없음.
// 흐름: 등록된 사용자 0명 → 폼 표시. 제출 후 router.replace(returnTo, 없으면 "/").
// 이미 등록돼 있으면 폼 없이 자동 세션(로딩 중 "시작하는 중...") 후 이동.
// 서버(웹) 모드에서는 "시작할 수 없습니다" 안내만 나온다(데스크톱 전용 화면).
//
// 가입 승인·거절(대기 승인/거절 API)은 서버 모드(다중 사용자) 전용 개념이라
// 데스크톱 E2E에는 없다 — 그 경로는 tests/test_user_approval_gate.py·
// tests/test_user_auth_audit.py(서버 모드 pytest)가 이미 검증한다.
const SKIP_PENDING_FEATURES = false;
const SKIP_REASON =
  "W4 desktop-session/setup(B안: 이름·이메일만, 비밀번호 없음) 미병합 — " +
  "병합 후 SKIP_PENDING_FEATURES=false로 전환";

async function fillSetupForm(ui: Page, name: string, email: string) {
  await ui.locator("#setup-name").fill(name);
  await ui.locator("#setup-email").fill(email);
  await ui.locator("#setup-submit").click();
}

test.describe("새 PC 첫 설치 — 데스크톱 자동 로그인(B안)", () => {
  test.setTimeout(180_000);
  let tmpUserData: string;

  test.beforeEach(() => {
    // 완전히 빈 userData로 시작(실제 사용자 DB·서버는 안 건드림)
    tmpUserData = fs.mkdtempSync(path.join(os.tmpdir(), "haehan-e2e-userdata-"));
  });

  test.afterEach(() => {
    fs.rmSync(tmpUserData, { recursive: true, force: true });
  });

  test(
    "1. 첫 실행 → /setup에서 이름·이메일만 입력 → 바로 메인 화면(로그인 화면 없음) [대기]",
    async () => {
      test.skip(SKIP_PENDING_FEATURES, SKIP_REASON);
      const app = await launchApp({}, [`--user-data-dir=${tmpUserData}`]);
      try {
        const ui = await getUiPage(app);
        await ui.waitForLoadState("domcontentloaded", { timeout: 20_000 }).catch(() => {});

        // 첫 실행이면 /setup으로 가야 한다(로그인 화면을 거치지 않음)
        await expect(ui).toHaveURL(/\/setup/, { timeout: 20_000 });
        expect(ui.url()).not.toContain("/login");

        await fillSetupForm(ui, "First User", "first-user@e2e.test");

        // 설정 완료 즉시 메인 화면으로(로그인 화면을 전혀 거치지 않음)
        await expect(ui).toHaveURL(/^(?!.*\/(setup|login)).*$/, { timeout: 20_000 });
      } finally {
        await app.close();
      }
    }
  );

  test(
    "2. 앱 종료 후 재실행하면 다시 묻지 않고 자동 로그인되고 데이터가 유지된다(D1) [대기]",
    async () => {
      test.skip(SKIP_PENDING_FEATURES, SKIP_REASON);
      // 1회차: 최초 설정
      const app1 = await launchApp({}, [`--user-data-dir=${tmpUserData}`]);
      try {
        const ui1 = await getUiPage(app1);
        await ui1.waitForLoadState("domcontentloaded", { timeout: 20_000 }).catch(() => {});
        await expect(ui1).toHaveURL(/\/setup/, { timeout: 20_000 });
        await fillSetupForm(ui1, "Persisted User", "persisted-user@e2e.test");
        await expect(ui1).toHaveURL(/^(?!.*\/(setup|login)).*$/, { timeout: 20_000 });
      } finally {
        await app1.close();
      }

      // 2회차: 같은 userData로 재실행 — /setup·/login 둘 다 다시 안 거쳐야 한다
      // (로딩 중에는 "시작하는 중..." 문구가 잠깐 보일 수 있다)
      const app2 = await launchApp({}, [`--user-data-dir=${tmpUserData}`]);
      try {
        const ui2 = await getUiPage(app2);
        await ui2.waitForLoadState("domcontentloaded", { timeout: 20_000 }).catch(() => {});
        await ui2.waitForTimeout(5_000);
        expect(ui2.url()).not.toContain("/setup");
        expect(ui2.url()).not.toContain("/login");

        // 데이터 유지(D1): 1회차에 등록한 이름이 재실행 후에도 그대로 보여야 한다
        await ui2.goto("http://localhost:3000/about", { timeout: 20_000 }).catch(() => {});
        await expect(ui2.getByText(/Persisted User/)).toBeVisible({ timeout: 15_000 });
      } finally {
        await app2.close();
      }
    }
  );

  test(
    "3. 마이페이지 '앱 정보'에 빌드 버전(build-info.json 기반)이 표시된다 [대기]",
    async () => {
      test.skip(SKIP_PENDING_FEATURES, SKIP_REASON);
      const app = await launchApp({}, [`--user-data-dir=${tmpUserData}`]);
      try {
        const ui = await getUiPage(app);
        await ui.waitForLoadState("domcontentloaded", { timeout: 20_000 }).catch(() => {});
        await expect(ui).toHaveURL(/\/setup/, { timeout: 20_000 });
        await fillSetupForm(ui, "Version Check User", "version-check@e2e.test");
        await expect(ui).toHaveURL(/^(?!.*\/(setup|login)).*$/, { timeout: 20_000 });

        await ui.goto("http://localhost:3000/about", { timeout: 20_000 }).catch(() => {});
        // CI가 write-build-info.json 단계에서 넣는 <yyyymmdd>-<sha7> 형식 버전 문자열
        await expect(ui.getByText(/\d{8}-[0-9a-f]{7}/)).toBeVisible({ timeout: 15_000 });
      } finally {
        await app.close();
      }
    }
  );
});

// 가입 승인/거절 API(list_pending·approve·reject)는 서버 모드(다중 사용자) 전용
// 개념이고, 그 경로는 서버 모드 pytest가 이미 가지고 있다 — 데스크톱 E2E에서는
// 다루지 않는다: tests/test_user_approval_gate.py(승인 대기/승인), 거절까지
// 포함한 범위는 user_auth_router.py의 /{user_id}/reject 핸들러에 대응하는
// 서버 모드 시험(동일 파일 또는 PR 2/integrate-2에서 추가된 전용 테스트)을 본다.
