"""
task 후보(candidate) 파일 기반 저장소 (JSONL)
경로: storage/candidates.jsonl
실제 task 생성 없음 — 후보 목록만 관리
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Optional

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES_PATH = os.path.join(_BASE_DIR, "storage", "candidates.jsonl")


def _candidates_path() -> str:
    return _CANDIDATES_PATH


def _make_item_id(external_id: str, source_account: str) -> str:
    raw = f"{external_id}:{source_account}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


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


def _is_duplicate(item_id: str, path: str) -> bool:
    return any(c.get("item_id") == item_id for c in _load_all(path))


def save_candidate(
    *,
    external_id: str,
    source_account: str,
    category: str,
    priority: str,
    needs_review: bool,
    candidate_task_type: Optional[str],
    classification_reason: str,
    path: Optional[str] = None,
) -> dict:
    """
    분류 결과를 candidate로 저장.
    동일 item_id가 이미 있으면 skip.
    """
    cand_path = path or _candidates_path()
    os.makedirs(os.path.dirname(cand_path), exist_ok=True)

    item_id = _make_item_id(external_id, source_account)

    if _is_duplicate(item_id, cand_path):
        return {"status": "skipped", "item_id": item_id}

    entry = {
        "item_id": item_id,
        "external_id": external_id,
        "source_account": source_account,
        "category": category,
        "priority": priority,
        "needs_review": needs_review,
        "candidate_task_type": candidate_task_type,
        "classification_reason": classification_reason,
        "classified_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "linked_task_id": None,
    }

    with open(cand_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return {"status": "saved", "item_id": item_id}


def get_candidate(item_id: str, path: Optional[str] = None) -> Optional[dict]:
    """item_id로 단건 조회. 없으면 None."""
    cand_path = path or _candidates_path()
    for c in _load_all(cand_path):
        if c.get("item_id") == item_id:
            return c
    return None


def set_linked_task_id(
    item_id: str,
    task_id: str,
    task_created_at: str,
    path: Optional[str] = None,
) -> bool:
    """
    candidate의 linked_task_id / task_created_at을 업데이트.
    JSONL 전체 재기록 방식 (파일 크기 작음 가정).
    해당 item_id가 없으면 False 반환.
    """
    cand_path = path or _candidates_path()
    items = _load_all(cand_path)
    updated = False
    for item in items:
        if item.get("item_id") == item_id:
            item["linked_task_id"] = task_id
            item["task_created_at"] = task_created_at
            updated = True
            break
    if updated:
        with open(cand_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return updated


def list_candidates(
    category: Optional[str] = None,
    needs_review: Optional[bool] = None,
    limit: int = 50,
    path: Optional[str] = None,
) -> list[dict]:
    """후보 목록 반환. category / needs_review 필터 가능."""
    cand_path = path or _candidates_path()
    items = _load_all(cand_path)
    if category:
        items = [i for i in items if i.get("category") == category]
    if needs_review is not None:
        items = [i for i in items if i.get("needs_review") == needs_review]
    return items[-limit:]
