"""딥스캔: 버튼 미감지 페이지 + 500 페이지 재점검 (더 긴 대기 + 넓은 셀렉터)"""

import asyncio
import contextlib
import json
import pathlib
import re
import time

from playwright.async_api import Page, async_playwright

BASE = "http://127.0.0.1:3000"
SS_DIR = pathlib.Path("C:/work/01. haehan-ai-orchestrator/data/e2e_report/deep")
SS_DIR.mkdir(parents=True, exist_ok=True)

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


def should_skip(label):
    l = label.lower()  # noqa: E741
    return any(p.lower() in l for p in SKIP_PATTERNS)


def safe(s):
    return re.sub(r"[^\w가-힣]", "_", s)[:35]


async def get_label(el):
    for attr in ["inner_text", "aria-label", "title", "placeholder", "value"]:
        try:
            if attr == "inner_text":
                t = (await el.inner_text()).strip()
            else:
                t = (await el.get_attribute(attr) or "").strip()
            if t:
                return t[:60]
        except Exception:  # noqa: BLE001 - 관리자 웹 심층 버튼 클릭 탐색 - SKIP_PATTERNS(삭제/결제 등)로 위험 버튼 클릭을 배제, except 는 클릭/스크린샷 실패를 기록할 뿐
            pass
    return "?"


async def scan_page(pg: Page, path: str, name: str):
    print(f"\n[{name}] {path}")
    try:
        r = await pg.goto(f"{BASE}{path}", wait_until="networkidle", timeout=30000)
        status = r.status if r else 0
    except Exception as e:  # noqa: BLE001 - 관리자 웹 심층 버튼 클릭 탐색 - SKIP_PATTERNS(삭제/결제 등)로 위험 버튼 클릭을 배제, except 는 클릭/스크린샷 실패를 기록할 뿐
        print(f"  ❌ 로드실패: {e}")
        return {"path": path, "name": name, "status": 0, "buttons": [], "errors": [str(e)]}

    # 충분한 대기 (CSR 렌더 완료)
    await pg.wait_for_timeout(3000)

    ss_path = str(SS_DIR / f"{safe(name)}_page.png")
    # 스크린샷 실패는 무시(위험 버튼 클릭은 SKIP_PATTERNS 로 이미 배제됨)
    with contextlib.suppress(Exception):
        await pg.screenshot(path=ss_path, full_page=False, timeout=30000)

    print(f"  HTTP {status}")

    # 넓은 셀렉터: button, [role=button], a.btn류, 탭
    sel = "button:visible, [role=button]:visible, [role=tab]:visible"
    els = pg.locator(sel)
    count = await els.count()
    print(f"  감지 요소: {count}개")

    btns = []
    for i in range(min(count, 25)):
        try:
            el = els.nth(i)
            if not await el.is_visible():
                continue
            label = await get_label(el)
            if not label or label == "?":
                continue

            is_enabled = await el.is_enabled()
            tag = await el.evaluate("e => e.tagName")
            role = await el.get_attribute("role") or tag

            if should_skip(label):
                btns.append({"label": label, "role": role, "status": "skip", "detail": ""})
                print(f"    ⏭ [{i}] {label[:40]!r} (skip)")
                continue
            if not is_enabled:
                btns.append({"label": label, "role": role, "status": "disabled", "detail": ""})
                print(f"    🔒 [{i}] {label[:40]!r} (disabled)")
                continue

            before = pg.url
            try:
                await el.click(timeout=4000)
                await pg.wait_for_timeout(700)
            except Exception as ce:  # noqa: BLE001 - 관리자 웹 심층 버튼 클릭 탐색 - SKIP_PATTERNS(삭제/결제 등)로 위험 버튼 클릭을 배제, except 는 클릭/스크린샷 실패를 기록할 뿐
                btns.append({"label": label, "role": role, "status": "error", "detail": str(ce)[:100]})
                print(f"    ❌ [{i}] {label[:40]!r} → {str(ce)[:60]}")
                await pg.goto(f"{BASE}{path}", wait_until="networkidle", timeout=20000)
                await pg.wait_for_timeout(1500)
                continue

            after = pg.url
            modal = await pg.query_selector("[role=dialog],[class*=modal],[class*=Modal]")
            toast = await pg.query_selector("[class*=toast],[class*=Toast],[class*=alert],[class*=Alert]")

            if after != before:
                st = "nav"
                detail = after
                await pg.goto(f"{BASE}{path}", wait_until="networkidle", timeout=20000)
                await pg.wait_for_timeout(1500)
            elif modal:
                st = "modal"
                detail = "모달 표시"
                try:
                    close = pg.locator(
                        "[role=dialog] button,[class*=modal] button,[aria-label=close],[aria-label=Close]"
                    ).first
                    if await close.count():
                        await close.click(timeout=2000)
                except Exception:  # noqa: BLE001 - 관리자 웹 심층 버튼 클릭 탐색 - SKIP_PATTERNS(삭제/결제 등)로 위험 버튼 클릭을 배제, except 는 클릭/스크린샷 실패를 기록할 뿐
                    pass
            elif toast:
                st = "toast"
                detail = "토스트/알림"
            else:
                st = "ok"
                detail = ""

            # 버튼 클릭 후 스크린샷
            ss_b = str(SS_DIR / f"{safe(name)}_btn{i}_{safe(label)}.png")
            try:
                await pg.screenshot(path=ss_b, full_page=False, timeout=20000)
            except Exception:  # noqa: BLE001 - 관리자 웹 심층 버튼 클릭 탐색 - SKIP_PATTERNS(삭제/결제 등)로 위험 버튼 클릭을 배제, except 는 클릭/스크린샷 실패를 기록할 뿐
                ss_b = ""

            btns.append({"label": label, "role": role, "status": st, "detail": detail, "screenshot": ss_b})
            icon = {"ok": "✅", "nav": "🔀", "modal": "📋", "toast": "💬"}.get(st, "?")
            print(f"    {icon} [{i}] {label[:40]!r} → {st} {detail[:50]}")

        except Exception as ex:  # noqa: BLE001 - 관리자 웹 심층 버튼 클릭 탐색 - SKIP_PATTERNS(삭제/결제 등)로 위험 버튼 클릭을 배제, except 는 클릭/스크린샷 실패를 기록할 뿐
            print(f"    ⚠️ [{i}] 처리오류: {ex}")

    return {"path": path, "name": name, "status": status, "buttons": btns, "errors": []}


