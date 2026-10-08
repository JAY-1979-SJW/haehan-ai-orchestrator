"""EUM 비정상 접근 감시 및 대응 핸들러.

기능:
  1. 비정상 접근 메시지 감지 (popup_classifier)
  2. 자동 대응: 재시도, 대기, 로그인 재수행
  3. 접근 차단 상태 추적
  4. 복구 전략 실행

사용:
    from scripts.eum.access_handler import handle_access_block, wait_for_recovery

    result = handle_access_block(page, category="access_blocked")
    if result["recovered"]:
        print("접근 복구됨")
    else:
        print("접근 불가능")
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.browser.popup.popup_classifier import Decision  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402
from scripts.common.op_log import log_op  # noqa: E402

log = get_logger(__name__)

# ── 설정 ──────────────────────────────────────────────────────────
RETRY_DELAYS = [5, 10, 30, 60, 180, 300]  # 초 단위: 5s, 10s, 30s, 1m, 3m, 5m
MAX_RETRIES = 3
RECOVERY_STATE_FILE = ROOT / "data" / "eum_access_recovery_state.json"


def is_access_blocked(decision: Decision) -> bool:
    """Decision이 접근 차단 상태인지 판단."""
    return decision["category"] in ("access_blocked", "bot_detected", "rate_limited")


def handle_access_block(
    page: Any,
    category: str,
    severity: str = "critical",
    target_button: str | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    """비정상 접근 메시지 대응.

    전략:
      1. 메시지 닫기 (확인 버튼 클릭)
      2. 잠시 대기
      3. 페이지 새로고침 또는 재로그인

    반환:
      {
        "recovered": bool,      # 복구 성공 여부
        "retry_count": int,     # 재시도 횟수
        "last_error": str,      # 마지막 오류
        "next_retry_time": int, # 다음 재시도 시간 (초)
      }
    """
    log.warning(f"[EUM] 비정상 접근 감지: {category} (심각도: {severity})")

    result: dict[str, Any] = {
        "recovered": False,
        "retry_count": retry_count,
        "last_error": "",
        "next_retry_time": 0,
    }

    # 1단계: 메시지 닫기
    if target_button:
        try:
            page.click(f"button:has-text('{target_button}')")
            log.info(f"[EUM] 메시지 닫음: '{target_button}'")
            time.sleep(2)
        except Exception as e:  # noqa: BLE001 - EUM 사이트 접근 복구 자동화 — 메시지창 닫기/복구 시도 실패는 무시하고 재시도 로직으로 넘어가거나 최종 실패를 result dict에 기록, 쓰기/삭제 동작 없음
            log.debug(f"[EUM] 메시지 닫기 실패: {e}")

    # 2단계: 대기
    if retry_count < len(RETRY_DELAYS):
        delay = RETRY_DELAYS[retry_count]
        log.info(f"[EUM] {delay}초 대기 후 재시도 ({retry_count + 1}/{len(RETRY_DELAYS)})")
        result["next_retry_time"] = delay
        time.sleep(delay)
    else:
        log.error("[EUM] 최대 재시도 횟수 초과")
        result["last_error"] = "max_retries_exceeded"
        log.critical("[EUM] 접근 불가능 상태 지속")
        return result

    # 3단계: 복구 시도
    try:
        # 페이지 새로고침 시도
        page.reload()
        log.info("[EUM] 페이지 새로고침 완료")

        # 차단 메시지 재확인
        try:
            error_msg = page.query_selector("text=비정상")
            if error_msg:
                # 여전히 차단 상태 → 재귀 호출
                log.warning("[EUM] 차단 메시지 재확인됨, 재시도")
                return handle_access_block(
                    page,
                    category=category,
                    severity=severity,
                    target_button=target_button,
                    retry_count=retry_count + 1,
                )
        except Exception:  # noqa: BLE001 - 메시지창 닫기 재시도 중 개별 실패는 무시하고 다음 재시도로 진행 — 읽기전용 접근복구
            pass

        result["recovered"] = True
        log.info("[EUM] 접근 복구 성공")

    except Exception as e:  # noqa: BLE001 - EUM 사이트 접근 복구 자동화 — 메시지창 닫기/복구 시도 실패는 무시하고 재시도 로직으로 넘어가거나 최종 실패를 result dict에 기록, 쓰기/삭제 동작 없음
        result["last_error"] = str(e)
        log.error(f"[EUM] 복구 실패: {e}")

        # 재시도
        if retry_count < MAX_RETRIES:
            return handle_access_block(
                page,
                category=category,
                severity=severity,
                target_button=target_button,
                retry_count=retry_count + 1,
            )

    # 로그 기록
    log_op(
        "eum_access_recovery",
        ok=result["recovered"],
        category=category,
        retries=retry_count,
        error=result["last_error"],
    )

    return result


def wait_for_recovery(minutes: int = 5) -> None:
    """접근 차단으로부터의 회복 대기.

    - 보통 5-10분 후 복구
    - IP 레벨 차단이면 더 오래 필요
    """
    log.warning(f"[EUM] {minutes}분 대기 (접근 차단 회복 대기)")
    time.sleep(minutes * 60)
    log.info("[EUM] 대기 완료, 재접근 시도")


def detect_and_handle(page: Any, decision: Decision) -> bool:
    """Decision을 기반으로 비정상 접근 자동 처리.

    반환:
      True: 복구 성공 또는 처리 불필요
      False: 복구 실패, 작업 중단 필요
    """
    if not is_access_blocked(decision):
        return True

    log.warning(f"[EUM] 비정상 접근 감지: {decision['category']}")

    result = handle_access_block(
        page,
        category=decision["category"],
        severity=decision["severity"],
        target_button=decision["target"],
    )

    if result["recovered"]:
        log.info("[EUM] 접근 복구됨, 작업 재개")
        return True
    else:
        log.error(f"[EUM] 접근 복구 불가: {result['last_error']}")
        return False
