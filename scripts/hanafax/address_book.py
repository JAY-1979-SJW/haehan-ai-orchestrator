"""하나팩스 주소록 그룹 읽기 — 그룹 목록과 그룹의 연락처(이름·팩스번호)를 **읽기 전용**으로 가져온다.

기준서: docs/specs/2026-10-02_hanafax_auto_send.md §14·§16
- 주소록 메뉴를 눌러 들어가 그룹 링크(`address_pList.asp?intid=…`)를 연다. 추가·변경·삭제·보내기 버튼은 누르지 않는다.
- 연락처 목록은 10명씩 `goPage(n)` 으로 넘긴다(1천 명대 그룹은 100쪽 넘게 — 몇 분 걸린다). 엔진과 같은 락을 쓴다.
- 연락처에는 개인정보(번호·이름)가 있으므로 이 모듈은 저장하지 않는다 — 호출자가 로컬 캐시에만 둔다(커밋 금지).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

log = logging.getLogger("hanafax.address_book")

_BASE_URL = "https://www.hanafax.com"
MAX_PAGES = 400  # 안전 상한(4000명)
_FAX = re.compile(r"^\d{2,4}-?\d{3,4}-?\d{4}$")

_JS_GROUPS = r"""() => Array.from(document.querySelectorAll('a[href*="address_pList.asp?intid="]')).map(a => {
    const tr = a.closest('tr');
    const cells = tr ? Array.from(tr.querySelectorAll(':scope > td')).map(c => c.innerText.replace(/\s+/g, ' ').trim()) : [];
    const m = /intid=(\d+)/.exec(a.getAttribute('href') || '');
    return {name: a.innerText.trim(), intid: m ? m[1] : '', cells: cells};
})"""
_JS_ROWS = r"""() => Array.from(document.querySelectorAll('tr'))
    .map(tr => Array.from(tr.querySelectorAll(':scope > td,:scope > th')).map(c => c.innerText.replace(/\s+/g, ' ').trim()))
    .filter(r => r.length >= 4)"""
_JS_PAGES = r"""() => Math.max(1, ...Array.from(document.querySelectorAll('[onclick*="goPage"],[href*="goPage"]')).map(e => {
    const m = /goPage\((\d+)\)/.exec(e.getAttribute('onclick') || e.getAttribute('href') || '');
    return m ? parseInt(m[1], 10) : 1;
}))"""  # 쪽 이동은 <button onclick="goPage(n)"> 이고, '끝' 버튼이 마지막 쪽 번호를 가진다


def parse_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """그룹 링크 + 같은 행의 셀 → [{name, intid, members, fax_count}]. 같은 intid 는 한 번만."""
    seen: set[str] = set()
    groups: list[dict[str, Any]] = []
    for item in items:
        intid = str(item.get("intid") or "")
        if not intid or intid in seen:
            continue
        seen.add(intid)
        cells = [str(c) for c in item.get("cells", [])]
        members = next((int(m.group(1)) for c in cells if (m := re.match(r"^(\d+)명$", c))), 0)
        fax_count = next((int(m.group(1)) for c in cells if (m := re.match(r"^(\d+)개$", c))), 0)
        groups.append(
            {"name": str(item.get("name") or "").strip(), "intid": intid, "members": members, "fax_count": fax_count}
        )
    return groups


def parse_members(rows: list[list[str]]) -> list[dict[str, str]]:
    """그룹 연락처 표의 행 → [{fax, name}]. 머리글 행(이름·팩스번호…)으로 열을 찾고, 팩스번호가 있는 행만 읽는다."""
    header_idx = next((i for i, r in enumerate(rows) if "팩스번호" in r and ("이름" in r or "회사" in r)), None)
    if header_idx is None:
        return []
    header = rows[header_idx]
    fax_col = header.index("팩스번호")
    name_col = header.index("이름") if "이름" in header else None
    company_col = header.index("회사") if "회사" in header else None
    members: list[dict[str, str]] = []
    for row in rows[header_idx + 1 :]:
        if len(row) <= fax_col or not _FAX.match(row[fax_col].strip()):
            continue
        name = (row[name_col] if name_col is not None and name_col < len(row) else "").strip()
        company = (row[company_col] if company_col is not None and company_col < len(row) else "").strip()
        members.append({"fax": row[fax_col].strip(), "name": name or company})
    return members


def _login_and_open_book(page: Any, uid: str, pwd: str) -> None:
    page.goto(_BASE_URL, wait_until="domcontentloaded", timeout=20_000)
    page.fill('input[name="struid"]', uid)
    page.fill('input[name="strpwd"]', pwd)
    page.evaluate("document.querySelector('form').submit()")
    page.wait_for_load_state("domcontentloaded", timeout=15_000)
    page.wait_for_timeout(1_500)
    with page.expect_navigation(timeout=15_000):
        page.click('a:has-text("주소록")')  # 직접 URL 이동은 홈으로 돌아가므로 메뉴를 눌러 들어간다
    page.wait_for_timeout(2_000)


def _session(work: Callable[[Any], Any]) -> Any:
    from playwright.sync_api import sync_playwright

    from scripts.hanafax import sender as engine
    from scripts.hanafax.auth import get_credentials

    uid, pwd = get_credentials()
    if not uid or not pwd:
        raise RuntimeError("하나팩스 자격증명이 없습니다")
    with engine._LOCK, sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        try:
            page = browser.new_context(locale="ko-KR", viewport={"width": 1280, "height": 1000}).new_page()
            page.on("dialog", lambda d: d.dismiss())
            _login_and_open_book(page, uid, pwd)
            return work(page)
        finally:
            browser.close()


def list_groups() -> list[dict[str, Any]]:
    """주소록 그룹 목록(이름·인원·팩스번호 수)."""
    return _session(lambda page: parse_groups(page.evaluate(_JS_GROUPS)))


def fetch_group(intid: str, progress: Callable[[int, int], None] | None = None) -> list[dict[str, str]]:
    """그룹 하나의 연락처 전체를 읽는다(쪽마다 `goPage(n)`). progress(현재 쪽, 전체 쪽)."""
    if not re.fullmatch(r"\d{1,12}", str(intid)):
        raise ValueError("그룹 번호가 올바르지 않습니다")

    def work(page: Any) -> list[dict[str, str]]:
        with page.expect_navigation(timeout=15_000):
            page.click(f'a[href*="intid={intid}"]')
        page.wait_for_timeout(2_000)
        pages = min(int(page.evaluate(_JS_PAGES)), MAX_PAGES)
        members = parse_members(page.evaluate(_JS_ROWS))
        if progress:
            progress(1, pages)
        for n in range(2, pages + 1):
            try:
                with page.expect_navigation(timeout=15_000):
                    page.evaluate(f"goPage({n})")
            except Exception:  # noqa: BLE001 - 이동 감지에 실패해도 잠시 기다린 뒤 읽는다
                page.wait_for_timeout(1_500)
            page.wait_for_timeout(300)
            members += parse_members(page.evaluate(_JS_ROWS))
            if progress:
                progress(n, pages)
        return members

    return _session(work)
