"""
전체 앱 E2E 점검 스크립트
모든 페이지 x 버튼/탭/링크 클릭 → 결과 + 스크린샷 + 보고서 생성
"""

import asyncio
import json
import pathlib
import re
import time
from dataclasses import dataclass, field

from playwright.async_api import Locator, Page, async_playwright

BASE = "http://127.0.0.1:3000"
SS_DIR = pathlib.Path("C:/work/01. haehan-ai-orchestrator/data/e2e_report")
SS_DIR.mkdir(parents=True, exist_ok=True)
REPORT = SS_DIR / "report.json"

# ── 데이터 구조 ──────────────────────────────────────────────────────────────


@dataclass
class BtnResult:
    label: str
    selector: str
    action: str  # click / tab / link
    before_url: str
    after_url: str
    status: str  # ok / error / nav / noop / skip
    error: str = ""
    screenshot: str = ""


@dataclass
class PageResult:
    path: str
    title: str
    status: int
    screenshot: str
    buttons: list = field(default_factory=list)
    errors: list = field(default_factory=list)


results: list[PageResult] = []

# ── 유틸 ────────────────────────────────────────────────────────────────────


async def goto(pg: Page, path: str) -> int:
    try:
        r = await pg.goto(f"{BASE}{path}", wait_until="networkidle", timeout=25000)
        await pg.wait_for_timeout(800)
        return r.status if r else 0
    except Exception:  # noqa: BLE001 - 관리자 웹 E2E 버튼/탭 클릭 탐색 리포트 - SKIP_PATTERNS(삭제/결제/발행/로그아웃 등)로 위험 버튼은 클릭 자체를 건너뛰고, except 는 클릭 실패를 errors 리스트에 기록할 뿐
        return 0


async def shot(pg: Page, name: str) -> str:
    p = str(SS_DIR / f"{name}.png")
    try:
        await pg.screenshot(path=p, full_page=False, timeout=30000)
    except Exception:  # noqa: BLE001 - 관리자 웹 E2E 버튼/탭 클릭 탐색 리포트 - SKIP_PATTERNS(삭제/결제/발행/로그아웃 등)로 위험 버튼은 클릭 자체를 건너뛰고, except 는 클릭 실패를 errors 리스트에 기록할 뿐
        pass
    return p


def safe_name(s: str) -> str:
    return re.sub(r"[^\w가-힣]", "_", s)[:40]


async def get_btn_label(el: Locator) -> str:
    try:
        t = (await el.inner_text()).strip()
        if t:
            return t[:50]
    except Exception:  # noqa: BLE001 - 관리자 웹 E2E 버튼/탭 클릭 탐색 리포트 - SKIP_PATTERNS(삭제/결제/발행/로그아웃 등)로 위험 버튼은 클릭 자체를 건너뛰고, except 는 클릭 실패를 errors 리스트에 기록할 뿐
        pass
    try:
        return (await el.get_attribute("aria-label") or "")[:50]
    except Exception:  # noqa: BLE001 - 관리자 웹 E2E 버튼/탭 클릭 탐색 리포트 - SKIP_PATTERNS(삭제/결제/발행/로그아웃 등)로 위험 버튼은 클릭 자체를 건너뛰고, except 는 클릭 실패를 errors 리스트에 기록할 뿐
        pass
    try:
        return (await el.get_attribute("title") or "")[:50]
    except Exception:  # noqa: BLE001 - 관리자 웹 E2E 버튼/탭 클릭 탐색 리포트 - SKIP_PATTERNS(삭제/결제/발행/로그아웃 등)로 위험 버튼은 클릭 자체를 건너뛰고, except 는 클릭 실패를 errors 리스트에 기록할 뿐
        pass
    return "?"


# 클릭하면 안 되는 버튼 패턴
SKIP_PATTERNS = [
    "삭제",
    "제거",
    "초기화",
    "비밀번호",
    "결제",
    "송금",
    "전송",
    "발행",
    "업로드",
    "저장",
    "등록",
    "신청",
    "탈퇴",
    "로그아웃",
    "인증 URL",
    "OAuth",
    "재인증",
    "승인",
    "기절",
    "거절",
    "발급",
    "회전",
    "rotate",
    "revoke",
    "delete",
    "remove",
]


def should_skip(label: str) -> bool:
    l = label.lower()  # noqa: E741
    return any(p.lower() in l for p in SKIP_PATTERNS)


