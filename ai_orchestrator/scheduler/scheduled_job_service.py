"""L6 — 사용자 예약 작업 서비스: 반복 계산, 생성·수정 검증, 실행 시각이 된 작업 실행.

기준서: docs/specs/2026-10-01_user_scheduled_jobs.md
승인: 발행·전송처럼 `USER_DELEGATED` 등급인 작업은 예약 시각이 되면 실행하지 않고 "승인 대기" 회차만 만든다. 사용자가 30분 안에
앱에서 승인해야 그 회차가 실행된다(회차마다 승인). `USER_DIRECT`·`BLOCKED` 는 예약 자체를 거부한다.
반복: once{at} / daily{time} / weekly{days,time} / interval{minutes}. 매일·매주 시각은 PC 로컬 시간대로 해석하고 UTC 로 저장한다.
"""

from __future__ import annotations

import re
import threading
from datetime import UTC, datetime, time, timedelta
from typing import Any

from ai_orchestrator.contracts.action_risk_policy import GRADE_AUTO_ALLOWED, GRADE_USER_DELEGATED, classify_action
from ai_orchestrator.scheduler import scheduled_job_store as store
from ai_orchestrator.services import scheduled_job_actions as actions

GRACE = timedelta(minutes=10)  # 예정 시각보다 이만큼 넘게 늦으면 실행하지 않고 "놓침" 처리
APPROVAL_TTL = timedelta(minutes=30)  # 승인 대기 회차가 유효한 시간(gates/approval 토큰 TTL 과 같다)
AWAITING = "awaiting_approval"
MIN_INTERVAL_MINUTES = 5
MAX_INTERVAL_MINUTES = 7 * 24 * 60
_RUN_LOCK = threading.Lock()  # 브라우저를 공유하므로 작업은 한 번에 하나씩
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


# ── 반복 계산 (순수) ─────────────────────────────────────────────────────


def _parse_hhmm(value: Any) -> tuple[int, int]:
    m = _HHMM.match(str(value or ""))
    if not m:
        raise ValueError("시각은 HH:MM 형식이어야 합니다")
    return int(m.group(1)), int(m.group(2))


def _parse_at(value: Any) -> datetime:
    try:
        at = datetime.fromisoformat(str(value))
    except ValueError as e:
        raise ValueError("실행 일시 형식이 올바르지 않습니다") from e
    return (at if at.tzinfo else at.astimezone()).astimezone(UTC)  # 시간대가 없으면 PC 로컬로 본다


def validate_recurrence(rec: Any) -> dict[str, Any]:
    """반복 설정을 검증하고 정규화한다. 잘못되면 ValueError."""
    if not isinstance(rec, dict):
        raise ValueError("반복 설정이 올바르지 않습니다")
    kind = rec.get("kind")
    if kind == "once":
        return {"kind": "once", "at": store.iso(_parse_at(rec.get("at")))}
    if kind == "daily":
        h, m = _parse_hhmm(rec.get("time"))
        return {"kind": "daily", "time": f"{h:02d}:{m:02d}"}
    if kind == "weekly":
        h, m = _parse_hhmm(rec.get("time"))
        raw = rec.get("days")
        if not isinstance(raw, list) or not raw or not all(isinstance(d, int) and 0 <= d <= 6 for d in raw):
            raise ValueError("요일은 0(월)~6(일) 숫자 목록이어야 합니다")
        return {"kind": "weekly", "days": sorted(set(raw)), "time": f"{h:02d}:{m:02d}"}
    if kind == "interval":
        minutes = rec.get("minutes")
        if not isinstance(minutes, int) or isinstance(minutes, bool):
            raise ValueError("간격(분)은 숫자여야 합니다")
        if not MIN_INTERVAL_MINUTES <= minutes <= MAX_INTERVAL_MINUTES:
            raise ValueError(f"간격은 {MIN_INTERVAL_MINUTES}분 이상 {MAX_INTERVAL_MINUTES}분 이하여야 합니다")
        return {"kind": "interval", "minutes": minutes}
    raise ValueError("반복 방식은 once / daily / weekly / interval 중 하나여야 합니다")


def _next_local(after: datetime, hhmm: str, days: list[int] | None) -> datetime | None:
    h, m = _parse_hhmm(hhmm)
    local_after = after.astimezone()
    for add in range(8):
        day = (local_after + timedelta(days=add)).date()
        if days is not None and day.weekday() not in days:
            continue
        candidate = datetime.combine(day, time(h, m)).astimezone()  # 시간대 없는 값은 PC 로컬로 해석된다
        if candidate > after:
            return candidate.astimezone(UTC)
    return None


def next_run(rec: dict[str, Any], after: datetime) -> datetime | None:
    """`after` 보다 뒤인 다음 실행 시각(UTC). 더 없으면 None."""
    kind = rec["kind"]
    if kind == "once":
        at = datetime.fromisoformat(rec["at"])
        return at if at > after else None
    if kind == "daily":
        return _next_local(after, rec["time"], None)
    if kind == "weekly":
        return _next_local(after, rec["time"], rec["days"])
    return after + timedelta(minutes=rec["minutes"])


