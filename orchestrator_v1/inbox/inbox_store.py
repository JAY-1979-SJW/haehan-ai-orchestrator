"""
파일 기반 inbox 저장소 (JSONL)
경로: storage/inbox.jsonl
중복 방지: external_id + source_account 조합
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from orchestrator_v1.tasks.candidate_store import _load_all

_BASE_DIR = str(Path(__file__).resolve().parents[2])
_INBOX_PATH = Path(_BASE_DIR) / "storage" / "inbox.jsonl"


def _inbox_path() -> str | Path:
    return _INBOX_PATH




def _is_duplicate(external_id: str, source_account: str, path: str | Path) -> bool:
    for item in _load_all(path):
        if item.get("external_id") == external_id and item.get("source_account") == source_account:
            return True
    return False


def save_mail(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    *,
    external_id: str,
    sender: str,
    title: str,
    body_raw: str,
    received_at: str,
    source_account: str,
    body_summary: str | None = None,
    path: str | None = None,
) -> dict:
    """
    메일 1건을 inbox에 저장.
    중복이면 {"status": "skipped", ...} 반환.
    필수 필드 누락 시 ValueError 발생.
    """
    if not external_id:
        raise ValueError("external_id는 필수입니다")
    if not source_account:
        raise ValueError("source_account는 필수입니다")
    if not sender:
        raise ValueError("sender는 필수입니다")
    if not title:
        raise ValueError("title은 필수입니다")

    inbox_path = Path(path or _inbox_path())
    inbox_path.parent.mkdir(parents=True, exist_ok=True)

    if _is_duplicate(external_id, source_account, inbox_path):
        return {
            "status": "skipped",
            "reason": "duplicate",
            "external_id": external_id,
            "source_account": source_account,
        }

    entry = {
        "source_type": "email",
        "source_account": source_account,
        "external_id": external_id,
        "sender": sender,
        "title": title,
        "body_raw": body_raw,
        "body_summary": body_summary,
        "received_at": received_at,
        "saved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "new",
        "linked_task_id": None,
    }

    with inbox_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return {"status": "saved", "external_id": external_id, "source_account": source_account}


def save_message(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    *,
    source_type: str,
    external_id: str,
    source_account: str,
    sender: str,
    title: str,
    body_raw: str,
    received_at: str,
    metadata: dict | None = None,
    path: str | None = None,
) -> dict:
    """
    메시지 1건을 inbox에 저장 (source_type 파라미터로 다양한 소스 지원).
    save_mail()의 범용 버전 — 카카오워크/카카오톡채널 등에서 사용.
    중복이면 {"status": "skipped", ...} 반환.
    필수 필드 누락 시 ValueError 발생.
    """
    if not source_type:
        raise ValueError("source_type은 필수입니다")
    if not external_id:
        raise ValueError("external_id는 필수입니다")
    if not source_account:
        raise ValueError("source_account는 필수입니다")
    if not sender:
        raise ValueError("sender는 필수입니다")
    if not title:
        raise ValueError("title은 필수입니다")

    inbox_path = Path(path or _inbox_path())
    inbox_path.parent.mkdir(parents=True, exist_ok=True)

    if _is_duplicate(external_id, source_account, inbox_path):
        return {
            "status": "skipped",
            "reason": "duplicate",
            "external_id": external_id,
            "source_account": source_account,
        }

    entry: dict[str, object] = {
        "source_type": source_type,
        "source_account": source_account,
        "external_id": external_id,
        "sender": sender,
        "title": title,
        "body_raw": body_raw,
        "body_summary": None,
        "received_at": received_at,
        "saved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "new",
        "linked_task_id": None,
    }
    if metadata:
        entry["metadata"] = metadata

    with inbox_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return {"status": "saved", "external_id": external_id, "source_account": source_account}


def list_inbox(
    source_type: str | None = None,
    limit: int = 50,
    path: str | None = None,
) -> list[dict]:
    """inbox 목록 반환. source_type으로 필터링 가능."""
    inbox_path = path or _inbox_path()
    items = _load_all(inbox_path)
    if source_type:
        items = [i for i in items if i.get("source_type") == source_type]
    return items[-limit:]