# ── 페이지별 버튼 테스트 ─────────────────────────────────────────────────────


async def test_page(pg: Page, path: str, page_name: str) -> PageResult:
    print(f"\n{'─' * 50}")
    print(f"  {page_name}  ({path})")

    status = await goto(pg, path)
    title = await pg.title()
    ss_name = f"page_{safe_name(page_name)}"
    ss = await shot(pg, ss_name)
    pr = PageResult(path=path, title=title, status=status, screenshot=ss)

    if status == 0:
        pr.errors.append("페이지 로드 실패")
        print("  ❌ 로드 실패")
        return pr

    print(f"  ✅ {title} (HTTP {status})")

    # ── 탭 클릭 ──────────────────────────────────────────────────────────────
    tabs = pg.locator("[role=tab], [class*=tab]:not([class*=table]):not([class*=stable])")
    tab_count = await tabs.count()
    print(f"  탭 {tab_count}개")
    for i in range(min(tab_count, 8)):
        try:
            el = tabs.nth(i)
            if not await el.is_visible():
                continue
            label = await get_btn_label(el)
            before_url = pg.url
            await el.click(timeout=3000)
            await pg.wait_for_timeout(600)
            after_url = pg.url
            ss_t = await shot(pg, f"tab_{safe_name(page_name)}_{i}_{safe_name(label)}")
            pr.buttons.append(
                BtnResult(
                    label=label,
                    selector=f"tab[{i}]",
                    action="tab",
                    before_url=before_url,
                    after_url=after_url,
                    status="nav" if after_url != before_url else "ok",
                    screenshot=ss_t,
                ).__dict__
            )
            print(f"    탭 [{i}] {label!r} → {'nav' if after_url != before_url else 'ok'}")
        except Exception as e:  # noqa: BLE001 - 관리자 웹 E2E 버튼/탭 클릭 탐색 리포트 - SKIP_PATTERNS(삭제/결제/발행/로그아웃 등)로 위험 버튼은 클릭 자체를 건너뛰고, except 는 클릭 실패를 errors 리스트에 기록할 뿐
            pr.errors.append(f"탭[{i}] 클릭 오류: {e}")

    # 원래 페이지로 복귀
    await goto(pg, path)

    # ── 버튼 클릭 ────────────────────────────────────────────────────────────
    btns = pg.locator("button:visible")
    btn_count = await btns.count()
    print(f"  버튼 {btn_count}개")
    for i in range(min(btn_count, 20)):
        try:
            el = btns.nth(i)
            if not await el.is_visible():
                continue
            if not await el.is_enabled():
                continue
            label = await get_btn_label(el)
            if should_skip(label):
                pr.buttons.append(
                    BtnResult(
                        label=label,
                        selector=f"btn[{i}]",
                        action="click",
                        before_url=pg.url,
                        after_url=pg.url,
                        status="skip",
                        screenshot="",
                    ).__dict__
                )
                print(f"    버튼 [{i}] {label!r} → SKIP")
                continue

            before_url = pg.url
            try:
                await el.click(timeout=4000)
                await pg.wait_for_timeout(800)
            except Exception as ce:  # noqa: BLE001 - 관리자 웹 E2E 버튼/탭 클릭 탐색 리포트 - SKIP_PATTERNS(삭제/결제/발행/로그아웃 등)로 위험 버튼은 클릭 자체를 건너뛰고, except 는 클릭 실패를 errors 리스트에 기록할 뿐
                pr.buttons.append(
                    BtnResult(
                        label=label,
                        selector=f"btn[{i}]",
                        action="click",
                        before_url=before_url,
                        after_url=pg.url,
                        status="error",
                        error=str(ce)[:120],
                    ).__dict__
                )
                print(f"    버튼 [{i}] {label!r} → error: {str(ce)[:60]}")
                await goto(pg, path)
                continue

            after_url = pg.url
            ss_b = await shot(pg, f"btn_{safe_name(page_name)}_{i}_{safe_name(label)}")

            if after_url != before_url:
                status_b = "nav"
                await goto(pg, path)  # 원복
            else:
                # 모달/토스트 확인
                modal = await pg.query_selector("[role=dialog],[class*=modal],[class*=Modal]")
                toast = await pg.query_selector("[class*=toast],[class*=Toast],[class*=alert]")
                if modal:
                    status_b = "modal"
                    # 모달 닫기
                    try:
                        close = pg.locator("[role=dialog] button, [class*=modal] button").first
                        if await close.count():
                            await close.click(timeout=2000)
                    except Exception:  # noqa: BLE001 - 관리자 웹 E2E 버튼/탭 클릭 탐색 리포트 - SKIP_PATTERNS(삭제/결제/발행/로그아웃 등)로 위험 버튼은 클릭 자체를 건너뛰고, except 는 클릭 실패를 errors 리스트에 기록할 뿐
                        pass
                elif toast:
                    status_b = "toast"
                else:
                    status_b = "ok"

            pr.buttons.append(
                BtnResult(
                    label=label,
                    selector=f"btn[{i}]",
                    action="click",
                    before_url=before_url,
                    after_url=after_url,
                    status=status_b,
                    screenshot=ss_b,
                ).__dict__
            )
            print(f"    버튼 [{i}] {label!r} → {status_b}")
        except Exception as e:  # noqa: BLE001 - 관리자 웹 E2E 버튼/탭 클릭 탐색 리포트 - SKIP_PATTERNS(삭제/결제/발행/로그아웃 등)로 위험 버튼은 클릭 자체를 건너뛰고, except 는 클릭 실패를 errors 리스트에 기록할 뿐
            pr.errors.append(f"버튼[{i}] 처리 오류: {str(e)[:100]}")
            await goto(pg, path)

    return pr


