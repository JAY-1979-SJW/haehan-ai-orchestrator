"""휴먼 행동 강화 — scripts.browser.page.human_input 확장.

추가 동작 (사람과 동일):
  - scroll_into_view + 짧은 응시 시간
  - mouse hover (selector 중심 + 작은 jitter)
  - 글자 간 delay 랜덤 (50~150ms)
  - 단어 사이 살짝 더 긴 지연
  - 가끔 backspace + 재입력 (오타 시뮬레이션, 옵션)
  - tab 또는 click으로 다음 필드 이동

scripts.browser.page.human_input.safe_human_input 은 그대로 유지 (단순/안정적 진입점).
여기는 회원가입처럼 더 자연스러워야 할 때 사용.
"""

from __future__ import annotations

import contextlib
import random
import time

from scripts.form.events import wait_field_ready, wait_value_settled
from scripts.browser.page.human_input import safe_human_input as _safe_basic  # noqa: F401
from scripts.common.logger import get_logger

log = get_logger(__name__)


# 기본 파라미터 (사람 평균 타이핑 90~110 WPM ≈ 100~120ms/char, 한국어는 더 느림)
_DEFAULT_CHAR_DELAY_MS = (50, 150)
_DEFAULT_WORD_PAUSE_MS = (80, 250)
_DEFAULT_FIELD_PAUSE_MS = (250, 700)
_DEFAULT_PRE_CLICK_PAUSE_MS = (400, 800)  # 클릭 후 첫 글자까지 응시 (인지 반응)
_THINKING_PAUSE_MS = (400, 1000)  # 사고 일시정지
_THINKING_PROB = 0.06  # 글자당 사고 일시정지 발생 확률 (~16글자당 1회)


def _rand_ms(rng: tuple[int, int]) -> float:
    return random.uniform(rng[0], rng[1]) / 1000.0


