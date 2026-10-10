"""
감사 로그 모듈 — logs/audit.jsonl (append-only, JSONL)
승인/차단/판정 이력을 event_type 기준으로 구조화 기록
민감정보 마스킹 후 기록
"""

import json
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ai_orchestrator.core.logging_utils import mask_sensitive, truncate_large_text

_LOGS_DIR = Path(__file__).resolve().parents[2] / "logs"
_AUDIT_PATH = _LOGS_DIR / "audit.jsonl"

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
    # email candidate → task 승격 이벤트
    "CANDIDATE_TASK_CREATED",
    "CANDIDATE_TASK_DUPLICATE",
    "CANDIDATE_TASK_FAILED",
    # email task → approval 요청 이벤트
    "EMAIL_TASK_APPROVAL_REQUESTED",
    "EMAIL_TASK_APPROVAL_DUPLICATE",
    "EMAIL_TASK_APPROVAL_FAILED",
    # 카카오/범용 메시지 분류 이벤트
    "KAKAOWORK_MESSAGE_CLASSIFIED",
    "KAKAOTALK_CHANNEL_MESSAGE_CLASSIFIED",
    "MESSAGE_CANDIDATE_CREATED",
    "MESSAGE_CANDIDATE_SKIPPED",
    # 카카오워크 webhook 수신 이벤트
    "KAKAOWORK_MESSAGE_RECEIVED",
    "KAKAOWORK_MESSAGE_DUPLICATE",
    "KAKAOWORK_MESSAGE_FAILED",
    # 카카오워크 서명 검증 이벤트
    "KAKAOWORK_SIGNATURE_INVALID",
    "KAKAOWORK_SIGNATURE_VALID",
    # 카카오톡 채널 webhook 수신 이벤트
    "KAKAOTALK_CHANNEL_MESSAGE_RECEIVED",
    "KAKAOTALK_CHANNEL_MESSAGE_DUPLICATE",
    "KAKAOTALK_CHANNEL_MESSAGE_FAILED",
    # 카카오톡 채널 payload 검증 실패 이벤트
    "KAKAOTALK_CHANNEL_PAYLOAD_INVALID",
    # email task approval → execution 연결 이벤트
    "EMAIL_TASK_APPROVED",
    "EMAIL_TASK_REJECTED",
    "EMAIL_TASK_EXECUTION_READY",
    "EMAIL_TASK_EXECUTION_BLOCKED_POLICY",
    "EMAIL_TASK_EXECUTION_SKIPPED",
    "EMAIL_TASK_EXECUTION_STARTED",
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
    # 전역 경로를 테스트가 str 로 monkeypatch 하는 경우가 있어
    # 사용 시점에 Path(...) 로 감싼다 (Path/str 양쪽 다 안전).
    logs_dir = Path(_LOGS_DIR)
    audit_path = Path(_AUDIT_PATH)
    logs_dir.mkdir(parents=True, exist_ok=True)
    lg = logging.getLogger("orchestrator.audit")
    if not lg.handlers:
        fh = RotatingFileHandler(
            audit_path,
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
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "event_type": event_type,
        "task_id": task_id,
        "action_type": action_type,
        "actor": actor,
        "risk_level": risk_level,
        "note": truncate_large_text(note, max_len=300),
    }
    payload.update(extra_fields)
    payload = mask_sensitive(payload)

    lg = _get_logger()
    lr = lg.makeRecord(
        name=lg.name,
        level=logging.INFO,
        fn="",
        lno=0,
        msg="",
        args=(),
        exc_info=None,
    )
    lr._audit_payload = payload
    lg.handle(lr)