# ── 페이지 목록 ──────────────────────────────────────────────────────────────

PAGES = [
    ("/", "홈 대시보드"),
    ("/login", "로그인"),
    ("/signup", "회원가입"),
    ("/ops", "운영센터"),
    ("/local-agents", "로컬 에이전트"),
    ("/naver/smartstore", "스마트스토어 AI 채팅"),
    ("/naver/smartstore/products", "상품 관리"),
    ("/naver/smartstore/orders", "주문 관리"),
    ("/naver/smartstore/settlements", "정산 관리"),
    ("/naver/smartstore/reviews", "리뷰/문의"),
    ("/naver/smartstore/stats", "데이터 분석"),
    ("/naver/smartstore/marketing", "마케팅/혜택"),
    ("/naver/blog", "블로그 관리"),
    ("/naver/keywords", "키워드 분석"),
    ("/cad", "CAD 자동화"),
    ("/youtube", "YouTube 관리"),
    ("/gabia", "가비아 자동화"),
    ("/google", "구글 허브"),
    ("/market-research", "시장 조사"),
    ("/hanafax", "하나팩스"),
    ("/dataportal", "공공데이터포털"),
    ("/external-tasks", "외부 업무"),
    ("/file-map", "파일 정리"),
    ("/settings/sites", "사이트 설정"),
    ("/admin/users", "Admin 사용자"),
    ("/about", "소개"),
]

# ── 메인 ─────────────────────────────────────────────────────────────────────


async def main():
    t0 = time.time()
    async with async_playwright() as pw:
        br = await pw.chromium.launch(headless=True)
        ctx = await br.new_context(viewport={"width": 1280, "height": 900})
        pg = await ctx.new_page()

        for path, name in PAGES:
            pr = await test_page(pg, path, name)
            results.append(pr.__dict__)
            # 중간 저장
            REPORT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

        await br.close()

    elapsed = time.time() - t0
    REPORT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 요약 출력 ────────────────────────────────────────────────────────────
    total_btns = sum(len(r["buttons"]) for r in results)
    ok_btns = sum(1 for r in results for b in r["buttons"] if b["status"] in ("ok", "nav", "tab", "modal", "toast"))
    skip_btns = sum(1 for r in results for b in r["buttons"] if b["status"] == "skip")
    err_btns = sum(1 for r in results for b in r["buttons"] if b["status"] == "error")
    nav_btns = sum(1 for r in results for b in r["buttons"] if b["status"] == "nav")

    print(f"\n{'=' * 60}")
    print(f"E2E 점검 완료  ({elapsed:.0f}초)")
    print(f"  페이지 {len(results)}개 / 버튼·탭 {total_btns}개")
    print(f"  ✅ 동작 {ok_btns}  🔀 네비게이션 {nav_btns}  ⏭ 스킵 {skip_btns}  ❌ 오류 {err_btns}")
    print(f"  보고서: {REPORT}")
    print(f"  스크린샷: {SS_DIR}")


asyncio.run(main())
