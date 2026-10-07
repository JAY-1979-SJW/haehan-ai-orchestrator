"""사람처럼 입력 — 모든 사이트 로그인의 공통 입력 헬퍼.

봇 감지 회피용. naver/auth.py 의 _safe_human_input 을 추출.

핵심 동작:
  1. 현재 입력값 확인
  2. 같은 값이면 skip
  3. 다른 값이면 Ctrl+A → Delete → 빈 상태 확인 (fill 폴백)
  4. 한 글자씩 keyboard.type(delay)
  5. 입력 후 값 검증
"""

from __future__ import annotations

import contextlib
import time

from scripts.common.logger import get_logger

_log = get_logger(__name__)


def _click_field(el, *, label: str, timeout: int = 3000) -> None:
    """Click an input field, with a forced click fallback for flaky CDP hit tests."""
    try:
        el.click(timeout=timeout)
        return
    except Exception as first_error:  # noqa: BLE001 - 폼 입력 범용 헬퍼(재시도/force클릭 포함) - 최종 실패시 원래 예외를 그대로 raise 하거나 ok:False,reason 반환, 값 검증까지 수행
        _log.warning("[human-input] %s 일반 클릭 실패 — force 클릭 재시도: %s", label, str(first_error)[:120])
        try:
            el.click(timeout=timeout, force=True)
            return
        except Exception:  # noqa: BLE001 - 폼 입력 범용 헬퍼(재시도/force클릭 포함) - 최종 실패시 원래 예외를 그대로 raise 하거나 ok:False,reason 반환, 값 검증까지 수행
            raise first_error


def safe_human_input(  # noqa: PLR0913 - 공개 시그니처(키워드 전용 옵션 4개) — 기존 호출자 호환 유지
    page,
    selector: str,
    value: str,
    *,
    label: str = "필드",
    delay_ms: int = 80,
    visible_timeout: int = 5000,
    click_timeout_ms: int = 3000,
) -> dict:
    """사람처럼 한 글자씩 입력 + 검증.

    Args:
        page: Playwright Page
        selector: CSS/XPath
        value: 입력할 값
        label: 로그용 이름 (예: "ID", "PW")
        delay_ms: 글자 간 지연
        visible_timeout: 필드가 visible 상태가 될 때까지 최대 대기 ms
        click_timeout_ms: 입력 칸 클릭 대기 ms(기본 3000). 느린 PC 에서 네이버 로그인 폼이 2초를 넘겨 시간 초과된 적이 있어
            네이버는 8000 을 넘긴다.

    Returns:
        dict{ok, action: "skip"|"empty"|"replaced"|"error",
             before, after, reason?}
    """
    try:
        el = page.locator(selector).first
        try:
            el.wait_for(state="visible", timeout=visible_timeout)
        except Exception:  # 네이버 로그인 폼은 보안 스크립트가 붙는 동안 wait_for 가 시간 초과되지만 실제로는 보이는 경우가 있다 — 보이면 진행, 안 보이면 원래 예외
            if not el.is_visible():
                raise

        # 1. 현재 값
        current = ""
        # 폼 입력 범용 헬퍼 - 현재값 조회 실패는 빈 문자열로 폴백, 값 검증은 뒤에서 별도 수행
        with contextlib.suppress(Exception):
            current = el.input_value(timeout=1500) or ""

        # 2. 동일 → skip
        if current == value:
            _log.info("[human-input] %s 동일 값 — skip", label)
            return {"ok": True, "action": "skip", "before": current, "after": current}

        # 3. 기존 값 제거
        if current:
            _log.info("[human-input] %s 다른 값 존재(%d자) — 삭제 후 재입력", label, len(current))
            _click_field(el, label=label, timeout=click_timeout_ms)
            time.sleep(0.3)
            page.keyboard.press("Control+a")
            time.sleep(0.15)
            page.keyboard.press("Delete")
            time.sleep(0.3)
            try:
                if el.input_value(timeout=1000) or "":
                    el.fill("", timeout=1500)
            except Exception:  # noqa: BLE001 - 폼 입력 범용 헬퍼(재시도/force클릭 포함) - 최종 실패시 원래 예외를 그대로 raise 하거나 ok:False,reason 반환, 값 검증까지 수행
                pass
            action = "replaced"
        else:
            action = "empty"

        # 4. 한 글자씩 입력
        _click_field(el, label=label, timeout=click_timeout_ms)
        time.sleep(0.4)
        for ch in value:
            page.keyboard.type(ch, delay=delay_ms)
        time.sleep(0.3)

        # 5. 검증
        final = ""
        # 폼 입력 범용 헬퍼 - 검증값 조회 실패는 빈 문자열로 폴백, 아래에서 불일치로 처리됨
        with contextlib.suppress(Exception):
            final = el.input_value(timeout=1500) or ""

        if final != value:
            _log.warning(
                "[human-input] %s 입력 검증 실패 (기대=%d자, 실제=%d자)",
                label,
                len(value),
                len(final),
            )
            return {
                "ok": False,
                "action": action,
                "before": current,
                "after": final,
                "reason": "value_mismatch",
            }

        _log.info("[human-input] %s 입력 완료 (%s, %d자)", label, action, len(value))
        return {"ok": True, "action": action, "before": current, "after": final}

    except Exception as e:  # noqa: BLE001 - 폼 입력 범용 헬퍼(재시도/force클릭 포함) - 최종 실패시 원래 예외를 그대로 raise 하거나 ok:False,reason 반환, 값 검증까지 수행
        _log.error("[human-input] %s 입력 실패: %s", label, e)
        return {"ok": False, "action": "error", "reason": str(e)[:120]}


def find_selector(page, candidates: list[str]) -> str | None:
    """selector 후보 목록에서 실제로 visible 한 첫 selector 반환."""
    for sel in candidates:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return sel
        except Exception:  # noqa: BLE001 - 폼 입력 범용 헬퍼(재시도/force클릭 포함) - 최종 실패시 원래 예외를 그대로 raise 하거나 ok:False,reason 반환, 값 검증까지 수행
            pass
    return None
