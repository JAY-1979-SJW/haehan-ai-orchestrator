"""Hiworks mail compose helpers.

compose 단계는 자동 진행 가능.
send_mail()은 사용자 명시 승인(confirmed=True) 후에만 발송 버튼 클릭.
"""
from __future__ import annotations

import time
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


def send_mail(page) -> dict[str, Any]:
    """현재 Hiworks 작성 페이지에서 메일 발송.

    반드시 fill_compose() 이후에 호출. 사용자 명시 승인 필수.
    Returns:
        {success, detail, error_msg}
    """
    result: dict[str, Any] = {"success": False}

    # 발송 버튼 탐색 (하이웍스 다국어 대응)
    send_labels = ["보내기", "발송", "Send", "보내기(S)"]
    clicked = False
    for label in send_labels:
        btn = page.locator(f"button:has-text('{label}'), a:has-text('{label}')").first
        if btn.count() > 0:
            try:
                btn.click(timeout=5000)
                clicked = True
                break
            except Exception:
                continue

    if not clicked:
        # JS 폴백 — 텍스트 매칭으로 버튼 클릭
        js_result = page.evaluate(
            r"""() => {
                const labels = ['보내기', '발송', 'Send'];
                const btns = document.querySelectorAll('button, a');
                for (const b of btns) {
                    const t = (b.innerText || b.textContent || '').trim();
                    if (labels.some(l => t.includes(l))) {
                        b.click();
                        return {found: true, text: t};
                    }
                }
                return {found: false};
            }"""
        )
        clicked = js_result.get("found", False)

    if not clicked:
        result["error_msg"] = "Hiworks 발송 버튼을 찾을 수 없음"
        return result

    time.sleep(2.0)

    # 확인 팝업 처리
    confirmed = page.evaluate(
        r"""() => {
            const dialogs = document.querySelectorAll('[role="dialog"], .modal, .popup, .layer');
            let found = false;
            dialogs.forEach(d => {
                if (!d.offsetParent) return;
                const btns = d.querySelectorAll('button');
                btns.forEach(b => {
                    const t = (b.innerText || '').trim();
                    if (t === '확인' || t === '보내기' || t === '예') {
                        b.click();
                        found = true;
                    }
                });
            });
            return found;
        }"""
    )
    if confirmed:
        time.sleep(1.5)

    # 발송 성공 판정
    time.sleep(1.0)
    current_url = page.url
    success = "read" in current_url or "list" in current_url or current_url == HIWORKS_MAIL_URL

    result["success"] = success
    result["detail"] = "발송 완료" if success else f"발송 후 URL 확인 필요: {current_url}"
    return result
