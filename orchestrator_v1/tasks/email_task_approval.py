"""
email task → approval request 연결 모듈
승인 요청 생성만 수행. 자동 실행 없음.
storage/email_approval_tokens.json (파일 기반, JSON dict)
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from orchestrator_v1.core import audit_logger
from orchestrator_v1.core.logger import get_logger
from orchestrator_v1.tasks import email_task_store

log = get_logger("email_task_approval")

_BASE_DIR = str(Path(__file__).resolve().parents[2])
_DEFAULT_TOKEN_PATH = str(Path(_BASE_DIR) / "storage" / "email_approval_tokens.json")


def _load_tokens(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.open(encoding="utf-8").read())
    except Exception:  # noqa: BLE001 - 승인 토큰 저장 파일 로드 실패 시 빈 dict 반환 - approve/reject/get_approval_for_task는 조회 실패를 'not_found'로 처리(자동승인 아님), request_approval도 자동 실행 없이 pending 상태만 기록하므로 예외가 승인 우회로 이어지지 않음
        return {}


def _save_tokens(tokens: dict, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        f.write(json.dumps(tokens, indent=2, ensure_ascii=False))


def _active_token_for_task(task_id: str, tokens: dict) -> dict | None:
    """task_id에 대해 활성(pending) 토큰 반환. 없으면 None."""
    for entry in tokens.values():
        if entry.get("task_id") == task_id and entry.get("status") == "pending":
            return entry
    return None


def request_approval(
    task_id: str,
    *,
    token_path: str | None = None,
    task_path: str | None = None,
    actor: str = "system",
) -> dict:
    """
    email task에 대한 승인 요청 생성.
    중복 활성 approval이 있으면 duplicate 반환.
    자동 실행 없음 — approval_status=pending으로만 기록.
    """
    tp = token_path or _DEFAULT_TOKEN_PATH

    # 1. task 존재 확인
    task = email_task_store.get_email_task(task_id, path=task_path)
    if task is None:
        audit_logger.record(
            "EMAIL_TASK_APPROVAL_FAILED",
            task_id=task_id,
            actor=actor,
            note="task not found",
        )
        return {"status": "not_found", "task_id": task_id}

    # 2. 중복 활성 approval 확인
    tokens = _load_tokens(tp)
    existing = _active_token_for_task(task_id, tokens)
    if existing:
        audit_logger.record(
            "EMAIL_TASK_APPROVAL_DUPLICATE",
            task_id=task_id,
            actor=actor,
            note=f"duplicate: active token={existing['token_id'][:6]}***",
            item_id=task.get("source_item_id"),
        )
        return {
            "status": "duplicate",
            "task_id": task_id,
            "token_id": existing["token_id"],
            "approval_status": existing["status"],
        }

    # 3. approval token 생성
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    token_id = str(uuid.uuid4())
    entry = {
        "token_id": token_id,
        "task_id": task_id,
        "source": "email_task",
        "status": "pending",
        "created_at": now,
        "item_id": task.get("source_item_id"),
    }
    tokens[token_id] = entry
    _save_tokens(tokens, tp)

    # 4. email task approval 필드 업데이트
    email_task_store.update_email_task_approval(
        task_id=task_id,
        approval_token_id=token_id,
        approval_requested_at=now,
        approval_status="pending",
        path=task_path,
    )

    # 5. 감사 로그
    audit_logger.record(
        "EMAIL_TASK_APPROVAL_REQUESTED",
        task_id=task_id,
        actor=actor,
        risk_level=task.get("risk_level"),
        note=f"approval request created, token={token_id[:6]}***",
        item_id=task.get("source_item_id"),
    )

    log.info("approval requested task_id=%s token=%s", task_id, token_id[:6] + "***")

    return {
        "status": "created",
        "task_id": task_id,
        "token_id": token_id,
        "approval_status": "pending",
        "created_at": now,
    }


def _decide(token_id: str, status: str, actor: str, token_path: str | None) -> dict:
    """pending 상태의 approval token 을 status(approved|rejected)로 바꾼다(approve/reject 공통)."""
    tp = token_path or _DEFAULT_TOKEN_PATH
    tokens = _load_tokens(tp)
    entry = tokens.get(token_id)
    if not entry:
        return {"status": "not_found", "token_id": token_id}
    if entry["status"] != "pending":
        return {"status": "already_processed", "token_id": token_id, "current_status": entry["status"]}
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    entry["status"] = status
    entry[f"{status}_by"] = actor
    entry[f"{status}_at"] = now
    _save_tokens(tokens, tp)
    return {"status": status, "token_id": token_id, "task_id": entry["task_id"]}


def approve(token_id: str, approved_by: str, *, token_path: str | None = None) -> dict:
    """approval token을 approved 상태로 변경. pending 상태일 때만 처리."""
    return _decide(token_id, "approved", approved_by, token_path)


def reject(token_id: str, rejected_by: str, *, token_path: str | None = None) -> dict:
    """approval token을 rejected 상태로 변경. pending 상태일 때만 처리."""
    return _decide(token_id, "rejected", rejected_by, token_path)


def get_approval_for_task(task_id: str, *, token_path: str | None = None) -> dict | None:
    """task_id에 대한 approval token 조회. 복수인 경우 최신 우선."""
    tp = token_path or _DEFAULT_TOKEN_PATH
    tokens = _load_tokens(tp)
    matching = [e for e in tokens.values() if e.get("task_id") == task_id]
    if not matching:
        return None
    return sorted(matching, key=lambda x: x.get("created_at", ""), reverse=True)[0]