def _bezier_path(x0: float, y0: float, x1: float, y1: float, n: int = 12) -> list[tuple[float, float]]:
    """제어점 1개의 2차 베지어 곡선 — 마우스가 사람처럼 휘어 이동."""
    # 중간 제어점: 직선에서 수직 방향으로 약간 벗어남
    mx = (x0 + x1) / 2
    my = (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    # 수직 단위벡터
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    nx, ny = -dy / length, dx / length
    offset = random.uniform(-min(60, length * 0.2), min(60, length * 0.2))
    cx, cy = mx + nx * offset, my + ny * offset
    pts = []
    for i in range(1, n + 1):
        t = i / n
        # 2차 베지어: (1-t)^2 P0 + 2(1-t)t C + t^2 P1
        u = 1 - t
        x = u * u * x0 + 2 * u * t * cx + t * t * x1
        y = u * u * y0 + 2 * u * t * cy + t * t * y1
        pts.append((x, y))
    return pts


def _thinking_pause_if_due() -> bool:
    """확률적 사고 일시정지. 발생 여부 반환."""
    if random.random() < _THINKING_PROB:
        time.sleep(_rand_ms(_THINKING_PAUSE_MS))
        return True
    return False


def hover_and_scroll(page, selector: str) -> None:
    """필드를 viewport 안으로 + 마우스 호버 + 잠시 응시."""
    try:
        el = page.locator(selector).first
        with contextlib.suppress(Exception):  # 보조 동작, 실패해도 계속(2026-09-28 검토)
            el.scroll_into_view_if_needed(timeout=2500)
        try:
            box = el.bounding_box()
        except Exception:  # noqa: BLE001 - 사람처럼 마우스/타이핑 입력하는 공용 헬퍼 — 실패는 {ok: False, reason} 반환 또는 안전한 폴백(직선 이동 등), 결제·삭제 없음(2026-09-28 검토)
            box = None
        if box:
            cx = box["x"] + box["width"] / 2 + random.uniform(-3, 3)
            cy = box["y"] + box["height"] / 2 + random.uniform(-2, 2)
            # 베지어 곡선으로 이동 (직선이 아닌 사람 같은 휨)
            try:
                # 현재 마우스 위치는 알 수 없으므로 첫 호출 시 viewport 중앙에서 출발
                cur_x = getattr(page, "_last_mouse_x", None)
                cur_y = getattr(page, "_last_mouse_y", None)
                if cur_x is None or cur_y is None:
                    vp = page.viewport_size or {"width": 1280, "height": 800}
                    cur_x = vp["width"] / 2 + random.uniform(-100, 100)
                    cur_y = vp["height"] / 2 + random.uniform(-100, 100)
                pts = _bezier_path(cur_x, cur_y, cx, cy, n=random.randint(8, 16))
                for px, py in pts:
                    page.mouse.move(px, py)
                page._last_mouse_x = cx
                page._last_mouse_y = cy
            except Exception:  # noqa: BLE001 - 사람처럼 마우스/타이핑 입력하는 공용 헬퍼 — 실패는 {ok: False, reason} 반환 또는 안전한 폴백(직선 이동 등), 결제·삭제 없음(2026-09-28 검토)
                # 폴백: 직선 이동
                with contextlib.suppress(Exception):  # 보조 동작, 실패해도 계속(2026-09-28 검토)
                    page.mouse.move(cx, cy, steps=random.randint(6, 14))
        time.sleep(_rand_ms(_DEFAULT_PRE_CLICK_PAUSE_MS))
    except Exception as e:  # noqa: BLE001 - 사람처럼 마우스/타이핑 입력하는 공용 헬퍼 — 실패는 {ok: False, reason} 반환 또는 안전한 폴백(직선 이동 등), 결제·삭제 없음(2026-09-28 검토)
        log.debug("[human] hover_and_scroll 실패 sel=%s err=%s", selector, e)


def _type_chars(page, value: str, char_delay_ms: tuple[int, int], word_pause_ms: tuple[int, int], simulate_typo: bool) -> None:
    """value 를 한 글자씩 사람 리듬으로 입력(사고 일시정지·단어 쉼·선택적 오타)."""
    for i, ch in enumerate(value):
        # 사고 일시정지 — 글자 입력 전 (3글자 이후부터, 마지막 직전 제외)
        if 3 <= i < len(value) - 1:
            _thinking_pause_if_due()
        d = int(random.uniform(char_delay_ms[0], char_delay_ms[1]))
        page.keyboard.type(ch, delay=d)
        if ch in " -_@.":
            time.sleep(_rand_ms(word_pause_ms))
        if simulate_typo and i > 2 and random.random() < 0.02:
            wrong = chr(random.randint(97, 122))
            page.keyboard.type(wrong, delay=int(random.uniform(60, 120)))
            time.sleep(_rand_ms((180, 350)))
            page.keyboard.press("Backspace")


def human_type(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    page,
    selector: str,
    value: str,
    *,
    label: str = "필드",
    char_delay_ms: tuple[int, int] = _DEFAULT_CHAR_DELAY_MS,
    word_pause_ms: tuple[int, int] = _DEFAULT_WORD_PAUSE_MS,
    simulate_typo: bool = False,
    visible_timeout: int = 5000,
) -> dict:
    """사람처럼 한 글자씩 입력 — 랜덤 지연 + 스크롤/호버 + 검증.

    Returns:
        {ok, action, before, after, [reason]}
    """
    try:
        # 1) 필드 준비 — 이벤트 기반 (visible + enabled)
        if not wait_field_ready(page, selector, timeout_ms=visible_timeout):
            return {"ok": False, "action": "error", "reason": "field_not_ready"}
        hover_and_scroll(page, selector)
        el = page.locator(selector).first

        # 2) 현재 값
        current = ""
        with contextlib.suppress(Exception):  # 보조 동작, 실패해도 계속(2026-09-28 검토)
            current = el.input_value(timeout=1500) or ""

        if current == value:
            log.info("[human] %s 동일 값 — skip", label)
            return {"ok": True, "action": "skip", "before": current, "after": current}

        # 3) 기존 값 제거 — 이벤트 기반 검증
        if current:
            log.info("[human] %s 기존값(%d자) 제거 후 재입력", label, len(current))
            el.click(timeout=2000)
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            # 빈 값이 될 때까지 이벤트 대기 (blind sleep 없음)
            if not wait_value_settled(page, selector, "", timeout_ms=1500):
                with contextlib.suppress(Exception):  # 보조 동작, 실패해도 계속(2026-09-28 검토)
                    el.fill("", timeout=1500)
            action = "replaced"
        else:
            action = "empty"

        el.click(timeout=2000)
        # 클릭 직후 짧은 응시 (사람 패턴) — 이벤트로 대체 불가한 인지 시간
        time.sleep(_rand_ms(_DEFAULT_PRE_CLICK_PAUSE_MS))

        # 4) 한 글자씩 입력 (사람 타이핑 리듬)
        _type_chars(page, value, char_delay_ms, word_pause_ms, simulate_typo)

        # 5) 입력 정착 대기 — 이벤트 기반 (blind sleep 제거)
        settled = wait_value_settled(page, selector, value, timeout_ms=2500)

        # 6) 최종 검증
        final = ""
        with contextlib.suppress(Exception):  # 보조 동작, 실패해도 계속(2026-09-28 검토)
            final = el.input_value(timeout=1500) or ""

        if final != value or not settled:
            log.warning(
                "[human] %s 입력 검증 실패 (기대=%d자, 실제=%d자, settled=%s)", label, len(value), len(final), settled
            )
            return {"ok": False, "action": action, "before": current, "after": final, "reason": "value_mismatch"}

        log.info("[human] %s 입력 완료 (%s, %d자, 이벤트 정착)", label, action, len(value))
        return {"ok": True, "action": action, "before": current, "after": final}

    except Exception as e:  # noqa: BLE001 - 사람처럼 마우스/타이핑 입력하는 공용 헬퍼 — 실패는 {ok: False, reason} 반환 또는 안전한 폴백(직선 이동 등), 결제·삭제 없음(2026-09-28 검토)
        log.error("[human] %s 입력 실패: %s", label, e)
        return {"ok": False, "action": "error", "reason": str(e)[:120]}


def human_click(page, selector: str, *, label: str = "버튼") -> dict:
    """사람처럼 버튼 클릭 — hover + 클릭. 이벤트 기반 readiness."""
    try:
        if not wait_field_ready(page, selector, timeout_ms=5000):
            return {"ok": False, "reason": "button_not_ready"}
        hover_and_scroll(page, selector)
        el = page.locator(selector).first
        el.click(timeout=5000)
        log.info("[human] %s 클릭", label)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001 - 사람처럼 마우스/타이핑 입력하는 공용 헬퍼 — 실패는 {ok: False, reason} 반환 또는 안전한 폴백(직선 이동 등), 결제·삭제 없음(2026-09-28 검토)
        log.error("[human] %s 클릭 실패: %s", label, e)
        return {"ok": False, "reason": str(e)[:120]}


def human_check(page, selector: str, *, checked: bool = True, label: str = "체크박스") -> dict:
    """체크박스 토글 — 현재 상태 확인 후 필요 시만 클릭. 이벤트 기반 검증."""
    try:
        if not wait_field_ready(page, selector, timeout_ms=5000):
            return {"ok": False, "reason": "checkbox_not_ready"}
        hover_and_scroll(page, selector)
        el = page.locator(selector).first
        try:
            current = el.is_checked()
        except Exception:  # noqa: BLE001 - 사람처럼 마우스/타이핑 입력하는 공용 헬퍼 — 실패는 {ok: False, reason} 반환 또는 안전한 폴백(직선 이동 등), 결제·삭제 없음(2026-09-28 검토)
            current = None
        if current == checked:
            log.info("[human] %s 이미 %s — skip", label, "체크됨" if checked else "해제됨")
            return {"ok": True, "action": "skip", "before": current}
        el.click(timeout=3000)
        # 체크 상태 변경 이벤트 대기 (blind sleep 제거)
        with contextlib.suppress(Exception):  # 보조 동작, 실패해도 계속(2026-09-28 검토)
            page.wait_for_function(
                """([sel, want]) => {
                    const el = document.querySelector(sel);
                    return el && el.checked === want;
                }""",
                arg=[selector, checked],
                timeout=2000,
            )
        try:
            after = el.is_checked()
        except Exception:  # noqa: BLE001 - 사람처럼 마우스/타이핑 입력하는 공용 헬퍼 — 실패는 {ok: False, reason} 반환 또는 안전한 폴백(직선 이동 등), 결제·삭제 없음(2026-09-28 검토)
            after = None
        if after == checked:
            log.info("[human] %s 토글 완료 → %s", label, checked)
            return {"ok": True, "action": "toggled", "before": current, "after": after}
        log.warning("[human] %s 토글 검증 실패 (기대=%s 실제=%s)", label, checked, after)
        return {"ok": False, "reason": "toggle_mismatch", "before": current, "after": after}
    except Exception as e:  # noqa: BLE001 - 사람처럼 마우스/타이핑 입력하는 공용 헬퍼 — 실패는 {ok: False, reason} 반환 또는 안전한 폴백(직선 이동 등), 결제·삭제 없음(2026-09-28 검토)
        log.error("[human] %s 토글 실패: %s", label, e)
        return {"ok": False, "reason": str(e)[:120]}


def move_to_next(page, current_selector: str | None = None, next_selector: str | None = None) -> None:
    """다음 필드로 이동 — Tab 또는 click."""
    if next_selector:
        hover_and_scroll(page, next_selector)
        return
    try:
        page.keyboard.press("Tab")
        time.sleep(_rand_ms((150, 350)))
    except Exception:  # noqa: BLE001 - 스크롤/좌표 조회 등 보조 동작 — 실패해도 다음 단계로 계속(2026-09-28 검토)
        pass
