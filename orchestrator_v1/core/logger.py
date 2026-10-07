"""
공통 로거 모듈
- 운영 로그  : logs/orchestrator.log    (INFO+, 5MB×5)
- 에러 로그  : logs/orchestrator.error.log (ERROR+, 2MB×3)
- 감사 로그  : logs/audit.jsonl         (audit_logger.py가 담당)
- 실행 이력  : storage/execution_history.jsonl (whitelist_executor가 담당)
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGS_DIR = Path(__file__).parent / "logs"

# 포맷: 구조화 필드 포함. extra dict로 event_type/task_id/action_type/actor 전달
_FMT = (
    "%(asctime)s [%(levelname)-8s] %(name)s "
    "event=%(event_type)s task=%(task_id)s action=%(action_type)s actor=%(actor)s "
    "| %(message)s"
)
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_EXTRA_DEFAULTS = {
    "event_type": "-",
    "task_id": "-",
    "action_type": "-",
    "actor": "-",
}


class _DefaultExtraFormatter(logging.Formatter):
    """extra 필드가 없을 때 기본값 '-' 채움"""

    def format(self, record: logging.LogRecord) -> str:
        for k, v in _EXTRA_DEFAULTS.items():
            if not hasattr(record, k):
                setattr(record, k, v)
        return super().format(record)


def _build_formatter() -> _DefaultExtraFormatter:
    return _DefaultExtraFormatter(_FMT, datefmt=_DATEFMT)


def get_logger(name: str) -> logging.Logger:
    """모듈 어디서든 get_logger('모듈명') 으로 운영/에러 로거 획득"""
    # 모듈 전역 LOGS_DIR 를 테스트가 str 로 monkeypatch 하는 경우가 있어
    # 사용 시점에 Path(...) 로 감싼다 (Path/str 양쪽 다 안전).
    logs_dir = Path(LOGS_DIR)
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"orchestrator.{name}")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = _build_formatter()

    # 운영 로그: INFO+ (5MB × 5)
    fh = RotatingFileHandler(
        logs_dir / "orchestrator.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    # 에러 로그: ERROR+ (2MB × 3)
    eh = RotatingFileHandler(
        logs_dir / "orchestrator.error.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    eh.setLevel(logging.ERROR)
    eh.setFormatter(fmt)

    # 콘솔: DEBUG+
    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(eh)
    logger.addHandler(sh)
    logger.propagate = False
    return logger


def log_event(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    logger: logging.Logger,
    level: int,
    message: str,
    event_type: str = "-",
    task_id: str = "-",
    action_type: str = "-",
    actor: str = "-",
) -> None:
    """구조화 필드를 extra로 전달하는 헬퍼"""
    logger.log(
        level,
        message,
        extra={
            "event_type": event_type,
            "task_id": task_id or "-",
            "action_type": action_type or "-",
            "actor": actor or "-",
        },
    )
