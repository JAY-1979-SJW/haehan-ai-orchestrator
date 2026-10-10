"""실행 리밋 (rate/timeout) + execution_history.jsonl 관리.

low 위험 인라인 실행에만 적용. medium/high/critical 기존 정책은 변경하지 않음.
"""

import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime

from .config import (
    EXEC_RATE_LIMIT_ACTION_MAX,
    EXEC_RATE_LIMIT_USER_MAX,
    EXEC_RATE_LIMIT_WINDOW_SEC,
    EXEC_TIMEOUT_SEC,
)
from .config import (
    EXECUTION_HISTORY_PATH as _HIST_PATH,
)
from .models import TaskRequest

logger = logging.getLogger(__name__)

# 차단 사유 상수 (router/executor 공용)
BLOCK_RATE_ACTION = "rate_limited_action"
BLOCK_RATE_USER = "rate_limited_user"
BLOCK_TIMEOUT = "execution_timeout"
# 신규 승인형 실행 정책 차단 사유
BLOCK_TASK_COOLDOWN = "task_cooldown"
BLOCK_USER_5MIN = "rate_limited_user_5min"
BLOCK_NIGHT = "night_blocked"

# 신규 제한 파라미터 (기본값 고정. 필요 시 후속 단계에서 config.py 로 이관)
TASK_COOLDOWN_SEC = 60  # 동일 task 1분 내 1회
USER_5MIN_WINDOW_SEC = 300  # 5분 창
USER_5MIN_MAX = 5  # 5분 내 5회
NIGHT_START_HOUR = 0  # KST 00시
NIGHT_END_HOUR = 6  # KST 06시 (end exclusive)
KST_OFFSET_HOURS = 9  # 서버 UTC → KST


def _now() -> datetime:
    return datetime.now(UTC)


def record_execution(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    task_id: str,
    action_type: str,
    requested_by: str,
    status: str,
    risk_level: str = "",
    duration_ms: int = 0,
    note: str = "",
) -> None:
    """execution_history.jsonl 에 한 줄 append."""
    entry = {
        "timestamp": _now().isoformat(),
        "task_id": task_id,
        "action_type": action_type,
        "requested_by": requested_by,
        "risk_level": risk_level,
        "status": status,
        "duration_ms": duration_ms,
        "note": note,
    }
    try:
        _HIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _HIST_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.error("실행 이력 기록 실패: %s | entry=%s", e, entry)


def _read_recent(window_sec: int) -> list[dict]:
    """최근 window_sec 초 이내 기록만 반환. 파일 없으면 빈 목록."""
    if not _HIST_PATH.exists():
        return []
    threshold = _now().timestamp() - window_sec
    out: list[dict] = []
    try:
        with _HIST_PATH.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    ts = datetime.fromisoformat(entry.get("timestamp", "")).timestamp()
                except (TypeError, ValueError):
                    continue
                if ts >= threshold:
                    out.append(entry)
    except OSError as e:
        logger.error("실행 이력 읽기 실패: %s", e)
    return out


def _is_countable(entry: dict) -> bool:
    """rate 카운트에 포함할 엔트리(정상 실행 + timeout). BLOCKED: 는 제외."""
    status = entry.get("status", "")
    return not status.startswith("BLOCKED:")


def check_rate_limits(req: TaskRequest) -> tuple[bool, str]:
    """실행 직전 체크. (True, '') 허용 / (False, reason) 차단."""
    recent = _read_recent(EXEC_RATE_LIMIT_WINDOW_SEC)
    action_count = 0
    user_count = 0
    for e in recent:
        if not _is_countable(e):
            continue
        if e.get("action_type") == req.action_type:
            action_count += 1
        if e.get("requested_by") == req.requested_by:
            user_count += 1
    if action_count >= EXEC_RATE_LIMIT_ACTION_MAX:
        return False, BLOCK_RATE_ACTION
    if user_count >= EXEC_RATE_LIMIT_USER_MAX:
        return False, BLOCK_RATE_USER
    return True, ""


