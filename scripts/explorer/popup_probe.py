"""범용 팝업 수집·안전 닫기·네이티브 대화상자 기록 (사이트 무관).

기준서: docs/specs/2026-09-30_page_analysis_layer.md §3-2 (v4).

- `probe_popups(page)`: 화면의 **모든** 팝업을 읽기 전용으로 수집한다(role=dialog, aria-modal, 열린 <dialog>,
  이름에 modal/popup/layer 가 든 요소, 그리고 이름과 무관하게 화면을 크게 덮는 고정 위치 요소).
  맨 위(z-index가 높은 것)부터 정렬해 문구·버튼과 함께 돌려준다.
- `dismiss_popups_safely(page)`: 맨 위 팝업부터 **위험하지 않은 닫기 버튼만** 눌러 반복 처리한다.
  위험 버튼(결제·삭제 등)뿐인 팝업은 누르지 않고 문구와 함께 보고한다. 닫은 팝업의 문구는 항상 결과에 남긴다.
- `install_dialog_recorder(page)`: JS 네이티브 alert/confirm/prompt/beforeunload 를 기록하고 안전 기본값으로 처리한다
  (alert 는 수락, 나머지는 취소). 호출자가 명시적으로 설치해야만 동작한다.

기존 `scripts/browser/popup/popup_detector.py`(25곳에서 호출)는 수정하지 않는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from scripts.explorer import page_analysis

logger = logging.getLogger(__name__)

_MAX_TEXT = 200
_MIN_COVER = 0.25  # 이름 없는 오버레이를 팝업으로 볼 최소 화면 덮음 비율
_MIN_NAMED_COVER = 0.05  # 이름(modal/popup/layer)만 근거인 후보의 최소 덮음 비율 — 작은 플로팅 위젯 오탐 방지
_MIN_OVERLAY_Z = 10

# 브라우저 안에서 실행된다. DOM 을 읽기만 하고 바꾸지 않는다.
_PROBE_JS = r"""
({maxText, minCover, minNamedCover, minZ}) => {
  const vw = window.innerWidth || document.documentElement.clientWidth;
  const vh = window.innerHeight || document.documentElement.clientHeight;
  const named = '[role="dialog"],[role="alertdialog"],[aria-modal="true"],dialog[open],' +
      '[class*="modal" i],[class*="popup" i],[class*="layer" i],[id*="modal" i],[id*="popup" i]';
  const visible = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const zOf = (el) => {
    let z = 0;
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      const v = parseInt(getComputedStyle(n).zIndex, 10);
      if (!isNaN(v)) z = Math.max(z, v);
    }
    return z;
  };
  const fixedish = (el) => {
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      const p = getComputedStyle(n).position;
      if (p === 'fixed' || p === 'sticky') return true;
    }
    return false;
  };
  const cover = (el) => {
    const r = el.getBoundingClientRect();
    const w = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0));
    const h = Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0));
    return (w * h) / (vw * vh);
  };
  const pathOf = (el) => {
    const parts = [];
    for (let n = el; n && n.nodeType === 1 && n !== document.documentElement; n = n.parentElement) {
      const same = n.parentElement ? [...n.parentElement.children] : [n];
      parts.unshift(n.tagName.toLowerCase() + ':nth-child(' + (same.indexOf(n) + 1) + ')');
    }
    return 'html > ' + parts.join(' > ');
  };
  const candidates = new Set(document.querySelectorAll(named));
  for (const el of document.body ? document.body.querySelectorAll('*') : []) {
    if (candidates.has(el)) continue;
    if (fixedish(el) && zOf(el) >= minZ && cover(el) >= minCover) candidates.add(el);
  }
  let list = [...candidates].filter(visible);
  // 명시적 표식(role/aria-modal/열린 dialog)은 크기와 무관하게 팝업이다.
  // 이름(modal/popup/layer)만 근거인 후보는 고정 위치이면서 의미 있는 크기(화면 minNamedCover 이상)일 때만 인정한다.
  // (실제 네이버 메인의 92x40 '최상단으로 이동/홈 설정' 플로팅 위젯이 클래스명 layer 때문에 오탐된 사례)
  const explicit = '[role="dialog"],[role="alertdialog"],[aria-modal="true"],dialog[open]';
  list = list.filter((el) => el.matches(explicit) || (fixedish(el) && cover(el) >= minNamedCover));
  // 다른 후보 안에 든 자손은 제외(가장 바깥 것만 남긴다)
  list = list.filter((el) => !list.some((o) => o !== el && o.contains(el)));
  const out = list.map((el, i) => {
    const text = (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, maxText);
    const buttons = [...el.querySelectorAll('button,[role="button"],a,input[type="button"],input[type="submit"]')]
      .filter(visible)
      .map((b) => ({
        text: ((b.innerText || b.value || '')).replace(/\s+/g, ' ').trim().slice(0, 40),
        aria: b.getAttribute('aria-label') || '',
        id: b.id || '',
      }))
      .filter((b) => b.text || b.aria).slice(0, 8);
    const role = el.getAttribute('role') || (el.tagName === 'DIALOG' ? 'dialog' : (fixedish(el) ? 'overlay' : 'popup'));
    return {role, text, buttons, z: zOf(el), cover: Math.round(cover(el) * 100) / 100, visible: true, order: i, path: pathOf(el)};
  });
  // 정렬은 파이썬(probe_popups)에서 한 곳에서만 한다. DOM 순서는 같은 z 일 때의 판단용으로만 돌려준다.
  return out;
}
"""


def probe_popups(page: Any) -> list[dict[str, Any]]:
    """화면의 모든 팝업(맨 위부터). 읽기 전용."""
    args = {"maxText": _MAX_TEXT, "minCover": _MIN_COVER, "minNamedCover": _MIN_NAMED_COVER, "minZ": _MIN_OVERLAY_Z}
    found: list[dict[str, Any]] = []
    for idx, frame in enumerate(page.frames):
        try:
            items = frame.evaluate(_PROBE_JS, args)
        except Exception as exc:  # noqa: BLE001 - 접근 못 하는 프레임(교차 출처·분리됨)은 건너뛰고 나머지를 계속 본다
            logger.debug("프레임 %d 팝업 수집 건너뜀: %s", idx, type(exc).__name__)
            continue
        for item in items:
            item["frame"] = idx
            found.append(item)
    # 겹침 순서: z-index 큰 것 먼저, 같으면 DOM 에서 나중에 그려진 것(order 큰 것) 먼저
    found.sort(key=lambda d: (-d.get("z", 0), -d.get("order", 0), -d.get("cover", 0)))
    for item in found:
        item.pop("order", None)
    return found


# ── 안전 닫기 ────────────────────────────────────────────────────────────


@dataclass
class _Round:
    closed: list[dict[str, Any]] = field(default_factory=list)


def _snapshot_like(popups: list[dict[str, Any]]) -> dict[str, Any]:
    return {"url": "", "title": "", "frames": [{"idx": 0, "dialogs": popups}]}


def _press(page: Any, popup: dict[str, Any], plan: dict[str, Any]) -> str | None:
    """분석 결과에 따라 한 팝업을 닫는다. 어떤 방법을 썼는지 반환(못 닫으면 None).

    같은 이름의 버튼이 겹친 팝업마다 있을 수 있어, 페이지 전체가 아니라 **그 팝업 요소 안에서** 버튼을 찾는다.
    """
    root = page.locator(popup["path"]) if popup.get("path") else page
    close = plan.get("safe_close")
    if close:
        for finder in (
            lambda: root.get_by_role("button", name=close["label"], exact=True),
            lambda: root.get_by_text(close["label"], exact=True),
        ):
            try:
                finder().first.click(timeout=2000)
                return "button"
            except Exception as exc:  # noqa: BLE001 - 첫 방법이 안 되면 다음 방법(문구 기반)을 시도하고, 끝내 못 누르면 보고한다
                logger.debug("팝업 닫기 클릭 실패, 다음 방법: %s", type(exc).__name__)
        return None
    if plan.get("escape_ok"):
        page.keyboard.press("Escape")
        return "escape"
    return None


def dismiss_popups_safely(page: Any, *, max_rounds: int = 10) -> dict[str, Any]:
    """맨 위 팝업부터 안전한 닫기 버튼만 눌러 반복 처리. 위험 버튼뿐이면 누르지 않고 보고한다."""
    closed: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    for _ in range(max_rounds):
        plans = page_analysis.analyze_popups(_snapshot_like(probe_popups(page)))
        if not plans:
            remaining = []
            break
        top = plans[0]
        how = _press(page, top, top)
        if how is None:
            remaining = plans  # 눌러도 되는 방법이 없다 — 문구와 함께 보고
            break
        closed.append({"text": top["text"], "kind": top["kind"], "how": how})
        page.wait_for_timeout(150)
    else:
        remaining = page_analysis.analyze_popups(_snapshot_like(probe_popups(page)))
    if not remaining:
        remaining = page_analysis.analyze_popups(_snapshot_like(probe_popups(page)))
    return {"closed": closed, "remaining": remaining, "clean": not remaining}


# ── 네이티브 대화상자 ─────────────────────────────────────────────────────


@dataclass
class DialogRecorder:
    """설치된 페이지에서 일어난 JS 네이티브 대화상자 기록."""

    events: list[dict[str, Any]] = field(default_factory=list)

    def handle(self, dialog: Any) -> None:
        kind = str(dialog.type)
        message = str(dialog.message or "")[:_MAX_TEXT]
        if kind == "alert":
            dialog.accept()
            handled = "accept"
        else:  # confirm / prompt / beforeunload 는 취소가 안전 기본값
            dialog.dismiss()
            handled = "dismiss"
        self.events.append({"type": kind, "message": message, "handled": handled})


def install_dialog_recorder(page: Any) -> DialogRecorder:
    """alert 는 수락, confirm/prompt/beforeunload 는 취소하며 메시지를 기록한다. 명시적으로 설치해야 동작."""
    recorder = DialogRecorder()
    page.on("dialog", recorder.handle)
    return recorder
