"""page_helper 실시간 브라우저 상태 감시 — page_inspect."""
from __future__ import annotations

from playwright.sync_api import Page

from scripts.common.logger import get_logger

log = get_logger(__name__)


def page_inspect(page: Page, label: str = "") -> dict:
    """현재 페이지의 실제 요소 상태를 실시간으로 수집·출력.

    각 단계 진입 시 호출하면 실제 셀렉터를 파악할 수 있다.
    반환값: { url, title, inputs, buttons, errors }
    """
    tag = f"[inspect{':' + label if label else ''}]"

    result = page.evaluate("""() => {
        const inputs = Array.from(document.querySelectorAll('input:not([type=hidden])'))
            .filter(el => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            })
            .map(el => ({
                id:          el.id || '',
                name:        el.name || '',
                type:        el.type || '',
                placeholder: el.placeholder || '',
                value:       el.value || '',
                class:       el.className || '',
            }));

        const buttons = Array.from(document.querySelectorAll(
            'button, [role="button"], input[type=submit], a[role="button"]'
        ))
            .filter(el => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && !el.disabled;
            })
            .map(el => ({
                text:  (el.innerText || el.value || '').trim().slice(0, 60),
                id:    el.id || '',
                class: el.className || '',
                role:  el.getAttribute('role') || '',
            }))
            .filter(b => b.text);

        const errors = Array.from(document.querySelectorAll(
            '[role="alert"], .mat-error, .error-message, .cfc-error'
        ))
            .map(el => el.innerText.trim())
            .filter(t => t);

        return { inputs, buttons, errors };
    }""")

    url   = page.url
    title = page.title()

    log.debug("%s URL=%s TITLE=%s", tag, url, title)
    print(f"  {tag} URL: {url}")
    print(f"  {tag} TITLE: {title}")

    inputs  = result.get("inputs", [])
    buttons = result.get("buttons", [])
    errors  = result.get("errors", [])

    if inputs:
        print(f"  {tag} INPUT ({len(inputs)}개):")
        for inp in inputs:
            print(f"    id={inp['id']!r:20} type={inp['type']!r:10} "
                  f"placeholder={inp['placeholder']!r:30} value={inp['value']!r}")
    else:
        print(f"  {tag} INPUT: 없음")

    if buttons:
        print(f"  {tag} BUTTON ({len(buttons)}개):")
        for btn in buttons[:10]:  # 최대 10개만 출력
            print(f"    text={btn['text']!r:40} id={btn['id']!r}")
    else:
        print(f"  {tag} BUTTON: 없음")

    if errors:
        print(f"  {tag} ERROR: {errors}")

    log.debug("%s inputs=%d buttons=%d errors=%d", tag, len(inputs), len(buttons), len(errors))
    return {"url": url, "title": title, "inputs": inputs, "buttons": buttons, "errors": errors}
