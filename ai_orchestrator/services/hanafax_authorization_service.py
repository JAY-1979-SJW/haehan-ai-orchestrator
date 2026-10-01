"""L6 서비스 — 하나팩스 발송 승인서 만들기·승인·취소·정지 (API 라우터가 호출한다).

기준서: docs/specs/2026-10-02_hanafax_auto_send.md
검증·해시 계산은 여기서 하고, 저장은 `fax_authorization_store`, 판정은 `fax_send_policy` 가 맡는다.
승인서는 한 번 승인하면 수정할 수 없다(범위를 바꾸려면 새로 만든다).
"""

from __future__ import annotations

import re
import threading
from datetime import UTC, datetime
from typing import Any

from ai_orchestrator.connectors import hanafax_auto_sender as adapter
from ai_orchestrator.gates import fax_send_policy as policy
from ai_orchestrator.persistence import fax_authorization_store as store
from ai_orchestrator.workflows import scheduled_job_actions as actions

MAX_RECIPIENTS = 500
MAX_PER_RUN_CAP = 100
MAX_PER_DAY_CAP = 300
MAX_TOTAL_CAP = 5000
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _clean_recipients(raw: Any) -> list[dict[str, str]]:
    """번호 형식을 검증하고 숫자만 남겨 중복을 제거한다. 하나라도 잘못되면 거부(조용히 빼지 않는다)."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("수신자 목록이 비어 있습니다")
    if len(raw) > MAX_RECIPIENTS:
        raise ValueError(f"수신자는 최대 {MAX_RECIPIENTS}명입니다")
    seen: set[str] = set()
    cleaned: list[dict[str, str]] = []
    for item in raw:
        number = policy.normalize_number(item.get("fax", "") if isinstance(item, dict) else "")
        if not policy.is_valid_number(number):
            raise ValueError(f"팩스번호 형식이 올바르지 않습니다: {policy.mask_number(number)}")
        if number in seen:
            continue
        seen.add(number)
        cleaned.append({"fax": number, "name": str(item.get("name", "")).strip()[:50]})
    return cleaned


def _limit(value: Any, label: str, cap: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label}은(는) 숫자여야 합니다") from None
    if not 1 <= number <= cap:
        raise ValueError(f"{label}은(는) 1~{cap} 사이여야 합니다")
    return number


def _hhmm(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not _HHMM.match(text):
        raise ValueError(f"{label}은(는) HH:MM 형식이어야 합니다")
    return text


def create(payload: dict[str, Any], *, user: str) -> dict[str, Any]:
    """승인 대기 승인서를 만든다. 문서는 허용 형식의 실제 파일이어야 하고, 내용 해시가 범위에 고정된다."""
    name = str(payload.get("name", "")).strip()
    subject = str(payload.get("subject", "")).strip()
    if not name or not subject:
        raise ValueError("이름과 제목은 필수입니다")
    document_ref = str(payload.get("document_ref", "")).strip()
    error = adapter.validate_document(document_ref) if document_ref else "문서 경로가 필요합니다"
    if error:
        raise ValueError(error)
    start, end = (
        _hhmm(payload.get("allowed_start", "09:00"), "허용 시작 시각"),
        _hhmm(payload.get("allowed_end", "18:00"), "허용 종료 시각"),
    )
    if start >= end:
        raise ValueError("허용 시작 시각이 종료 시각보다 빨라야 합니다")
    recipients = _clean_recipients(payload.get("recipients"))
    document_hash = adapter.file_sha256(document_ref)
    return store.create_authorization(
        store.NewAuthorization(
            name=name[:80],
            recipients=recipients,
            subject=subject[:80],
            document_hash=document_hash,
            document_ref=document_ref,
            scope_hash=policy.scope_hash(recipients, subject, document_hash),
            max_per_run=_limit(payload.get("max_per_run", 10), "1회 최대 건수", MAX_PER_RUN_CAP),
            max_per_day=_limit(payload.get("max_per_day", 50), "1일 최대 건수", MAX_PER_DAY_CAP),
            max_total=_limit(payload.get("max_total", len(recipients)), "총 최대 건수", MAX_TOTAL_CAP),
            allowed_start=start,
            allowed_end=end,
            valid_from=payload.get("valid_from") or None,
            valid_until=payload.get("valid_until") or None,
            created_by=user,
        )
    )


def preview(auth_id: str) -> dict[str, Any]:
    """승인 전 미리보기 — 사람이 보고 승인한다. 수신번호는 승인 대상이므로 전체를 보여 준다."""
    row = store.get_authorization(auth_id)
    if row is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    return {
        **row,
        "recipient_count": len(row["recipients"]),
        "document_name": re.split(r"[\\/]", row["document_ref"])[-1],
        "document_matches": _document_matches(row),
    }


def _document_matches(row: dict[str, Any]) -> bool:
    try:
        return (
            not adapter.validate_document(row["document_ref"])
            and adapter.file_sha256(row["document_ref"]) == row["document_hash"]
        )
    except OSError:
        return False


def approve(auth_id: str, *, user: str, live: bool) -> dict[str, Any]:
    """승인한다. 승인 순간에도 문서가 생성 때와 같은지 확인한다."""
    row = store.get_authorization(auth_id)
    if row is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    if not _document_matches(row):
        raise ValueError("문서가 승인서를 만든 뒤 바뀌었거나 없습니다 — 새 승인서를 만드세요")
    return store.approve(auth_id, user=user, live=live)


def revoke(auth_id: str, *, user: str) -> dict[str, Any]:
    return store.revoke(auth_id, user=user)


def set_kill_switch(on: bool, *, user: str) -> dict[str, Any]:
    store.set_kill_switch(on, user=user)
    return {"kill_switch": store.kill_switch_on()}


def send_log(auth_id: str) -> list[dict[str, Any]]:
    """발송 이력 — 수신번호는 마스킹해서 돌려준다."""
    return [{**r, "fax_digits": policy.mask_number(r["fax_digits"])} for r in store.list_send_log(auth_id)]


def add_opt_out(number: str, *, reason: str, user: str) -> str:
    digits = policy.normalize_number(number)
    if not policy.is_valid_number(digits):
        raise ValueError("팩스번호 형식이 올바르지 않습니다")
    store.add_opt_out(digits, reason=reason, user=user)
    return policy.mask_number(digits)


# ── 지금 발송 (승인된 승인서만) ────────────────────────────────────────────────
# 팩스 1건이 수십 초 걸리므로 백그라운드 스레드로 돌리고, 화면은 상태·이력을 조회한다. 같은 승인서의 동시 실행은 막는다.
_run_lock = threading.Lock()
_running: set[str] = set()
_last_run: dict[str, dict[str, str]] = {}


def _run_job(auth_id: str) -> None:
    try:
        message = actions.get_action("hanafax_send").run({"authorization_id": auth_id})  # type: ignore[union-attr]
        outcome = {"status": "done", "message": message}
    except Exception as exc:  # noqa: BLE001 - 실패 사유를 화면에 보여 주기 위해 기록한다(발송 재시도는 하지 않는다)
        outcome = {"status": "failed", "message": str(exc)[:300] or type(exc).__name__}
    with _run_lock:
        _last_run[auth_id] = {**outcome, "finished_at": datetime.now(UTC).isoformat(timespec="seconds")}
        _running.discard(auth_id)


def run_now(auth_id: str) -> dict[str, Any]:
    """승인된 승인서를 지금 한 번 실행한다. 승인되지 않았거나 취소됐으면 거부한다(발송 전 승인 필수)."""
    row = store.get_authorization(auth_id)
    if row is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    if not row["approved"]:
        raise ValueError("승인되지 않은 승인서는 발송할 수 없습니다 — 미리보기를 확인하고 먼저 승인하세요")
    if row["revoked"]:
        raise ValueError("취소된 승인서입니다")
    with _run_lock:
        if auth_id in _running:
            raise ValueError("이미 발송 중입니다")
        _running.add(auth_id)
        _last_run.pop(auth_id, None)
    threading.Thread(target=_run_job, args=(auth_id,), daemon=True, name=f"fax-run-{auth_id[:8]}").start()
    return run_status(auth_id)


def run_status(auth_id: str) -> dict[str, Any]:
    with _run_lock:
        running = auth_id in _running
        last = dict(_last_run.get(auth_id, {}))
    return {"running": running, "last": last or None}
