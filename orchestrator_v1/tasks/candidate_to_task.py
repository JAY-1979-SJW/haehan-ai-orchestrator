"""
candidate → task 승격 모듈
- 명시적 API 호출로만 실행됨 (자동 실행 없음)
- 동일 candidate 중복 승격 방지
- 생성된 task는 status=pending, 자동 실행 없음
"""

import hashlib
from datetime import UTC, datetime

from orchestrator_v1.core import audit_logger
from orchestrator_v1.core.logger import get_logger
from orchestrator_v1.tasks import candidate_store, email_task_store

log = get_logger("candidate_to_task")

# 이메일 파생 task의 risk_level — 보수적으로 medium 고정
# (executor 파이프라인에 진입하지 않으므로 실질적 실행 위험 없음)
_DEFAULT_RISK_LEVEL = "medium"

# category별 위험도 보정 (ops만 high)
_RISK_OVERRIDE: dict[str, str] = {
    "operations": "high",
}


def _make_task_id(item_id: str) -> str:
    h = hashlib.sha256(item_id.encode()).hexdigest()[:12]
    return f"etask-{h}"


def promote(
    item_id: str,
    candidate_path: str | None = None,
    task_path: str | None = None,
) -> dict:
    """
    candidate item_id를 task로 승격.

    반환:
      {"status": "created", "task_id": ..., "item_id": ...}
      {"status": "duplicate", "task_id": ..., "item_id": ...}
      {"status": "not_found", "item_id": ...}
      {"status": "no_task_type", "item_id": ...}
    """
    # ── candidate 조회 ────────────────────────────────────────────
    candidate = candidate_store.get_candidate(item_id, path=candidate_path)
    if candidate is None:
        log.warning("candidate not found: item_id=%s", item_id)
        audit_logger.record(
            event_type="CANDIDATE_TASK_FAILED",
            task_id=None,
            action_type="promote_candidate",
            actor="candidate_to_task",
            note=f"candidate not found: item_id={item_id}",
        )
        return {"status": "not_found", "item_id": item_id}

    # ── 이미 승격된 candidate 차단 ────────────────────────────────
    existing_task_id = candidate.get("linked_task_id")
    if existing_task_id:
        log.info("candidate already promoted: item_id=%s task_id=%s", item_id, existing_task_id)
        audit_logger.record(
            event_type="CANDIDATE_TASK_DUPLICATE",
            task_id=existing_task_id,
            action_type="promote_candidate",
            actor="candidate_to_task",
            note=f"duplicate promote attempt: item_id={item_id}",
        )
        return {"status": "duplicate", "task_id": existing_task_id, "item_id": item_id}

    # ── task_type 없는 경우 차단 ──────────────────────────────────
    task_type = candidate.get("candidate_task_type")
    if not task_type:
        log.warning("no task_type on candidate: item_id=%s", item_id)
        audit_logger.record(
            event_type="CANDIDATE_TASK_FAILED",
            task_id=None,
            action_type="promote_candidate",
            actor="candidate_to_task",
            note=f"candidate has no task_type: item_id={item_id} category={candidate.get('category')}",
        )
        return {"status": "no_task_type", "item_id": item_id}

    # ── task_id 생성 ──────────────────────────────────────────────
    task_id = _make_task_id(item_id)
    category = candidate.get("category", "general")
    risk_level = _RISK_OVERRIDE.get(category, _DEFAULT_RISK_LEVEL)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")

    # ── email_tasks.jsonl에 저장 ──────────────────────────────────
    email_task_store.save_email_task(
        task_id=task_id,
        source_item_id=item_id,
        category=category,
        priority=candidate.get("priority", "medium"),
        task_type=task_type,
        title=f"[{category}] {task_type} — {candidate.get('external_id', '')[:40]}",
        risk_level=risk_level,
        path=task_path,
    )

    # ── candidate에 linked_task_id 기록 ──────────────────────────
    candidate_store.set_linked_task_id(
        item_id=item_id,
        task_id=task_id,
        task_created_at=now,
        path=candidate_path,
    )

    log.info("candidate promoted to task: item_id=%s task_id=%s", item_id, task_id)
    audit_logger.record(
        event_type="CANDIDATE_TASK_CREATED",
        task_id=task_id,
        action_type="promote_candidate",
        actor="candidate_to_task",
        risk_level=risk_level,
        note=f"item_id={item_id} category={category} task_type={task_type}",
    )

    return {
        "status": "created",
        "task_id": task_id,
        "item_id": item_id,
        "category": category,
        "priority": candidate.get("priority", "medium"),
        "task_type": task_type,
        "risk_level": risk_level,
    }