DEEP_PAGES = [
    ("/", "홈 대시보드"),
    ("/login", "로그인"),
    ("/signup", "회원가입"),
    ("/ops", "운영센터"),
    ("/local-agents", "로컬 에이전트"),
    ("/naver/smartstore/orders", "주문 관리"),
    ("/naver/smartstore/settlements", "정산 관리"),
    ("/naver/smartstore/marketing", "마케팅/혜택"),
    ("/naver/blog", "블로그 관리"),
    ("/naver/keywords", "키워드 분석"),
    ("/cad", "CAD 자동화"),
    ("/market-research", "시장 조사"),
    ("/external-tasks", "외부 업무"),
    ("/file-map", "파일 정리"),
    ("/settings/sites", "사이트 설정"),
    ("/admin/users", "Admin 사용자"),
    ("/about", "소개"),
]


async def main():
    t0 = time.time()
    all_results = []

    async with async_playwright() as pw:
        br = await pw.chromium.launch(headless=True)
        ctx = await br.new_context(viewport={"width": 1280, "height": 900})
        pg = await ctx.new_page()

        for path, name in DEEP_PAGES:
            r = await scan_page(pg, path, name)
            all_results.append(r)

        await br.close()

    out = pathlib.Path("C:/work/01. haehan-ai-orchestrator/data/e2e_report/deep_report.json")
    out.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = time.time() - t0
    total_b = sum(len(r["buttons"]) for r in all_results)
    ok = sum(1 for r in all_results for b in r["buttons"] if b["status"] in ("ok", "modal", "toast"))
    nav = sum(1 for r in all_results for b in r["buttons"] if b["status"] == "nav")
    skip = sum(1 for r in all_results for b in r["buttons"] if b["status"] == "skip")
    err = sum(1 for r in all_results for b in r["buttons"] if b["status"] == "error")
    dis = sum(1 for r in all_results for b in r["buttons"] if b["status"] == "disabled")

    print(f"\n{'=' * 60}")
    print(f"딥스캔 완료 ({elapsed:.0f}초)  페이지 {len(all_results)}개 / 버튼 {total_b}개")
    print(f"  ✅ {ok}  🔀 {nav}  ⏭ {skip}  🔒 {dis}  ❌ {err}")
    print(f"  결과: {out}")


asyncio.run(main())
