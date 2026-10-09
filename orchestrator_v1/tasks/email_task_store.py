"""
이메일 candidate에서 승격된 task 파일 기반 저장소 (JSONL)
경로: storage/email_tasks.jsonl
자동 실행 없음 — status=pending 상태로만 저장
기존 in-memory task_store / executor와 분리된 독립 저장소
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from orchestrator_v1.tasks.candidate_store import _load_all

_BASE_DIR = str(Path(__file__).resolve().parents[2])
_EMAIL_TASKS_PATH = Path(_BASE_DIR) / "storage" / "email_tasks.jsonl"


def _tasks_path() -> str | Path:
    return _EMAIL_TASKS_PATH




def save_email_task(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    *,
    task_id: str,
    source_item_id: str,
    category: str,
    priority: str,
    task_type: str | None,
    title: str,
    risk_level: str,
    path: str | None = None,
) -> dict:
    """
    email candidate에서 승격된 task를 저장.
    status=pending, 자동 실행 없음.
    """
    tasks_path = Path(path or _tasks_path())
    tasks_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    entry = {
        "task_id": task_id,
        "source": "email_candidate",
        "source_item_id": source_item_id,
        "category": category,
        "priority": priority,
        "task_type": task_type,
        "title": title,
        "status": "pending",
        "risk_level": risk_level,
        "created_at": now,
        "linked_candidate_id": source_item_id,
    }

    with tasks_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


def get_email_task(task_id: str, path: str | None = None) -> dict | None:
    """task_id로 단건 조회."""
    tasks_path = path or _tasks_path()
    for t in _load_all(tasks_path):
        if t.get("task_id") == task_id:
            return t
    return None


def list_email_tasks(limit: int = 50, path: str | None = None) -> list[dict]:
    tasks_path = path or _tasks_path()
    return _load_all(tasks_path)[-limit:]


def update_email_task_status(task_id: str, status: str, *, path: str | None = None) -> bool:
    """email task의 status 필드 단독 업데이트 (JSONL 전체 재기록)."""
    tasks_path = Path(path or _tasks_path())
    tasks = _load_all(tasks_path)
    updated = False
    for t in tasks:
        if t.get("task_id") == task_id:
            t["status"] = status
            updated = True
            break
    if updated:
        with tasks_path.open("w", encoding="utf-8") as f:
            for t in tasks:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return updated


def update_email_task_approval(
    task_id: str,
    *,
    approval_token_id: str,
    approval_requested_at: str,
    approval_status: str,
    path: str | None = None,
) -> bool:
    """
    email task의 approval 필드 업데이트 (JSONL 전체 재기록).
    approval_token_id / approval_requested_at / approval_status 기록.
    """
    tasks_path = Path(path or _tasks_path())
    tasks = _load_all(tasks_path)
    updated = False
    for t in tasks:
        if t.get("task_id") == task_id:
            t["approval_token_id"] = approval_token_id
            t["approval_requested_at"] = approval_requested_at
            t["approval_status"] = approval_status
            updated = True
            break
    if updated:
        with tasks_path.open("w", encoding="utf-8") as f:
            for t in tasks:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return updated