# ── 생성·수정 ────────────────────────────────────────────────────────────


def _validated_action(action: str, params: Any) -> tuple[actions.ActionSpec, dict[str, Any]]:
    spec = actions.get_action(action)
    if spec is None:
        raise ValueError(f"예약할 수 없는 작업입니다: {action}")
    if classify_action(spec.risk_action) not in (GRADE_AUTO_ALLOWED, GRADE_USER_DELEGATED):
        raise ValueError("사용자가 직접 해야 하거나 허용되지 않는 작업은 예약할 수 없습니다")
    if not isinstance(params, dict):
        raise ValueError("설정값이 올바르지 않습니다")
    return spec, spec.validate(params)


def _validated_name(name: Any) -> str:
    text = str(name or "").strip()
    if not text or len(text) > 80:
        raise ValueError("이름은 1~80자여야 합니다")
    return text


def create(
    *, name: Any, action: str, params: Any, recurrence: Any, created_by: str, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    _, clean_params = _validated_action(action, params)
    rec = validate_recurrence(recurrence)
    first = next_run(rec, now)
    if first is None:
        raise ValueError("실행 일시가 이미 지났습니다")
    return store.create_job(
        name=_validated_name(name),
        action=action,
        params=clean_params,
        recurrence=rec,
        next_run_at=store.iso(first),
        created_by=created_by,
    )


def update(job_id: str, *, name: Any, params: Any, recurrence: Any, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    job = store.get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    _, clean_params = _validated_action(job["action"], params)
    rec = validate_recurrence(recurrence)
    fields: dict[str, Any] = {"name": _validated_name(name), "params": clean_params, "recurrence": rec}
    _cancel_awaiting(job_id, "예약 내용이 바뀌어 승인 대기를 취소했습니다")  # 사용자가 본 내용과 실행 내용이 달라지지 않게
    if job["status"] == "active":
        first = next_run(rec, now)
        if first is None:
            raise ValueError("실행 일시가 이미 지났습니다")
        fields["next_run_at"] = store.iso(first)
    return store.update_job(job_id, **fields)  # type: ignore[return-value]


def pause(job_id: str) -> dict[str, Any]:
    job = store.update_job(job_id, status="paused", next_run_at=None)
    if job is None:
        raise KeyError(job_id)
    return job


def resume(job_id: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    job = store.get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    first = next_run(job["recurrence"], now)  # 멈춰 있던 동안의 회차는 건너뛰고 다음 회차부터
    if first is None:
        raise ValueError("다시 시작할 다음 실행 시각이 없습니다 (이미 지난 한 번 실행 작업)")
    return store.update_job(job_id, status="active", next_run_at=store.iso(first))  # type: ignore[return-value]


# ── 실행 ────────────────────────────────────────────────────────────────


def _needs_approval(job: dict[str, Any]) -> bool:
    spec = actions.get_action(job["action"])
    return spec is not None and classify_action(spec.risk_action) == GRADE_USER_DELEGATED


def _execute(job: dict[str, Any], run: dict[str, Any], *, approved: bool = False) -> dict[str, Any]:
    status, message = "ok", ""
    with _RUN_LOCK:
        try:
            spec = actions.get_action(job["action"])
            if spec is None:
                raise ValueError(f"허용 목록에 없는 작업: {job['action']}")
            grade = classify_action(spec.risk_action)  # 실행 시점에도 다시 판정한다
            if grade == GRADE_USER_DELEGATED and not approved:
                status, message = "skipped", "승인 없이는 실행하지 않습니다"
            elif grade not in (GRADE_AUTO_ALLOWED, GRADE_USER_DELEGATED):
                status, message = "skipped", "예약으로 실행할 수 없는 작업이라 건너뜀"
            else:
                if spec.needs_browser:
                    actions.ensure_cdp()
                message = spec.run(spec.validate(job["params"]))
        except Exception as e:  # noqa: BLE001 - 작업 실패는 회차 기록(failed)으로 남기고 다음 작업을 계속한다
            status, message = "failed", str(e)[:300] or type(e).__name__
    finished = store.iso(datetime.now(UTC))
    store.finish_run(run["id"], status, message, finished)
    store.update_job(job["id"], last_run_at=finished, last_status=status, last_message=message[:300])
    return {**run, "status": status, "message": message, "finished_at": finished}


def _advance(job: dict[str, Any], now: datetime) -> str | None:
    nxt = next_run(job["recurrence"], now)
    return store.iso(nxt) if nxt else None


_AWAITING_MESSAGE = "승인 대기 — 앱의 예약 작업 화면에서 30분 안에 승인해야 실행됩니다"


def _initial_state(job: dict[str, Any]) -> tuple[str, str]:
    return (AWAITING, _AWAITING_MESSAGE) if _needs_approval(job) else ("running", "")


def _cancel_awaiting(job_id: str, message: str) -> None:
    now = store.iso(datetime.now(UTC))
    for r in store.list_runs_with_status(AWAITING):
        if r["job_id"] == job_id:
            store.transition_run(r["id"], from_status=AWAITING, to_status="cancelled", message=message, finished_at=now)


def _expire_pending(now: datetime) -> None:
    for r in store.list_runs_with_status(AWAITING):
        if now - datetime.fromisoformat(r["started_at"]) > APPROVAL_TTL:
            message = "30분 안에 승인하지 않아 건너뜀"
            done = store.transition_run(
                r["id"], from_status=AWAITING, to_status="expired", message=message, finished_at=store.iso(now)
            )
            if done:
                store.update_job(r["job_id"], last_run_at=store.iso(now), last_status="expired", last_message=message)


def tick(now: datetime | None = None) -> list[dict[str, Any]]:
    """실행 시각이 된 작업을 선점해 실행하고 회차 결과를 돌려준다. 승인이 필요한 작업은 "승인 대기" 회차만 만든다."""
    now = now or datetime.now(UTC)
    _expire_pending(now)
    results: list[dict[str, Any]] = []
    for job, run in store.claim_due(store.iso(now), lambda j, _: _advance(j, now), _initial_state):
        late = now - datetime.fromisoformat(run["scheduled_for"])
        if late > GRACE:
            minutes = int(late.total_seconds() // 60)
            message = f"예정 시각보다 {minutes}분 늦어 건너뜀(서버 중단 등)"
            store.finish_run(run["id"], "missed", message, store.iso(now))
            store.update_job(job["id"], last_run_at=store.iso(now), last_status="missed", last_message=message)
            results.append({**run, "status": "missed", "message": message})
        elif run["status"] == AWAITING:
            store.update_job(job["id"], last_run_at=store.iso(now), last_status=AWAITING, last_message=_AWAITING_MESSAGE)
            results.append(run)
        else:
            results.append(_execute(job, run))
    return results


def run_now(job_id: str) -> dict[str, Any]:
    """예약과 별개로 지금 한 번 실행한다(다음 예약 시각은 그대로). 승인이 필요한 작업은 "승인 대기" 회차만 만든다."""
    job = store.get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    now = store.iso(datetime.now(UTC))
    if _needs_approval(job):
        return store.create_run(job_id, scheduled_for=now, started_at=now, status=AWAITING, message=_AWAITING_MESSAGE)
    return _execute(job, store.create_run(job_id, scheduled_for=now, started_at=now))


def pending_approvals(now: datetime | None = None) -> list[dict[str, Any]]:
    """승인 대기 중인 회차(무엇이 실행될지 보이도록 작업 이름·설정 포함)."""
    now = now or datetime.now(UTC)
    _expire_pending(now)
    items = []
    for r in store.list_runs_with_status(AWAITING):
        expires = datetime.fromisoformat(r["started_at"]) + APPROVAL_TTL
        items.append(
            {
                "run_id": r["id"],
                "job_id": r["job_id"],
                "job_name": r["job_name"],
                "action": r["job_action"],
                "params": r["job_params"],
                "requested_at": r["started_at"],
                "expires_at": store.iso(expires),
            }
        )
    return items


def approve(run_id: str, user: str, now: datetime | None = None) -> dict[str, Any]:
    """승인 대기 회차를 승인하고 바로 실행한다. 한 회차는 한 번만 승인된다."""
    now = now or datetime.now(UTC)
    run = store.get_run(run_id)
    if run is None:
        raise KeyError(run_id)
    if run["status"] != AWAITING:
        raise ValueError("승인 대기 중인 회차가 아닙니다")
    job = store.get_job(run["job_id"])
    if job is None:
        raise KeyError(run_id)
    if now - datetime.fromisoformat(run["started_at"]) > APPROVAL_TTL:
        _expire_pending(now)
        raise ValueError("승인 시간(30분)이 지나 건너뛰었습니다")
    if not store.transition_run(run_id, from_status=AWAITING, to_status="running", decided_by=user):
        raise ValueError("이미 처리된 회차입니다")
    return _execute(job, {**run, "status": "running", "decided_by": user}, approved=True)


def reject(run_id: str, user: str) -> dict[str, Any]:
    run = store.get_run(run_id)
    if run is None:
        raise KeyError(run_id)
    now = store.iso(datetime.now(UTC))
    message = "사용자가 거부했습니다"
    rejected = store.transition_run(
        run_id, from_status=AWAITING, to_status="rejected", message=message, decided_by=user, finished_at=now
    )
    if not rejected:
        raise ValueError("승인 대기 중인 회차가 아닙니다")
    store.update_job(run["job_id"], last_run_at=now, last_status="rejected", last_message=message)
    return {**run, "status": "rejected", "message": message, "decided_by": user, "finished_at": now}


def recover() -> int:
    """서버 시작 시, 중단되어 `running` 으로 남은 회차를 정리한다(승인 대기 회차는 유효 시간 안이면 그대로 둔다)."""
    return store.recover_stale_runs(store.iso(datetime.now(UTC)))
