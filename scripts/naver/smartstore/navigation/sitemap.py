"""스마트스토어 셀러센터 정밀 사이트맵 탐색 (모든 클릭 로그).

각 메뉴 클릭의 모든 과정을 상세 로그로 기록:
  - 클릭 시각 / 클릭 대상 텍스트
  - 클릭 전 URL → 클릭 후 URL
  - 클릭 성공 여부 (요소 발견/클릭/URL변화)
  - 펼쳐진 하위 메뉴 개수
  - 페이지 메타 (필드/버튼/테이블)
  - 실패 시 원인

결과:
  - data/sitemap/smartstore_sellercenter_deep.json  (사이트맵)
  - data/logs/smartstore_explorer.log              (모든 클릭 로그)
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.auth.login_detector import get_logged_in_user, is_logged_in_generic  # noqa: E402
from scripts.browser.cdp.connection import get_page  # noqa: E402
from scripts.browser.popup.popup_detector import close_popup_windows, handle_page_popups  # noqa: E402
from scripts.common.critical_logger import log_critical  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402

_log = get_logger(__name__)

SELLER_HOST = "sell.smartstore.naver.com"
DASHBOARD_URL = f"https://{SELLER_HOST}/#/home/dashboard"
OUTPUT = ROOT / "data" / "sitemap" / "smartstore_sellercenter_deep.json"
LOG_FILE = ROOT / "data" / "logs" / "smartstore_explorer.log"


# ── 상세 클릭 로거 ──────────────────────────────────────────────────────────


class ClickLogger:
    """모든 클릭/탐색 이벤트를 텍스트 파일 + 메모리에 기록."""

    def __init__(self, log_file: Path):
        self.events: list[dict] = []
        self.log_file = log_file
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # 헤더
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"\n\n{'=' * 70}\n")
            f.write(f"  스마트스토어 탐색 시작: {datetime.now().isoformat(timespec='seconds')}\n")
            f.write(f"{'=' * 70}\n")

    def log(self, event_type: str, **kwargs) -> None:
        ts = datetime.now().isoformat(timespec="seconds")
        ev = {"ts": ts, "type": event_type, **kwargs}
        self.events.append(ev)
        # 한 줄 텍스트 포맷
        line = f"[{ts}] {event_type:<14} "
        line += " | ".join(f"{k}={v}" for k, v in kwargs.items() if v not in (None, "", []))
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(line[:500] + "\n")
        # 콘솔에도 짧게
        print(
            f"    LOG[{event_type}] " + " ".join(f"{k}={str(v)[:30]}" for k, v in list(kwargs.items())[:3]), flush=True
        )


# ── 사이드바 메뉴 추출 ──────────────────────────────────────────────────────

EXTRACT_SIDEBAR_JS = r"""
() => {
    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };
    const menus = [];
    const seen = new Set();
    document.querySelectorAll('a, li, button').forEach(el => {
        if (!isVisible(el)) return;
        const text = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
        if (!text || text.length < 2 || text.length > 25 || seen.has(text)) return;
        const r = el.getBoundingClientRect();
        if (r.x >= -10 && r.x < 70 && r.y > 150 && r.height < 60) {
            seen.add(text);
            menus.push({
                text: text, tag: el.tagName,
                href: (el.href || '').substring(0, 200),
                pos: [Math.round(r.x), Math.round(r.y)],
            });
        }
    });
    menus.sort((a, b) => a.pos[1] - b.pos[1]);
    return menus;
}
"""


SUBMENU_JS = r"""
(parentY) => {
    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };
    const sub = [];
    const seen = new Set();
    document.querySelectorAll('a, li, button').forEach(el => {
        if (!isVisible(el)) return;
        const text = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
        if (!text || text.length < 2 || text.length > 30 || seen.has(text)) return;
        const r = el.getBoundingClientRect();
        // 좌측 영역 (x: 5~280) + 부모 근처 (y: parentY-100 ~ parentY+800)
        if (r.x >= 5 && r.x < 280 && r.height < 50 && r.y >= parentY - 100 && r.y < parentY + 800) {
            seen.add(text);
            sub.push({
                text: text, tag: el.tagName,
                href: (el.href || '').substring(0, 200),
                pos: [Math.round(r.x), Math.round(r.y)],
            });
        }
    });
    sub.sort((a, b) => a.pos[1] - b.pos[1]);
    return sub;
}
"""


PAGE_META_JS = r"""
() => {
    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };
    const result = { url: location.href, title: document.title };
    result.heading = document.querySelector('h1, h2, [class*="title"]')?.innerText?.trim().substring(0, 80) || '';

    const txt = (document.body?.innerText || '').toLowerCase();
    result.is_product_register = /상품\s*등록|판매상품\s*등록|new\s*product|상품\s*신규/.test(txt) ||
        /상품등록/.test(result.heading || '');
    result.is_list = document.querySelectorAll('table tbody tr').length > 1;
    result.is_form = document.querySelectorAll('input, select, textarea').length > 5;

    const fields = [];
    document.querySelectorAll('input, select, textarea').forEach(el => {
        if (!isVisible(el)) return;
        const type = (el.type || el.tagName).toLowerCase();
        if (type === 'hidden') return;
        let label = el.getAttribute('aria-label') || el.placeholder || '';
        if (!label && el.id) {
            const l = document.querySelector(`label[for="${el.id}"]`);
            if (l) label = (l.innerText || '').trim();
        }
        fields.push({type, name: el.name || el.id || '', label: label.substring(0, 40),
                     required: el.required || el.getAttribute('aria-required') === 'true'});
    });
    result.fields = fields.slice(0, 80);
    result.field_count = fields.length;

    const buttons = [];
    const seenBtn = new Set();
    document.querySelectorAll('button, a.btn, a[role=button]').forEach(b => {
        if (!isVisible(b)) return;
        const text = (b.innerText || '').trim().substring(0, 25);
        if (text && text.length >= 2 && !seenBtn.has(text)) {
            seenBtn.add(text);
            buttons.push({text});
        }
    });
    result.buttons = buttons.slice(0, 30);

    const tables = [];
    document.querySelectorAll('table').forEach(t => {
        if (!isVisible(t)) return;
        const headers = Array.from(t.querySelectorAll('thead th, thead td'))
            .map(h => (h.innerText || '').trim().substring(0, 30)).filter(Boolean);
        if (headers.length) tables.push({headers, row_count: t.querySelectorAll('tbody tr').length});
    });
    result.tables = tables.slice(0, 3);

    return result;
}
"""


# ── 클릭 (로그 포함) ────────────────────────────────────────────────────────


def click_with_log(page, text: str, clicker: ClickLogger, wait_s: float = 2.5, reason: str = "") -> dict:
    """텍스트 메뉴 클릭 — 실제 마우스 이벤트 (Playwright 네이티브).

    동작:
      1. 좌측 영역(x<280)에서 정확 텍스트 매칭되는 요소 좌표 추출
      2. page.mouse.move(x,y) → hover (사람처럼)
      3. page.mouse.click(x,y) — 실제 마우스 이벤트
      4. URL 변화 대기

    JS의 el.click()이 아닌 실제 마우스 이벤트라서 SPA onclick/이벤트 위임 정상 작동.
    """
    before_url = page.url
    clicker.log("click_start", target=text, before_url=before_url, reason=reason)
    try:
        # 1. 좌측 영역의 매칭 요소 좌표 + tag 추출
        candidates = page.evaluate(
            r"""
        (text) => {
            const isVisible = (el) => {
                const s = window.getComputedStyle(el);
                if (s.display === 'none' || s.visibility === 'hidden') return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            };
            const out = [];
            for (const el of document.querySelectorAll('a, button, li, span, div[role="button"]')) {
                if (!isVisible(el)) continue;
                const t = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
                if (t === text) {
                    const r = el.getBoundingClientRect();
                    out.push({
                        tag: el.tagName,
                        cls: (el.className || '').substring(0, 50),
                        x: Math.round(r.x + r.width / 2),  // 요소 중앙
                        y: Math.round(r.y + r.height / 2),
                        rect_x: Math.round(r.x),
                        has_onclick: !!el.onclick || !!el.getAttribute('onclick'),
                    });
                }
            }
            // 좌측 영역 우선 (rect_x < 280), 동률이면 y가 작은 것 (위쪽)
            out.sort((a, b) => {
                const aLeft = a.rect_x < 280 ? 0 : 1;
                const bLeft = b.rect_x < 280 ? 0 : 1;
                if (aLeft !== bLeft) return aLeft - bLeft;
                return a.y - b.y;
            });
            return out;
        }
        """,
            text,
        )

        if not candidates:
            clicker.log("click_failed", target=text, reason="not_found")
            return {"ok": False, "reason": "not_found"}

        target = candidates[0]
        clicker.log(
            "click_target_found",
            target=text,
            x=target["x"],
            y=target["y"],
            tag=target["tag"],
            cls=target["cls"][:30],
            has_onclick=target["has_onclick"],
            candidates=len(candidates),
        )

        # 2. 실제 마우스 이동 + hover (사람처럼)
        page.mouse.move(target["x"], target["y"])
        time.sleep(0.2)

        # 3. 실제 마우스 클릭
        page.mouse.click(target["x"], target["y"])
        clicker.log("click_executed", target=text, x=target["x"], y=target["y"], method="mouse.click")

        # 4. URL 변화 대기 (또는 컨텐츠 변화)
        deadline = time.time() + wait_s
        url_changed = False
        while time.time() < deadline:
            if page.url != before_url:
                url_changed = True
                break
            time.sleep(0.3)
        time.sleep(1.2)

        clicker.log("click_result", target=text, url_changed=url_changed, after_url=page.url[:100])
        return {"ok": True, "url_changed": url_changed, "after_url": page.url, "x": target["x"], "y": target["y"]}
    except Exception as e:  # noqa: BLE001 - 스마트스토어 관리자 메뉴 트리 읽기전용 매핑(클릭하며 사이트맵 구축) - 실패시 error 필드 기록, 데이터 변경 없음
        clicker.log("click_exception", target=text, error=str(e)[:80])
        return {"ok": False, "reason": str(e)[:80]}


# ── 메인 ────────────────────────────────────────────────────────────────────


def _find_seller_page(clicker: ClickLogger):
    """셀러센터 탭 찾기 (없으면 새 탭)."""
    existing = get_page()
    ctx = existing.context
    page = None
    for p in ctx.pages:
        try:
            if SELLER_HOST in p.url:
                page = p
                clicker.log("tab_reuse", url=p.url[:80])
                break
        except Exception:  # noqa: BLE001 - 스마트스토어 관리자 메뉴 트리 읽기전용 매핑(클릭하며 사이트맵 구축) - 실패시 error 필드 기록, 데이터 변경 없음
            continue
    if page is None:
        page = ctx.new_page()
        clicker.log("tab_new", reason="no_existing_seller_tab")
    return page


def _enter_dashboard(page, clicker: ClickLogger):
    """대시보드 진입 + 팝업 처리 + 로그인 확인. 로그인된 사용자 반환."""
    clicker.log("goto_start", url=DASHBOARD_URL)
    page.goto(DASHBOARD_URL, timeout=20000, wait_until="domcontentloaded")
    time.sleep(5)
    try:
        handle_page_popups(page, timeout_s=2.0)
        close_popup_windows(page)
        clicker.log("popups_handled")
    except Exception as e:  # noqa: BLE001 - 스마트스토어 관리자 메뉴 트리 읽기전용 매핑(클릭하며 사이트맵 구축) - 실패시 error 필드 기록, 데이터 변경 없음
        clicker.log("popups_error", error=str(e)[:80])

    if not is_logged_in_generic(page):
        clicker.log("not_logged_in", url=page.url)
        print("  ✗ 로그인 필요")
        sys.exit(1)
    user = get_logged_in_user(page)
    clicker.log("login_confirmed", user=user, url=page.url)
    return user


def _click_main_menu(page, clicker: ClickLogger, text: str) -> bool:
    """메인 메뉴 클릭 (1차). 실패 시 대시보드 복귀 후 재시도. 최종 성공 여부 반환."""
    click_result = click_with_log(page, text, clicker, wait_s=3.0, reason="main_menu")
    if not click_result["ok"]:
        # 자동 복구 1: 대시보드 복귀 후 재시도
        clicker.log("recover_attempt", reason="main_menu_click_failed", action="goto_dashboard")
        page.goto(DASHBOARD_URL, timeout=15000, wait_until="domcontentloaded")
        time.sleep(3)
        click_result = click_with_log(page, text, clicker, wait_s=3.0, reason="main_menu_retry")
        if not click_result["ok"]:
            clicker.log("recover_failed", text=text, action="skip_menu")
            return False
    return True


def _read_page_meta(page, clicker: ClickLogger, text: str):
    """메인 페이지 메타."""
    try:
        page_meta = page.evaluate(PAGE_META_JS)
        clicker.log(
            "page_meta",
            text=text,
            url=page_meta.get("url", "")[:80],
            fields=page_meta.get("field_count", 0),
            buttons=len(page_meta.get("buttons", [])),
            is_product_register=page_meta.get("is_product_register"),
        )
    except Exception as e:  # noqa: BLE001 - 스마트스토어 관리자 메뉴 트리 읽기전용 매핑(클릭하며 사이트맵 구축) - 실패시 error 필드 기록, 데이터 변경 없음
        page_meta = {"error": str(e)[:80]}
        clicker.log("page_meta_error", error=str(e)[:80])
    return page_meta


def _recover_same_submenu(page, clicker: ClickLogger, text: str, parent_y, previous_submenu_names, submenus):
    """자동 복구 2: 직전 부모와 동일한 submenu (부모 클릭 안 됨). (submenus, 복구실패여부) 반환."""
    no_effect = False
    clicker.log("recover_attempt", reason="same_submenu_as_previous", text=text, action="reload_dashboard_and_retry")
    page.goto(DASHBOARD_URL, timeout=15000, wait_until="domcontentloaded")
    time.sleep(3)
    retry_click = click_with_log(page, text, clicker, wait_s=3.5, reason="recover_same_submenu")
    if retry_click["ok"]:
        submenus = page.evaluate(SUBMENU_JS, parent_y)
        submenus = [s for s in submenus if s["text"] != text]
        new_names = {s["text"] for s in submenus}
        if new_names == previous_submenu_names and new_names:
            # 복구 실패 → 이 부모는 skip
            clicker.log("recover_failed", text=text, reason="still_same_submenu", action="skip_submenus")
            submenus = []
            no_effect = True
        else:
            clicker.log("recover_success", text=text, new_submenu_count=len(new_names))
    return submenus, no_effect


def _extract_submenus(page, clicker: ClickLogger, text: str, parent_y, previous_submenu_names, page_meta):
    """하위 메뉴 추출. (submenus, 갱신된 previous_submenu_names) 반환."""
    try:
        submenus = page.evaluate(SUBMENU_JS, parent_y)
        submenus = [s for s in submenus if s["text"] != text]
        current_names = {s["text"] for s in submenus}

        # 자동 복구 2: 직전 부모와 동일한 submenu (부모 클릭 안 됨)
        if previous_submenu_names is not None and current_names == previous_submenu_names and current_names:
            submenus, no_effect = _recover_same_submenu(
                page, clicker, text, parent_y, previous_submenu_names, submenus
            )
            if no_effect:
                page_meta["error"] = "parent_click_no_effect"

        previous_submenu_names = {s["text"] for s in submenus} if submenus else previous_submenu_names
        clicker.log("submenu_extracted", parent=text, count=len(submenus), names=[s["text"] for s in submenus[:8]])
    except Exception as e:  # noqa: BLE001 - 스마트스토어 관리자 메뉴 트리 읽기전용 매핑(클릭하며 사이트맵 구축) - 실패시 error 필드 기록, 데이터 변경 없음
        submenus = []
        clicker.log("submenu_error", parent=text, error=str(e)[:80])
    return submenus, previous_submenu_names


def _visit_submenu_pages(page, clicker: ClickLogger, text: str, submenus: list) -> list:
    """하위 메뉴 페이지 진입 (최대 8개)."""
    sub_pages = []
    for j, s in enumerate(submenus[:8], 1):
        sub_text = s["text"]
        print(f"      [{j}/{min(len(submenus), 8)}] {sub_text}", end=" ", flush=True)
        # 부모 다시 클릭 (펼침)
        click_with_log(page, text, clicker, wait_s=1.5, reason="re_expand_parent")
        sub_click = click_with_log(page, sub_text, clicker, wait_s=2.5, reason="submenu")
        if not sub_click["ok"]:
            print("✗")
            continue
        try:
            sm = page.evaluate(PAGE_META_JS)
            sm["menu_text"] = sub_text
            sub_pages.append(sm)
            tag = "[상품등록]" if sm.get("is_product_register") else ("[폼]" if sm.get("is_form") else "")
            print(f"✓ 필드:{sm.get('field_count', 0)} 버튼:{len(sm.get('buttons', []))} {tag}")
            clicker.log(
                "submenu_page_meta",
                parent=text,
                menu=sub_text,
                url=sm.get("url", "")[:80],
                fields=sm.get("field_count", 0),
            )
        except Exception as e:  # noqa: BLE001 - 스마트스토어 관리자 메뉴 트리 읽기전용 매핑(클릭하며 사이트맵 구축) - 실패시 error 필드 기록, 데이터 변경 없음
            print(f"메타실패 {str(e)[:30]}")
            clicker.log("submenu_page_error", menu=sub_text, error=str(e)[:80])
    return sub_pages


def _explore_menu(page, clicker: ClickLogger, i: int, total: int, m: dict, previous_submenu_names):
    """메인 메뉴 1개 탐색. (트리 항목, 갱신된 previous_submenu_names) 반환."""
    text = m["text"]
    parent_y = m["pos"][1]
    print(f"\n  [{i:2}/{total}] {text}")
    clicker.log("menu_loop", index=i, total=total, text=text)

    # 메뉴 클릭 (1차)
    if not _click_main_menu(page, clicker, text):
        return {**m, "click_ok": False, "submenus": [], "submenu_pages": []}, previous_submenu_names

    # 메인 페이지 메타
    page_meta = _read_page_meta(page, clicker, text)

    # 하위 메뉴 추출
    submenus, previous_submenu_names = _extract_submenus(
        page, clicker, text, parent_y, previous_submenu_names, page_meta
    )

    sub_pages = _visit_submenu_pages(page, clicker, text, submenus)

    return (
        {**m, "click_ok": True, "page_meta": page_meta, "submenus": submenus, "submenu_pages": sub_pages},
        previous_submenu_names,
    )


def _find_register_candidates(full_tree: list) -> list:
    """상품등록 후보 식별."""
    candidates = []
    for t in full_tree:
        if t.get("page_meta", {}).get("is_product_register"):
            candidates.append({"parent": t["text"], "from": "main", "page": t["page_meta"]})
        for sp in t.get("submenu_pages", []):
            if sp.get("is_product_register"):
                candidates.append({"parent": t["text"], "from": "sub", "menu": sp.get("menu_text"), "page": sp})
    return candidates


def main():
    clicker = ClickLogger(LOG_FILE)
    print(f"\n{'=' * 70}")
    print("  스마트스토어 사이트맵 (모든 클릭 로그)")
    print(f"  로그 파일: {LOG_FILE.name}")
    print(f"{'=' * 70}\n")

    page = _find_seller_page(clicker)
    user = _enter_dashboard(page, clicker)

    # 사이드바 추출
    main_menus = page.evaluate(EXTRACT_SIDEBAR_JS)
    clicker.log("sidebar_extracted", count=len(main_menus), names=[m["text"] for m in main_menus])
    print(f"  메인 메뉴 {len(main_menus)}개 발견")

    # 각 메인 메뉴 + 하위 + 페이지 메타
    full_tree = []
    previous_submenu_names: set | None = None  # 직전 부모의 submenu 텍스트 집합 (중복 감지)
    for i, m in enumerate(main_menus, 1):
        entry, previous_submenu_names = _explore_menu(page, clicker, i, len(main_menus), m, previous_submenu_names)
        full_tree.append(entry)

    candidates = _find_register_candidates(full_tree)

    output = {
        "domain": SELLER_HOST,
        "user": user,
        "explored_at": datetime.now().isoformat(timespec="seconds"),
        "main_menu_count": len(main_menus),
        "total_submenus": sum(len(t.get("submenus", [])) for t in full_tree),
        "total_pages": sum(len(t.get("submenu_pages", [])) for t in full_tree),
        "menu_tree": full_tree,
        "product_register_candidates": candidates,
        "click_log": clicker.events,  # 모든 클릭 이벤트 JSON에도
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  ✓ 저장: {OUTPUT.name}")
    print(f"     메인 {len(main_menus)} | 하위 {output['total_submenus']} | 페이지 {output['total_pages']}")
    print(f"     상품등록 후보: {len(candidates)}")
    print(f"     클릭 이벤트: {len(clicker.events)}")
    print(f"     상세 로그: {LOG_FILE}")

    log_critical(
        "OTHER",
        "스마트스토어 사이트맵 완료",
        user=user,
        menus=len(main_menus),
        pages=output["total_pages"],
        click_events=len(clicker.events),
        candidates=len(candidates),
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단됨")
    except Exception:  # noqa: BLE001 - 스마트스토어 관리자 메뉴 트리 읽기전용 매핑(클릭하며 사이트맵 구축) - 실패시 error 필드 기록, 데이터 변경 없음
        import traceback

        traceback.print_exc()
        sys.exit(1)
