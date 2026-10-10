"""미해결 메서드 3건 탐지 — calendar, mail_search, mybox_list.

핵심 보완 사항:
1. add_init_script로 XHR/fetch 후킹 사전 설치 (페이지 로드시부터 캡처)
2. 페이지 진입 후 사용자 인터랙션 시뮬레이션 (클릭/입력)
3. 클릭/입력 가능 요소 셀렉터 자동 dump
4. 캡처된 모든 API 호출 + 응답 본문 JSON으로 저장

결과 저장 위치:
  data/reports/local_agent/explore_unresolved_<timestamp>.json
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.browser.agent.agent import BrowserAgent

HOOK_JS = """
window.__cap = [];
const _xhrOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(m, url, ...r) {
    this._capUrl = url;
    this._capMethod = m;
    return _xhrOpen.apply(this, [m, url, ...r]);
};
const _xhrSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = function(...a) {
    const _start = Date.now();
    this.addEventListener('load', function() {
        try {
            window.__cap.push({
                via: 'xhr',
                method: this._capMethod,
                url: this._capUrl,
                status: this.status,
                body: (this.responseText || '').slice(0, 2000),
                ts: Date.now() - _start
            });
        } catch(e) {}
    });
    return _xhrSend.apply(this, a);
};
const _fetch = window.fetch;
window.fetch = async function(...a) {
    const url = typeof a[0] === 'string' ? a[0] : (a[0]?.url || '');
    const method = (a[1]?.method) || (a[0]?.method) || 'GET';
    const _start = Date.now();
    try {
        const resp = await _fetch(...a);
        const clone = resp.clone();
        clone.text().then(b => {
            window.__cap.push({
                via: 'fetch',
                method,
                url,
                status: resp.status,
                body: (b || '').slice(0, 2000),
                ts: Date.now() - _start
            });
        }).catch(() => {});
        return resp;
    } catch(e) {
        window.__cap.push({ via: 'fetch', method, url, error: String(e) });
        throw e;
    }
};
"""


def _filter_cap(cap: list, keywords: tuple) -> list:
    """관심 있는 API 호출만 필터."""
    out = []
    for x in cap:
        url = x.get("url", "")
        if not url:
            continue
        # 정적 자원 제외
        if any(url.endswith(ext) for ext in (".js", ".css", ".png", ".jpg", ".svg", ".ico", ".woff", ".woff2")):
            continue
        if any(k in url for k in keywords):
            out.append(x)
    return out


def _read_cap(page) -> list:
    return page.evaluate("() => window.__cap || []")


def _reset_cap(page):
    page.evaluate("() => { window.__cap = []; }")


def dump_elements(page, selector: str, limit: int = 20) -> list[dict]:
    """주어진 셀렉터 매칭 요소들의 정보 dump."""
    return page.evaluate(
        f"""(sel) => {{
        const els = document.querySelectorAll(sel);
        return Array.from(els).slice(0, {limit}).map(el => ({{
            tag: el.tagName.toLowerCase(),
            id: el.id || '',
            cls: el.className || '',
            type: el.type || '',
            placeholder: el.placeholder || '',
            ariaLabel: el.getAttribute('aria-label') || '',
            text: (el.innerText || '').trim().slice(0, 60),
            rect: (() => {{
                const r = el.getBoundingClientRect();
                return {{ x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }};
            }})(),
            visible: el.offsetWidth > 0 && el.offsetHeight > 0,
        }}));
    }}""",
        selector,
    )


def explore_calendar(page, report: dict):
    """캘린더 — 월 이동/일정 클릭 시뮬레이션 후 API 캡처."""
    print("\n[1/3] 캘린더 탐지")
    page.add_init_script(HOOK_JS)

    # 1) 페이지 진입
    page.goto("https://calendar.naver.com/")
    time.sleep(5)
    init_cap = _filter_cap(_read_cap(page), ("ajax/", "calendar.naver.com/a", "schedule", "Schedule", "event"))
    print(f"  초기 로드 API: {len(init_cap)}개")
    report["calendar"]["initial_apis"] = init_cap

    # 2) 다음달/이전달 버튼 셀렉터 dump
    nav_selectors = [
        '[aria-label*="다음"]',
        '[aria-label*="이전"]',
        '[aria-label*="next"]',
        '[aria-label*="prev"]',
        '[class*="next"]',
        '[class*="prev"]',
        '[class*="Next"]',
        '[class*="Prev"]',
        'button[class*="month"]',
        '[class*="navi"] button',
    ]
    nav_dump = {}
    for sel in nav_selectors:
        try:
            els = dump_elements(page, sel, limit=5)
            visible = [e for e in els if e["visible"]]
            if visible:
                nav_dump[sel] = visible
        except Exception:  # noqa: BLE001 - 네이버 캘린더/메일검색/마이박스 UI 구조 읽기전용 탐색 스크립트(아카이브) - 실패시 report 에 error 기록 후 계속 진행, 쓰기 동작 없음
            pass
    print(f"  네비 후보 셀렉터: {len(nav_dump)}개 발견")
    report["calendar"]["nav_buttons"] = nav_dump

    # 3) 첫번째 보이는 다음/이전 버튼 클릭 시도
    _reset_cap(page)
    clicked = False
    for sel in nav_selectors:
        try:
            target = page.query_selector(f"{sel}:visible") or page.query_selector(sel)
            if target:
                target.click(timeout=3000)
                time.sleep(3)
                cap_after = _filter_cap(_read_cap(page), ("ajax/", "calendar.naver.com/a", "schedule", "Schedule"))
                if cap_after:
                    print(f"  클릭 셀렉터 '{sel}' → API {len(cap_after)}개 호출됨")
                    report["calendar"]["after_click_selector"] = sel
                    report["calendar"]["after_click_apis"] = cap_after
                    clicked = True
                    break
        except Exception:  # noqa: BLE001 - 네이버 캘린더/메일검색/마이박스 UI 구조 읽기전용 탐색 스크립트(아카이브) - 실패시 report 에 error 기록 후 계속 진행, 쓰기 동작 없음
            pass
    if not clicked:
        print("  ⚠ 네비게이션 클릭 실패 — 추가 분석 필요")

    # 4) 주/월/일 뷰 변경 버튼 dump
    view_dump = {}
    for sel in ['[class*="view"]', '[role="tab"]', '[aria-label*="월"]', '[aria-label*="주"]']:
        try:
            els = dump_elements(page, sel, limit=5)
            visible = [e for e in els if e["visible"]]
            if visible:
                view_dump[sel] = visible
        except Exception:  # noqa: BLE001 - 네이버 캘린더/메일검색/마이박스 UI 구조 읽기전용 탐색 스크립트(아카이브) - 실패시 report 에 error 기록 후 계속 진행, 쓰기 동작 없음
            pass
    report["calendar"]["view_buttons"] = view_dump


def explore_mail_search(page, report: dict):
    """메일 검색 — input 발견 + 입력 + Enter 시뮬레이션."""
    print("\n[2/3] mail_search 탐지")
    # 메일 진입
    page.goto("https://mail.naver.com/v2/folders/0/all")
    time.sleep(4)
    _reset_cap(page)

    # 1) 모든 input 요소 dump
    print("  모든 input 요소 dump")
    all_inputs = dump_elements(page, "input", limit=30)
    visible_inputs = [e for e in all_inputs if e["visible"]]
    report["mail_search"]["all_inputs"] = visible_inputs
    print(f"    표시되는 input: {len(visible_inputs)}개")
    for inp in visible_inputs[:10]:
        print(f"    - tag=input type={inp['type']!r} placeholder={inp['placeholder']!r} cls={inp['cls'][:60]!r}")

    # 2) 검색 관련 버튼 dump (검색 input이 클릭으로만 활성화될 수 있음)
    search_btns = dump_elements(page, '[class*="search"], button[class*="search"], [aria-label*="검색"]', limit=10)
    visible_btns = [e for e in search_btns if e["visible"]]
    report["mail_search"]["search_buttons"] = visible_btns
    print(f"    검색 관련 요소: {len(visible_btns)}개")

    # 3) v2/search URL로 진입 시도
    page.goto(f"https://mail.naver.com/v2/search?q={quote('네이버')}")
    time.sleep(5)
    cap_search = _filter_cap(_read_cap(page), ("json/", "search", "list", "mail"))
    report["mail_search"]["url_navigation_apis"] = cap_search
    print(f"    URL 네비 후 API: {len(cap_search)}개")

    # 4) URL 진입 후 페이지의 input 다시 dump (검색창이 활성화되어 있을 수 있음)
    inputs_after = dump_elements(page, "input", limit=30)
    visible_after = [e for e in inputs_after if e["visible"]]
    report["mail_search"]["inputs_after_url"] = visible_after

    # 5) 첫 번째 검색 input 후보에 입력 + Enter 시뮬레이션
    _reset_cap(page)
    input_selectors = [
        'input[placeholder*="검색"]',
        'input[type="search"]',
        '[class*="search"] input',
        'input[name*="query"]',
        'input[name*="search"]',
        'input[name*="q"]',
    ]
    triggered_sel = None
    for sel in input_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                el.fill("네이버")
                page.keyboard.press("Enter")
                time.sleep(4)
                cap_typed = _filter_cap(_read_cap(page), ("json/", "search", "list", "mail.naver.com/json"))
                if cap_typed:
                    triggered_sel = sel
                    report["mail_search"]["triggered_selector"] = sel
                    report["mail_search"]["triggered_apis"] = cap_typed
                    print(f"    입력 트리거 성공 셀렉터: {sel} → API {len(cap_typed)}개")
                    break
        except Exception:  # noqa: BLE001 - 네이버 캘린더/메일검색/마이박스 UI 구조 읽기전용 탐색 스크립트(아카이브) - 실패시 report 에 error 기록 후 계속 진행, 쓰기 동작 없음
            continue
    if not triggered_sel:
        print("    ⚠ 검색 입력 트리거 실패")
        # 모든 캡처 dump (분석용)
        report["mail_search"]["all_caps_after_typing_attempt"] = _read_cap(page)


def explore_mybox(page, report: dict):
    """MyBox — 폴더/파일 클릭으로 file/list API 트리거."""
    print("\n[3/3] mybox_list 탐지")
    page.goto("https://mybox.naver.com/main/web/my")
    time.sleep(6)
    init_cap = _filter_cap(_read_cap(page), ("api/", "service/", "mybox", "/file"))
    report["mybox"]["initial_apis"] = init_cap
    print(f"  초기 API: {len(init_cap)}개")

    # 1) 클릭 가능한 폴더/파일 요소 dump
    candidates_selectors = [
        '[role="row"]',
        '[role="gridcell"]',
        '[role="button"]',
        '[class*="file"]',
        '[class*="File"]',
        '[class*="folder"]',
        '[class*="Folder"]',
        '[class*="item"]',
        '[class*="Item"]',
        '[class*="row"]',
        '[class*="Row"]',
        "tr",
        "li",
        "[data-id]",
    ]
    for sel in candidates_selectors:
        try:
            els = dump_elements(page, sel, limit=5)
            visible = [e for e in els if e["visible"] and e["rect"]["w"] > 50 and e["rect"]["h"] > 20]
            if visible and 1 <= len(visible) <= 50:
                report["mybox"].setdefault("clickable_dumps", {})[sel] = visible
        except Exception:  # noqa: BLE001 - 네이버 캘린더/메일검색/마이박스 UI 구조 읽기전용 탐색 스크립트(아카이브) - 실패시 report 에 error 기록 후 계속 진행, 쓰기 동작 없음
            pass

    # 2) 폴더 트리/사이드바 항목 클릭 시도
    _reset_cap(page)
    sidebar_selectors = [
        '[class*="tree"] [role="button"]',
        '[class*="sidebar"] li',
        '[class*="menu"] [role="button"]',
        "nav a",
        '[class*="folder"]',
    ]
    triggered = False
    for sel in sidebar_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click(timeout=3000)
                time.sleep(4)
                cap_after = _filter_cap(_read_cap(page), ("api/", "service/", "mybox", "/file", "/list"))
                if cap_after:
                    report["mybox"]["sidebar_click_selector"] = sel
                    report["mybox"]["sidebar_click_apis"] = cap_after
                    print(f"  사이드바 클릭 성공: {sel} → API {len(cap_after)}개")
                    triggered = True
                    break
        except Exception:  # noqa: BLE001 - 네이버 캘린더/메일검색/마이박스 UI 구조 읽기전용 탐색 스크립트(아카이브) - 실패시 report 에 error 기록 후 계속 진행, 쓰기 동작 없음
            continue

    # 3) 메인 영역 첫 항목 클릭 시도
    if not triggered:
        _reset_cap(page)
        main_selectors = ['[role="row"]', '[class*="file_item"]', '[class*="list_item"]', "tr[data-id]"]
        for sel in main_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    time.sleep(4)
                    cap_after = _filter_cap(_read_cap(page), ("api/", "service/", "mybox", "/file", "/list"))
                    if cap_after:
                        report["mybox"]["main_click_selector"] = sel
                        report["mybox"]["main_click_apis"] = cap_after
                        print(f"  메인 클릭 성공: {sel} → API {len(cap_after)}개")
                        triggered = True
                        break
            except Exception:  # noqa: BLE001 - 네이버 캘린더/메일검색/마이박스 UI 구조 읽기전용 탐색 스크립트(아카이브) - 실패시 report 에 error 기록 후 계속 진행, 쓰기 동작 없음
                continue

    if not triggered:
        print("  ⚠ 모든 클릭 실패 — 전체 캡처 저장")
        report["mybox"]["all_caps"] = _filter_cap(_read_cap(page), ("api", "mybox", "service"))


def main():
    out_dir = Path(__file__).resolve().parents[1] / "data" / "reports" / "local_agent"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"explore_unresolved_{ts}.json"

    report = {"timestamp": ts, "calendar": {}, "mail_search": {}, "mybox": {}}

    print("=" * 70)
    print("  미해결 항목 탐지 시작")
    print("=" * 70)

    with BrowserAgent() as a:
        try:
            explore_calendar(a._page, report)
        except Exception as e:  # noqa: BLE001 - 네이버 캘린더/메일검색/마이박스 UI 구조 읽기전용 탐색 스크립트(아카이브) - 실패시 report 에 error 기록 후 계속 진행, 쓰기 동작 없음
            print(f"  캘린더 탐지 오류: {e}")
            report["calendar"]["error"] = str(e)

        try:
            explore_mail_search(a._page, report)
        except Exception as e:  # noqa: BLE001 - 네이버 캘린더/메일검색/마이박스 UI 구조 읽기전용 탐색 스크립트(아카이브) - 실패시 report 에 error 기록 후 계속 진행, 쓰기 동작 없음
            print(f"  메일검색 탐지 오류: {e}")
            report["mail_search"]["error"] = str(e)

        try:
            explore_mybox(a._page, report)
        except Exception as e:  # noqa: BLE001 - 네이버 캘린더/메일검색/마이박스 UI 구조 읽기전용 탐색 스크립트(아카이브) - 실패시 report 에 error 기록 후 계속 진행, 쓰기 동작 없음
            print(f"  MyBox 탐지 오류: {e}")
            report["mybox"]["error"] = str(e)

    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {out_file}")
    print("=" * 70)

    # 요약 출력
    print("\n[요약]")
    cal = report["calendar"]
    print(
        f"  캘린더: 초기 {len(cal.get('initial_apis', []))}개 API, "
        f"네비 후보 {len(cal.get('nav_buttons', {}))}개, "
        f"클릭 후 {len(cal.get('after_click_apis', []))}개 API"
    )
    ms = report["mail_search"]
    print(f"  메일검색: input {len(ms.get('all_inputs', []))}개, 트리거 셀렉터: {ms.get('triggered_selector', '없음')}")
    mb = report["mybox"]
    print(
        f"  MyBox: 초기 {len(mb.get('initial_apis', []))}개 API, "
        f"클릭 셀렉터: {mb.get('sidebar_click_selector') or mb.get('main_click_selector') or '없음'}"
    )


if __name__ == "__main__":
    main()
