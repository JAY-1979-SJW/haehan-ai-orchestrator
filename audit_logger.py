"""
감사 로그 모듈 — logs/audit.jsonl (append-only, JSONL)
승인/차단/판정 이력을 event_type 기준으로 구조화 기록
민감정보 마스킹 후 기록
"""
import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler

from logging_utils import mask_sensitive, truncate_large_text

_LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
_AUDIT_PATH = os.path.join(_LOGS_DIR, "audit.jsonl")

VALID_EVENT_TYPES = {
    "TASK_RECEIVED",
    "RISK_ASSESSED",
    "PLAN_CREATED",
    "APPROVAL_ISSUED",
    "APPROVAL_GRANTED",
    "APPROVAL_REJECTED",
    "EXECUTION_ALLOWED",
    "EXECUTION_BLOCKED",
    "EXECUTION_PREVIEW",
    "EXECUTION_COMPLETED",
    "EXECUTION_FAILED",
}

_logger: logging.Logger | None = None


class _JsonLineFormatter(logging.Formatter):
    """레코드를 JSON 한 줄로 직렬화"""
    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "_audit_payload", {})
        return json.dumps(payload, ensure_ascii=False)


def _get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    os.makedirs(_LOGS_DIR, exist_ok=True)
    lg = logging.getLogger("orchestrator.audit")
    if not lg.handlers:
        fh = RotatingFileHandler(
            _AUDIT_PATH,
            maxBytes=10 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8",
        )
        fh.setFormatter(_JsonLineFormatter())
        lg.addHandler(fh)
        lg.setLevel(logging.INFO)
        lg.propagate = False
    _logger = lg
    return _logger


def record(
    event_type: str,
    task_id: str | None = None,
    action_type: str | None = None,
    actor: str = "system",
    risk_level: str | None = None,
    note: str = "",
    **extra_fields,
) -> None:
    """
    감사 이벤트 기록.
    write 직전 mask_sensitive 적용.
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid audit event_type: '{event_type}'. Must be one of {sorted(VALID_EVENT_TYPES)}")

    payload = {
        "timestamp":   time.strftime("%Y-%m-%dT%H:%M:%S"),
        "event_type":  event_type,
        "task_id":     task_id,
        "action_type": action_type,
        "actor":       actor,
        "risk_level":  risk_level,
        "note":        truncate_large_text(note, max_len=300),
    }
    payload.update(extra_fields)
    payload = mask_sensitive(payload)

    lg = _get_logger()
    lr = lg.makeRecord(
        name=lg.name,
        level=logging.INFO,
        fn="", lno=0, msg="", args=(),
        exc_info=None,
    )
    lr._audit_payload = payload
    lg.handle(lr)
