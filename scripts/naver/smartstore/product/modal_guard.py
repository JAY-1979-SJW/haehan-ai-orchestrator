"""쌓인 경고 모달 정리 — 클릭 실패의 숨은 원인.

2026-08-15 실제 사고:
    '옵션목록으로 적용' 버튼 클릭이 계속 TimeoutError 였다. 셀렉터를 세 번 바꿨고
    (button -> a -> :visible) 전부 실패했다. 원인은 셀렉터가 아니었다.

    앞선 태그 입력에서 발생한 경고 모달이 **10개나 큐로 쌓여** 화면을 덮고 있었다.
        "태그 불가 단어: 인테리어조명 / 카테고리, 브랜드, 판매처명은 태그로 사용 불가합니다"
    Playwright 는 가려진 요소를 클릭하지 않으므로 정상 셀렉터도 전부 타임아웃난다.

교훈:
    클릭이 안 되면 셀렉터를 의심하기 전에 **무엇이 화면을 덮고 있는지** 먼저 본다.
    그리고 모달 텍스트는 버리지 않는다 — 왜 실패했는지가 거기 적혀 있다.
    (실제로 '인테리어조명' 태그가 거부된 이유를 이 모달이 알려줬다)
"""

from __future__ import annotations

from typing import Any

# 보이는 모달 1개의 텍스트와 버튼
_PEEK_JS = r"""
() => {
  const m = [...document.querySelectorAll('.modal, [role="dialog"]')]
      .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  if (!m.length) return null;
  return {
    text: (m[0].innerText || '').replace(/\s+/g, ' ').trim().slice(0, 200),
    buttons: [...m[0].querySelectorAll('button,a')]
        .map(b => (b.innerText || '').trim()).filter(Boolean).slice(0, 8),
  };
}
"""

# 확인/닫기 버튼을 눌러 1개 닫는다.
# Playwright 클릭은 '모달이 모달을 가리는' 상황에서 또 막히므로 DOM click 을 쓴다.
_DISMISS_ONE_JS = r"""
() => {
  const m = [...document.querySelectorAll('.modal, [role="dialog"]')]
      .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  if (!m.length) return false;
  const btn = [...m[0].querySelectorAll('button,a')]
      .find(b => /^(확인|닫기|OK|취소)$/.test((b.innerText || '').trim()));
  if (!btn) return false;
  btn.click();
  return true;
}
"""


def peek_modal(page: Any) -> dict | None:
    """현재 떠 있는 모달의 내용. 없으면 None."""
    try:
        return page.evaluate(_PEEK_JS)
    except Exception:
        return None


def dismiss_blocking_modals(page: Any, *, max_rounds: int = 15, settle_ms: int = 600) -> list[str]:
    """가로막는 모달을 모두 닫고, **닫은 모달의 텍스트를 반환한다**.

    텍스트를 버리지 않는 것이 중요하다. 거기에 실패 사유가 적혀 있다.
    호출부는 이 반환값을 로그로 남겨 조용한 실패를 막는다.
    """
    seen: list[str] = []
    for _ in range(max_rounds):
        info = peek_modal(page)
        if not info:
            break
        try:
            closed = page.evaluate(_DISMISS_ONE_JS)
        except Exception:
            break
        if not closed:
            break
        text = (info.get("text") or "").strip()
        if text:
            seen.append(text)
        try:
            page.wait_for_timeout(settle_ms)
        except Exception:
            pass
    return seen


def assert_no_modal(page: Any) -> str | None:
    """모달이 남아 있으면 그 텍스트를 돌려준다(클릭 전 확인용)."""
    info = peek_modal(page)
    return (info or {}).get("text") if info else None
