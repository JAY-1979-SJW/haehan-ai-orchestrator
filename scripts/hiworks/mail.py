"""Hiworks mail compose helpers.

These helpers prepare drafts only. They never click the send button.
"""
from __future__ import annotations

from typing import Any

from scripts.hiworks.schemas import HIWORKS_MAIL_URL


def inspect_compose_page(page) -> dict[str, Any]:
    return page.evaluate(
        """() => ({
          url: location.href,
          title: document.title,
          inputs: Array.from(document.querySelectorAll('input, textarea, [contenteditable=true]')).map((el, idx) => ({
            index: idx,
            tag: el.tagName.toLowerCase(),
            type: el.type || '',
            name: el.name || '',
            id: el.id || '',
            placeholder: el.placeholder || '',
            aria: el.getAttribute('aria-label') || '',
            text: (el.innerText || el.value || '').slice(0, 120),
            visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
          })).slice(0, 120),
          buttons: Array.from(document.querySelectorAll('button, a[href]')).map((el, idx) => ({
            index: idx,
            text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim(),
            href: el.href || '',
            id: el.id || '',
            className: String(el.className || '').slice(0, 120),
            visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
          })).filter((x) => x.text || x.href).slice(0, 160)
        })"""
    )


def open_compose(page) -> dict[str, Any]:
    if "mails.office.hiworks.com" not in (page.url or ""):
        page.goto(HIWORKS_MAIL_URL, timeout=30000)
    page.wait_for_timeout(1500)
    candidates = [
        "a:has-text('메일 쓰기')",
        "button:has-text('메일 쓰기')",
        "a[href*='write']",
        "a[href*='compose']",
    ]
    clicked = ""
    for selector in candidates:
        locator = page.locator(selector).first
        if locator.count() > 0:
            try:
                locator.click(timeout=5000)
            except Exception:
                # Hiworks SPA can handle the click while Playwright waits for
                # completion. Continue and inspect the resulting state.
                pass
            clicked = selector
            break
    if not clicked:
        raise RuntimeError("Hiworks compose button not found")
    page.wait_for_timeout(2500)
    return {"clicked": clicked, "summary": inspect_compose_page(page)}


def fill_compose(page, *, to: str, subject: str, body: str) -> dict[str, Any]:
    """Fill Hiworks compose fields without sending."""
    if "/write" not in (page.url or ""):
        open_compose(page)

    inputs = page.locator("input[type='text']")
    if inputs.count() < 2:
        raise RuntimeError("Hiworks compose text inputs not found")
    inputs.nth(0).fill(to, timeout=5000)
    page.keyboard.press("Enter")
    inputs.nth(1).fill(subject, timeout=5000)

    editor_frame = None
    for frame in page.frames:
        try:
            if frame.frame_element().get_attribute("class") == "se-contents-edit":
                editor_frame = frame
                break
        except Exception:
            pass
    if editor_frame:
        editor_frame.evaluate(
            """(text) => {
              document.body.focus();
              document.body.innerHTML = text.split('\\n').map((line) => `<p>${line || '<br>'}</p>`).join('');
              document.body.dispatchEvent(new Event('input', {bubbles: true}));
              document.body.dispatchEvent(new Event('change', {bubbles: true}));
            }""",
            body,
        )
    else:
        editors = page.locator("[contenteditable='true']").filter(has_not=page.locator(".se-clipboard"))
        if editors.count() > 0:
            editors.first.fill(body, timeout=5000)
        else:
            textarea = page.locator("textarea").first
            textarea.fill(body, timeout=5000)

    return {
        "ok": True,
        "url": page.url,
        "to": to,
        "subject": subject,
        "sent": False,
        "note": "filled only; send button was not clicked",
    }