def run_with_timeout(func: Callable[[], str], timeout_sec: int) -> str:
    """func 를 timeout_sec 초 내 실행. 초과 시 TimeoutError raise.

    Windows 호환을 위해 threading 기반. 초과된 워커 스레드는 daemon 으로
    프로세스 종료 시 함께 소멸. 제어권은 즉시 호출자에 반환.
    """
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="exec-to") as pool:
        future = pool.submit(func)
        try:
            return future.result(timeout=timeout_sec)
        except FutureTimeout as exc:
            # 스레드풀은 with-block 종료 시 shutdown 되며 남은 future 를
            # 취소할 수 없지만 daemon 으로 돌아 프로세스 종료 시 정리됨.
            raise TimeoutError(f"execution exceeded {timeout_sec}s") from exc


# 편의: 윈도우/카운트/타임아웃 설정 조회
def current_limits() -> dict:
    return {
        "window_sec": EXEC_RATE_LIMIT_WINDOW_SEC,
        "action_max": EXEC_RATE_LIMIT_ACTION_MAX,
        "user_max": EXEC_RATE_LIMIT_USER_MAX,
        "timeout_sec": EXEC_TIMEOUT_SEC,
        "task_cooldown_sec": TASK_COOLDOWN_SEC,
        "user_5min_window_sec": USER_5MIN_WINDOW_SEC,
        "user_5min_max": USER_5MIN_MAX,
        "night_start_hour_kst": NIGHT_START_HOUR,
        "night_end_hour_kst": NIGHT_END_HOUR,
    }


# ── 신규 승인형 실행 제한 ─────────────────────────────────────────────
def check_task_cooldown(task_id: str, window_sec: int = TASK_COOLDOWN_SEC) -> tuple[bool, str]:
    """동일 task_id 가 window_sec 내에 이미 실행된 적 있으면 차단."""
    recent = _read_recent(window_sec)
    for e in recent:
        if not _is_countable(e):
            continue
        if e.get("task_id") == task_id:
            return False, BLOCK_TASK_COOLDOWN
    return True, ""


def check_user_5min_window(
    requested_by: str,
    window_sec: int = USER_5MIN_WINDOW_SEC,
    max_count: int = USER_5MIN_MAX,
) -> tuple[bool, str]:
    """동일 사용자가 5분 내 max_count 회 초과 실행 시 차단."""
    recent = _read_recent(window_sec)
    count = 0
    for e in recent:
        if not _is_countable(e):
            continue
        if e.get("requested_by") == requested_by:
            count += 1
    if count >= max_count:
        return False, BLOCK_USER_5MIN
    return True, ""


def _is_night_kst(
    dt_utc: datetime | None = None, start_hour: int = NIGHT_START_HOUR, end_hour: int = NIGHT_END_HOUR
) -> bool:
    """KST 기준 야간 시간대 여부. end_hour 는 exclusive."""
    base = dt_utc or _now()
    # UTC → KST 오프셋
    kst_hour = (base.hour + KST_OFFSET_HOURS) % 24
    if start_hour <= end_hour:
        return start_hour <= kst_hour < end_hour
    # wrap (예: 22~6) 처리
    return kst_hour >= start_hour or kst_hour < end_hour


def check_night_block(now_utc: datetime | None = None) -> tuple[bool, str]:
    """KST 00:00~06:00 사이면 실행 차단."""
    if _is_night_kst(now_utc):
        return False, BLOCK_NIGHT
    return True, ""


def check_execution_policy(req: TaskRequest) -> tuple[bool, str]:
    """승인형 실제 실행 전 3종 정책(task cooldown / user 5min / night) 검사.

    기존 check_rate_limits 와 결합해 쓰며, 어느 하나라도 막히면 차단.
    """
    ok, reason = check_night_block()
    if not ok:
        return ok, reason
    ok, reason = check_task_cooldown(req.task_id)
    if not ok:
        return ok, reason
    ok, reason = check_user_5min_window(req.requested_by)
    if not ok:
        return ok, reason
    return True, ""
