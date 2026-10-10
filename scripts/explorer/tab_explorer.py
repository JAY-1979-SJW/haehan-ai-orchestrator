"""탭 인터페이스 순회 + 활성 패널 추출 + JSON 저장.

기본 셀렉터(`button.tab_link`)는 건설e음 등 일반적인 패턴.
다른 사이트는 tab_selector 인자로 셀렉터 지정 가능.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.common.logger import get_logger
from scripts.browser.cdp.connection import get_page

_log = get_logger(__name__)

DEFAULT_TAB_SELECTOR = "button.tab_link"
DEFAULT_PANEL_SELECTOR = ".form_cont.tab_cont.on, [role='tabpanel'][aria-hidden='false'], .tab_cont.on"


_EXTRACT_PANEL_JS = r"""
(panelSel) => {
    const cont = document.querySelector(panelSel);
    if (!cont) return null;
    const inputs = Array.from(cont.querySelectorAll('input, select, textarea')).map(e => ({
        tag: e.tagName,
        type: e.getAttribute('type') || '',
        name: e.getAttribute('name') || '',
        id: e.id || '',
        placeholder: e.getAttribute('placeholder') || '',
        aria: e.getAttribute('aria-label') || '',
        visible: e.offsetParent !== null,
    }));
    const buttons = Array.from(cont.querySelectorAll('button, a.btn, [role="button"]')).map(b => ({
        text: (b.innerText || '').trim().slice(0, 80),
        cls: (b.className || '').toString().slice(0, 80),
        id: b.id || '',
        href: b.getAttribute('href') || '',
    })).filter(b => b.text);
    const links = Array.from(cont.querySelectorAll('a')).map(a => ({
        text: (a.innerText || '').trim().slice(0, 60),
        href: a.getAttribute('href') || '',
    })).filter(l => l.text);
    return {
        id: cont.id || '',
        innerText: (cont.innerText || '').trim().slice(0, 800),
        inputs, buttons, links,
    };
}
"""

_LIST_TABS_JS = r"""
(tabSel) => Array.from(document.querySelectorAll(tabSel)).map(b => (b.innerText || '').trim()).filter(Boolean)
"""

_CLICK_TAB_JS = r"""
(args) => {
    const [tabSel, name] = args;
    const btn = Array.from(document.querySelectorAll(tabSel)).find(b => (b.innerText || '').trim() === name);
    if (!btn) return {clicked: false, reason: 'not found'};
    btn.click();
    return {clicked: true};
}
"""


def slugify(url: str) -> str:
    s = url.replace("https://", "").replace("http://", "")
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", s)[:120]


def explore_tabs(
    page,
    tab_selector: str = DEFAULT_TAB_SELECTOR,
    panel_selector: str = DEFAULT_PANEL_SELECTOR,
    save_dir: str = "data/sitemap",
    settle_ms: int = 800,
    restore_initial: bool = True,
) -> dict[str, Any]:
    """탭 순회 + 각 활성 패널 추출 + 저장.

    Args:
        page: Playwright Page
        tab_selector: 탭 버튼 셀렉터
        panel_selector: 현재 활성 패널 셀렉터 (탭 클릭 후 활성화된 패널)
        save_dir: 저장 디렉터리
        settle_ms: 탭 클릭 후 패널 안정화 대기 (ms)
        restore_initial: 종료 시 첫 탭으로 복귀 (기본 True)

    Returns: {path, url, title, tabs: [...]}
    """
    main = page.frames[0]
    url = page.url
    title = page.title()

    tab_names = main.evaluate(_LIST_TABS_JS, tab_selector)
    if not tab_names:
        _log.warning("[explorer] 탭 없음: %s (selector=%s)", url, tab_selector)
        return {"error": f"탭 없음 (selector={tab_selector})", "url": url}

    initial_tab = tab_names[0]
    settle_s = settle_ms / 1000.0

    _log.info("[explorer] 탭 탐색 시작: %s (%d탭)", url, len(tab_names))

    results: dict[str, Any] = {
        "url": url,
        "title": title,
        "captured_at": datetime.now().isoformat(),
        "tab_selector": tab_selector,
        "panel_selector": panel_selector,
        "tabs": [],
    }

    for tab_name in tab_names:
        _log.debug("[explorer] 탭 클릭: %s", tab_name)
        click = main.evaluate(_CLICK_TAB_JS, [tab_selector, tab_name])
        time.sleep(settle_s)
        snap = main.evaluate(_EXTRACT_PANEL_JS, panel_selector)
        results["tabs"].append({"tab": tab_name, "click": click, **(snap or {})})

    if restore_initial:
        main.evaluate(_CLICK_TAB_JS, [tab_selector, initial_tab])
        time.sleep(0.3)
        _log.debug("[explorer] 첫 탭으로 복귀: %s", initial_tab)

    Path(save_dir).mkdir(parents=True, exist_ok=True)
    out_path = Path(save_dir) / f"{slugify(url)}_login_tabs.json"
    with out_path.open("w", encoding="utf-8") as fp:
        json.dump(results, fp, ensure_ascii=False, indent=2)

    results["path"] = str(out_path)
    _log.info("[explorer] 탭 탐색 저장: %s", out_path)
    return results


def run_cli(args: list[str]) -> None:
    """CLI: explore tabs [tab_selector] [panel_selector]."""
    tab_sel = args[0] if args else DEFAULT_TAB_SELECTOR
    panel_sel = args[1] if len(args) > 1 else DEFAULT_PANEL_SELECTOR
    _log.info("[explorer] CLI 탭 탐색 요청: tab_selector=%s", tab_sel)
    page = get_page()
    r = explore_tabs(page, tab_selector=tab_sel, panel_selector=panel_sel)
    if "error" in r:
        print(f"\n✗ {r['error']}")
        _log.error("[explorer] 탭 탐색 실패: %s", r["error"])
        return
    print(f"\n✓ 탭 탐색 저장: {r['path']}")
    print(f"  URL: {r['url']}")
    print(f"  탭 셀렉터: {r['tab_selector']}")
    print(f"  총 탭: {len(r['tabs'])}")
    for t in r["tabs"]:
        if "inputs" in t:
            print(
                f"  - [{t['tab']}] panel_id={t.get('id', '')} "
                f"inputs={len(t['inputs'])} buttons={len(t['buttons'])} "
                f"links={len(t['links'])}"
            )
        else:
            print(f"  - [{t['tab']}] click 실패: {t.get('click', {})}")
