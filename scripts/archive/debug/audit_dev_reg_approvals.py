"""개발자 등록 승인 게이트 운영 점검 CLI.

기능 (read-only):
  - 저장소 읽기 가능 여부
  - pending 개수
  - 만료 지난 pending 존재 여부
  - 만료 임박 pending 개수 (기본 30분 이내)
  - 최근 executed / rejected / failed 개수 (기본 24시간)
  - 과다 누적·오래된 pending 감지

판정 기준:
  FAIL  — 저장소 읽기 실패(OSError 등)
  WARN  — 만료 지난 pending 존재 / pending 과다(>10) /
           오래된 pending(>24h) / 데이터 없음
  PASS  — 최근 executed 존재 OR pending 정상 존재

출력:
  사람이 읽을 수 있는 요약 + 마지막 줄 "RESULT: PASS|WARN|FAIL"
  exit code: PASS=0, WARN=2, FAIL=3

알림/재시도 (5단계):
  DEV_REG_ALERT_ENABLED=true 또는 --alert 플래그 시 텔레그램 알림 발송.
  자동 재시도 금지 — retry_candidate 판단만 기록, 실행 없음.

보안:
  approval_token_hash·screenshot_path 경로 전체·password/cookie/session/token
  값 일절 출력 금지.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# LOG_DIR: 환경변수 우선, 없으면 패키지 내 storage/
_log_dir_env = os.environ.get("LOG_DIR", "").strip()
_LOG_DIR = Path(_log_dir_env) if _log_dir_env else _REPO_ROOT / "ai_orchestrator" / "storage"
_STORE_PATH = _LOG_DIR / "dev_reg_approvals.jsonl"

_BLOCKED_FIELDS = frozenset({"approval_token_hash", "screenshot_path"})
_SENSITIVE_KEYWORDS = ("password", "passwd", "cookie", "session", "token", "secret", "apikey", "api_key")

_PENDING_WARN_MAX = 10
_PENDING_OLD_HOURS = 24
_EXPIRY_SOON_MINUTES = 30
_RECENT_WINDOW_HOURS = 24


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def _line(label: str, value: object) -> str:
    return f"  {label:<30} {value}"


# ── 데이터 컨테이너 ──────────────────────────────────────────────────────────


@dataclass
class _AuditData:
    storage_readable: bool
    read_error: str
    total: int
    pending_count: int
    expired_pending_count: int
    expiry_soon_count: int
    recent_executed: int
    recent_rejected: int
    recent_failed: int
    oldest_pending_age: str
    warnings: list[str] = field(default_factory=list)
    result: str = "PASS"  # PASS | WARN | FAIL
    audit_time: str = ""


# ── 저장소 읽기 ──────────────────────────────────────────────────────────────


def _load_records(path: Path) -> tuple[list[dict], str | None]:
    if not path.exists():
        return [], None

    store: dict[str, dict] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                tid = ev.get("task_id")
                if not tid:
                    continue
                store[tid] = ev
    except OSError as exc:
        return [], f"{type(exc).__name__}: {exc}"

    return list(store.values()), None


def _check_summary_leakage(records: list[dict]) -> list[str]:
    hits: list[str] = []
    for rec in records:
        summary_lower = str(rec.get("summary", "")).lower()
        for kw in _SENSITIVE_KEYWORDS:
            if kw in summary_lower:
                tid = str(rec.get("task_id", "?"))[:8]
                hits.append(f"SUMMARY_SENSITIVE_KEYWORD:{kw}:task_id_prefix={tid}")
                break
    return hits


# ── 핵심: 데이터 수집 (print 없음) ──────────────────────────────────────────


def _collect(
    *,
    pending_max: int,
    pending_old_hours: int,
    expiry_soon_minutes: int,
    recent_hours: int,
    store_path: Path,
) -> _AuditData:
    now = _utc_now()
    audit_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    warnings: list[str] = []

    # 1. 저장소 읽기
    records, read_err = _load_records(store_path)
    if read_err is not None:
        warnings.append(f"STORAGE_READ_FAILED:{read_err}")
        return _AuditData(
            storage_readable=False,
            read_error=read_err,
            total=0,
            pending_count=0,
            expired_pending_count=0,
            expiry_soon_count=0,
            recent_executed=0,
            recent_rejected=0,
            recent_failed=0,
            oldest_pending_age="-",
            warnings=warnings,
            result="FAIL",
            audit_time=audit_time,
        )

    total = len(records)

    # 2. 데이터 없음
    if total == 0:
        warnings.append("NO_RECORDS:저장소가 비어있거나 파일이 존재하지 않음")

    # 3. 상태별 분류
    pending: list[dict] = []
    recent_cutoff = now - timedelta(hours=recent_hours)
    recent_executed = recent_rejected = recent_failed = 0

    for rec in records:
        status = rec.get("status", "")
        if status == "pending":
            pending.append(rec)
        elif status == "executed":
            ts = _parse_iso(rec.get("executed_at") or rec.get("decided_at") or "")
            if ts and ts >= recent_cutoff:
                recent_executed += 1
        elif status == "rejected":
            ts = _parse_iso(rec.get("decided_at") or "")
            if ts and ts >= recent_cutoff:
                recent_rejected += 1
        elif status == "failed":
            ts = _parse_iso(rec.get("executed_at") or rec.get("decided_at") or "")
            if ts and ts >= recent_cutoff:
                recent_failed += 1

    # 4. pending 세부 점검
    expired_pending: list[str] = []
    expiry_soon_pending: list[str] = []
    old_pending: list[str] = []
    oldest_pending_dt: datetime | None = None
    expiry_soon_cutoff = now + timedelta(minutes=expiry_soon_minutes)

    for rec in pending:
        tid_prefix = str(rec.get("task_id", "?"))[:8]
        expires_at_dt = _parse_iso(rec.get("expires_at", ""))
        created_at_dt = _parse_iso(rec.get("created_at", ""))

        if expires_at_dt is not None:
            if expires_at_dt <= now:
                expired_pending.append(tid_prefix)
            elif expires_at_dt <= expiry_soon_cutoff:
                expiry_soon_pending.append(tid_prefix)

        if created_at_dt is not None:
            if now - created_at_dt > timedelta(hours=pending_old_hours):
                old_pending.append(tid_prefix)
            if oldest_pending_dt is None or created_at_dt < oldest_pending_dt:
                oldest_pending_dt = created_at_dt

    if oldest_pending_dt is not None:
        secs = (now - oldest_pending_dt).total_seconds()
        oldest_pending_age = f"{int(secs // 3600)}h {int((secs % 3600) // 60)}m"
    else:
        oldest_pending_age = "-"

    # 5. summary 민감 정보 감지 (값 출력 금지)
    leakage_hits = _check_summary_leakage(records)

    # 6. 경고 수집
    if expired_pending:
        warnings.append(
            f"EXPIRED_PENDING_EXISTS:만료 지난 pending {len(expired_pending)}건"
            f" (task_id prefix: {', '.join(expired_pending[:5])})"
        )
    if old_pending:
        warnings.append(f"OLD_PENDING_EXISTS:{pending_old_hours}h 이상 경과 pending {len(old_pending)}건")
    if len(pending) > pending_max:
        warnings.append(f"PENDING_OVERLOAD:pending {len(pending)}건 > 허용 {pending_max}건")
    for hit in leakage_hits:
        warnings.append(f"SUMMARY_LEAKAGE_DETECTED:{hit}")

    # 7. 최종 판정
    result = "PASS"
    if warnings:
        result = "WARN"
    elif total == 0:
        result = "WARN"
    elif recent_executed > 0 or (pending and not expired_pending):
        result = "PASS"
    else:
        warnings.append("NO_RECENT_ACTIVITY:최근 executed 없고 정상 pending 없음")
        result = "WARN"

    return _AuditData(
        storage_readable=True,
        read_error="",
        total=total,
        pending_count=len(pending),
        expired_pending_count=len(expired_pending),
        expiry_soon_count=len(expiry_soon_pending),
        recent_executed=recent_executed,
        recent_rejected=recent_rejected,
        recent_failed=recent_failed,
        oldest_pending_age=oldest_pending_age,
        warnings=warnings,
        result=result,
        audit_time=audit_time,
    )


# ── 출력 (데이터 없음) ───────────────────────────────────────────────────────


def _print_audit(
    data: _AuditData,
    *,
    expiry_soon_minutes: int,
    recent_hours: int,
    store_path: Path,
) -> None:
    lines: list[str] = [
        "=== Dev-Reg Approval Gate — Operational Audit ===",
        _line("store_file", store_path.name),
        _line("audit_time_utc", data.audit_time),
        _line("storage_readable", data.storage_readable),
    ]

    if not data.storage_readable:
        lines.append(_line("read_error", data.read_error))
    else:
        lines += [
            _line("total_records", data.total),
            _line("pending_count", data.pending_count),
            _line("expired_pending_count", data.expired_pending_count),
            _line(f"expiry_soon_pending (<{expiry_soon_minutes}m)", data.expiry_soon_count),
            _line(f"recent_executed ({recent_hours}h)", data.recent_executed),
            _line(f"recent_rejected ({recent_hours}h)", data.recent_rejected),
            _line(f"recent_failed ({recent_hours}h)", data.recent_failed),
            _line("oldest_pending_age", data.oldest_pending_age),
        ]

    if data.warnings:
        lines.append("  warnings")
        for w in data.warnings:
            lines.append(f"    - {w}")
    else:
        lines.append(_line("warnings", "(none)"))

    lines.append(f"RESULT: {data.result}")
    print("\n".join(lines))


def _exit_code(result: str) -> int:
    if result == "PASS":
        return 0
    if result == "FAIL":
        return 3
    return 2


# ── 공개 API ────────────────────────────────────────────────────────────────


def audit(
    *,
    pending_max: int = _PENDING_WARN_MAX,
    pending_old_hours: int = _PENDING_OLD_HOURS,
    expiry_soon_minutes: int = _EXPIRY_SOON_MINUTES,
    recent_hours: int = _RECENT_WINDOW_HOURS,
    store_path: Path = _STORE_PATH,
) -> int:
    """감사 실행 후 stdout 에 요약 출력. exit code 반환.

    기존 테스트 호환: 시그니처·출력·반환값 변경 없음.
    """
    data = _collect(
        pending_max=pending_max,
        pending_old_hours=pending_old_hours,
        expiry_soon_minutes=expiry_soon_minutes,
        recent_hours=recent_hours,
        store_path=store_path,
    )
    _print_audit(
        data,
        expiry_soon_minutes=expiry_soon_minutes,
        recent_hours=recent_hours,
        store_path=store_path,
    )
    return _exit_code(data.result)


def audit_and_alert(
    *,
    pending_max: int = _PENDING_WARN_MAX,
    pending_old_hours: int = _PENDING_OLD_HOURS,
    expiry_soon_minutes: int = _EXPIRY_SOON_MINUTES,
    recent_hours: int = _RECENT_WINDOW_HOURS,
    store_path: Path = _STORE_PATH,
    alert_enabled: bool = False,
    log_run: bool = True,
    audit_log_path: Path | None = None,
) -> int:
    """감사 실행 + 조건부 텔레그램 알림 + 실행 로그 기록.

    보안:
      자동 재시도 절대 금지 — retry_candidate 판단만 기록.
      알림 메시지에 민감정보 포함 금지.
    """
    # 2026-09-29 복원(defect_index #32): 원본 삭제 이후 "허브 분리 1단계"
    # 리팩터(e9c7144b)로 두 모듈이 ai_orchestrator 루트에서
    # persistence/·clients/ 하위로 이동됐다 — 새 경로로 갱신.
    from ai_orchestrator.core.telegram_sender import send_message
    from ai_orchestrator.dev_reg.dev_reg_audit_log import append_run
    from ai_orchestrator.notify.alert_classifier import build_alert_text, classify

    data = _collect(
        pending_max=pending_max,
        pending_old_hours=pending_old_hours,
        expiry_soon_minutes=expiry_soon_minutes,
        recent_hours=recent_hours,
        store_path=store_path,
    )
    _print_audit(
        data,
        expiry_soon_minutes=expiry_soon_minutes,
        recent_hours=recent_hours,
        store_path=store_path,
    )

    classification = classify(data.warnings, data.result)

    alert_sent = False
    if alert_enabled and classification.should_notify:
        text = build_alert_text(
            classification,
            pending_count=data.pending_count,
            expired_pending_count=data.expired_pending_count,
            recent_executed=data.recent_executed,
            recent_failed=data.recent_failed,
            audit_time=data.audit_time,
        )
        try:
            resp = send_message(text)
            alert_sent = bool(resp.get("ok", False))
        except Exception:  # noqa: BLE001
            pass

    if log_run:
        warning_codes = list({w.split(":")[0]: None for w in data.warnings})
        append_run(
            {
                "run_at": data.audit_time,
                "result": data.result,
                "pending_count": data.pending_count,
                "expired_pending_count": data.expired_pending_count,
                "expiry_soon_count": data.expiry_soon_count,
                "recent_executed": data.recent_executed,
                "recent_rejected": data.recent_rejected,
                "recent_failed": data.recent_failed,
                "warning_count": len(data.warnings),
                "warning_codes": warning_codes,
                "alert_sent": alert_sent,
                "alert_type": classification.alert_type,
                "retry_candidate": classification.retry_candidate,
            },
            path=audit_log_path,
        )

    return _exit_code(data.result)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="개발자 등록 승인 게이트 운영 점검 (read-only)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--pending-max", type=int, default=_PENDING_WARN_MAX, help="pending 과다 기준 (이 값 초과 시 WARN)"
    )
    parser.add_argument("--pending-old-hours", type=int, default=_PENDING_OLD_HOURS, help="오래된 pending 기준(시간)")
    parser.add_argument("--expiry-soon-minutes", type=int, default=_EXPIRY_SOON_MINUTES, help="만료 임박 기준(분)")
    parser.add_argument("--recent-hours", type=int, default=_RECENT_WINDOW_HOURS, help="recent 집계 창(시간)")
    parser.add_argument("--store-path", type=Path, default=None, help="dev_reg_approvals.jsonl 직접 지정")
    parser.add_argument(
        "--alert", action="store_true", default=False, help="텔레그램 알림 발송 (DEV_REG_ALERT_ENABLED=true 로도 가능)"
    )
    parser.add_argument("--no-log", action="store_true", default=False, help="감사 실행 로그 기록 안 함")
    args = parser.parse_args()

    alert_enabled = args.alert or os.environ.get("DEV_REG_ALERT_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    store_path = args.store_path if args.store_path else _STORE_PATH

    try:
        return audit_and_alert(
            pending_max=args.pending_max,
            pending_old_hours=args.pending_old_hours,
            expiry_soon_minutes=args.expiry_soon_minutes,
            recent_hours=args.recent_hours,
            store_path=store_path,
            alert_enabled=alert_enabled,
            log_run=not args.no_log,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"RESULT: FAIL ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
