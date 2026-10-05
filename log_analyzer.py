"""
로그 기반 운영 분석 모듈 (5단계)
audit.jsonl + execution_history.jsonl 읽어 집계 및 운영 요약 생성.
앱 런타임 유료 AI 호출 없음(2026-09-24 OpenAI 삭제) — 항상 deterministic mock 요약 반환.
"""

import json
import time
from collections import Counter
from pathlib import Path

from logger import get_logger

_BASE_DIR = Path(__file__).resolve().parent
_AUDIT_PATH = _BASE_DIR / "logs" / "audit.jsonl"
_HISTORY_PATH = _BASE_DIR / "storage" / "execution_history.jsonl"
_CACHE_PATH = _BASE_DIR / "storage" / "dashboard_cache.json"

log = get_logger("log_analyzer")


def _read_jsonl(path: str | Path, limit: int = 0) -> list:
    """JSONL 파일 읽기. 파싱 실패 라인은 skip + WARN."""
    if not Path(path).exists():
        return []
    try:
        with Path(path).open(encoding="utf-8") as f:
            raw_lines = f.readlines()
    except Exception as e:  # noqa: BLE001 - 로그 분석 도구 -- 로그 파일 읽기 실패 시 빈 리스트 반환, 캐시 쓰기 실패는 경고만(분석 결과에는 영향 없음)
        log.warning("Failed to read %s: %s", path, e)
        return []

    if limit and len(raw_lines) > limit:
        raw_lines = raw_lines[-limit:]

    results = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            log.warning("JSONL parse failed, skipping: %s", line[:80])
    return results


def summarize_recent_activity(limit: int = 100) -> dict:
    """최근 작업 흐름 요약 — execution_history 기반."""
    history = _read_jsonl(_HISTORY_PATH, limit=limit)
    audit = _read_jsonl(_AUDIT_PATH, limit=limit * 3)

    executed = sum(1 for h in history if h.get("execution_status") == "EXECUTED")
    preview = sum(1 for h in history if h.get("execution_status") == "PREVIEW_ONLY")
    blocked = sum(1 for h in history if h.get("execution_status") == "BLOCKED")
    failed = sum(1 for a in audit if a.get("event_type") == "EXECUTION_FAILED")

    action_counter: Counter = Counter(h.get("action_type", "unknown") for h in history if h.get("action_type"))

    reason_counter: Counter = Counter(
        h["note"] for h in history if h.get("execution_status") == "BLOCKED" and h.get("note")
    )

    recent_tasks = []
    for h in reversed(history[-10:]):
        recent_tasks.append(
            {
                "task_id": h.get("task_id"),
                "action_type": h.get("action_type"),
                "target": h.get("target"),
                "status": h.get("execution_status"),
                "timestamp": h.get("timestamp"),
                "risk_level": h.get("risk_level", ""),
            }
        )

    return {
        "total_tasks": len(history),
        "executed_count": executed,
        "preview_count": preview,
        "blocked_count": blocked,
        "failed_count": failed,
        "top_action_types": action_counter.most_common(5),
        "top_blocked_reasons": reason_counter.most_common(5),
        "recent_tasks": recent_tasks,
    }


def summarize_failures(limit: int = 100) -> dict:
    """최근 에러/차단 이벤트 요약 — audit 기반."""
    audit = _read_jsonl(_AUDIT_PATH, limit=limit)

    failed_events = [a for a in audit if a.get("event_type") in {"EXECUTION_FAILED", "EXECUTION_BLOCKED"}]

    recent_errors = []
    for e in reversed(failed_events[-20:]):
        recent_errors.append(
            {
                "timestamp": e.get("timestamp"),
                "task_id": e.get("task_id"),
                "action_type": e.get("action_type"),
                "event_type": e.get("event_type"),
                "note": e.get("note", ""),
                "risk_level": e.get("risk_level", ""),
            }
        )

    return {
        "total_failures": len(failed_events),
        "recent_errors": recent_errors,
    }


def summarize_pending_approvals() -> dict:
    """감사 로그에서 승인 대기 중인 task_id 분석 (ISSUED - GRANTED/REJECTED)."""
    audit = _read_jsonl(_AUDIT_PATH)

    issued: dict = {}
    granted_or_rejected: set = set()

    for a in audit:
        task_id = a.get("task_id")
        if not task_id:
            continue
        if a.get("event_type") == "APPROVAL_ISSUED":
            if task_id not in issued:
                issued[task_id] = a
        elif a.get("event_type") in {"APPROVAL_GRANTED", "APPROVAL_REJECTED"}:
            granted_or_rejected.add(task_id)

    pending_task_ids = [tid for tid in issued if tid not in granted_or_rejected]

    pending_list = []
    for tid in pending_task_ids:
        event = issued[tid]
        pending_list.append(
            {
                "task_id": tid,
                "action_type": event.get("action_type"),
                "risk_level": event.get("risk_level"),
                "timestamp": event.get("timestamp"),
                "actor": event.get("actor"),
            }
        )

    return {
        "pending_count": len(pending_list),
        "pending_approvals": pending_list,
    }


def generate_ai_ops_summary(summary_dict: dict) -> str:
    """운영 요약 생성 — 유료 AI 미사용(2026-09-24 OpenAI 삭제), 항상 deterministic mock 반환.

    맞춤 운영 요약이 필요하면 Claude Code가 summary_dict를 직접 읽고 작성한다.
    """
    return _mock_summary(summary_dict)


def _mock_summary(s: dict) -> str:
    total = s.get("total_tasks", 0)
    blocked = s.get("blocked_count", 0)
    pending = s.get("pending_approvals", 0)
    executed = s.get("executed_count", 0)
    failed = s.get("failed_count", 0)
    preview = s.get("preview_count", 0)

    if total == 0:
        return "[운영 요약 - Mock] 아직 처리된 작업이 없습니다. 시나리오를 실행하여 데이터를 생성하세요."

    block_rate = int(blocked / total * 100) if total else 0
    parts = [
        f"[운영 요약 - Mock] 최근 총 {total}개의 작업이 처리되었습니다.",
        f"실행 완료 {executed}건, 프리뷰 {preview}건, 차단 {blocked}건({block_rate}%), 실패 {failed}건.",
    ]
    if pending > 0:
        parts.append(f"현재 승인 대기 {pending}건이 있습니다 — 확인이 필요합니다.")
    if failed > 0:
        parts.append(f"실패 이벤트 {failed}건 감지됨 — 에러 로그 확인을 권장합니다.")
    top_blocked = s.get("top_blocked_reasons", [])
    if top_blocked:
        parts.append(f"주요 차단 원인: '{top_blocked[0][0]}'.")
    return " ".join(parts)


def save_cache(summary: dict) -> None:
    """마지막 요약을 dashboard_cache.json에 저장."""
    try:
        cache = {
            "cached_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "summary": summary,
        }
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _CACHE_PATH.open("w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa: BLE001 - 로그 분석 도구 -- 로그 파일 읽기 실패 시 빈 리스트 반환, 캐시 쓰기 실패는 경고만(분석 결과에는 영향 없음)
        log.warning("Cache write failed: %s", e)
