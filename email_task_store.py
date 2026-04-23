"""
이메일 candidate에서 승격된 task 파일 기반 저장소 (JSONL)
경로: storage/email_tasks.jsonl
자동 실행 없음 — status=pending 상태로만 저장
기존 in-memory task_store / executor와 분리된 독립 저장소
"""
import json
import os
from datetime import datetime, timezone
from typing import Optional

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_EMAIL_TASKS_PATH = os.path.join(_BASE_DIR, "storage", "email_tasks.jsonl")


def _tasks_path() -> str:
    return _EMAIL_TASKS_PATH


def _load_all(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return items


def save_email_task(
    *,
    task_id: str,
    source_item_id: str,
    category: str,
    priority: str,
    task_type: Optional[str],
    title: str,
    risk_level: str,
    path: Optional[str] = None,
) -> dict:
    """
    email candidate에서 승격된 task를 저장.
    status=pending, 자동 실행 없음.
    """
    tasks_path = path or _tasks_path()
    os.makedirs(os.path.dirname(tasks_path), exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
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

    with open(tasks_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


def get_email_task(task_id: str, path: Optional[str] = None) -> Optional[dict]:
    """task_id로 단건 조회."""
    tasks_path = path or _tasks_path()
    for t in _load_all(tasks_path):
        if t.get("task_id") == task_id:
            return t
    return None


def list_email_tasks(limit: int = 50, path: Optional[str] = None) -> list[dict]:
    tasks_path = path or _tasks_path()
    return _load_all(tasks_path)[-limit:]


def update_email_task_status(task_id: str, status: str, *, path: Optional[str] = None) -> bool:
    """email task의 status 필드 단독 업데이트 (JSONL 전체 재기록)."""
    tasks_path = path or _tasks_path()
    tasks = _load_all(tasks_path)
    updated = False
    for t in tasks:
        if t.get("task_id") == task_id:
            t["status"] = status
            updated = True
            break
    if updated:
        with open(tasks_path, "w", encoding="utf-8") as f:
            for t in tasks:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return updated


def update_email_task_approval(
    task_id: str,
    *,
    approval_token_id: str,
    approval_requested_at: str,
    approval_status: str,
    path: Optional[str] = None,
) -> bool:
    """
    email task의 approval 필드 업데이트 (JSONL 전체 재기록).
    approval_token_id / approval_requested_at / approval_status 기록.
    """
    tasks_path = path or _tasks_path()
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
        with open(tasks_path, "w", encoding="utf-8") as f:
            for t in tasks:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return updated
