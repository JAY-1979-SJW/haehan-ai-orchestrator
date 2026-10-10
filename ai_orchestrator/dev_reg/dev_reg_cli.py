"""개발자 등록 승인 게이트 운영 CLI.

명령어:
  pending              pending 승인 목록 조회
  history [--limit N]  승인 히스토리 조회
  detail <task_id>     단일 task 상세 조회
  expire <task_id>     pending task 강제 만료 (관리자용)
  summary              상태 요약

보안 원칙:
  - approve/reject 금지 (텔레그램 전용)
  - submit 실행 금지
  - 토큰/민감정보 출력 금지
  - read-only (expire 제외)

실행: python -m ai_orchestrator.dev_reg.dev_reg_cli <명령> (저장소 루트에서 — ai_orchestrator 는 패키지로만 실행)

출력: 표 형태, 마지막 줄 RESULT: PASS|WARN|FAIL
종료 코드: PASS=0, WARN=2, FAIL=3
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta

from ai_orchestrator.dev_reg import dev_reg_approval, dev_reg_audit_log
from tools.gates.approval import revoke_token

# 출력에서 제거할 필드
_BLOCKED_FIELDS = frozenset({"approval_token_hash", "screenshot_path", "token_id"})
# 값에 포함 시 REDACTED 처리할 키워드
_SENSITIVE_KW = ("password", "passwd", "cookie", "session", "secret", "apikey", "api_key")

EXIT_PASS = 0
EXIT_WARN = 2
EXIT_FAIL = 3


# ── 공통 헬퍼 ────────────────────────────────────────────────────────────────


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


def _fmt_dt(s: str) -> str:
    dt = _parse_iso(s)
    if not dt:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _age(s: str) -> str:
    dt = _parse_iso(s)
    if not dt:
        return "-"
    delta = _utc_now() - dt
    h = int(delta.total_seconds() // 3600)
    m = int((delta.total_seconds() % 3600) // 60)
    if h > 0:
        return f"{h}h {m}m ago"
    return f"{m}m ago"


def _col(s: object, width: int) -> str:
    t = str(s) if s is not None else "-"
    if len(t) > width:
        t = t[: width - 1] + "…"
    return t.ljust(width)


def _hr(width: int = 90) -> None:
    print("-" * width)


def _is_sensitive(key: str, value: object) -> bool:
    low_key = key.lower()
    low_val = str(value).lower()
    return any(kw in low_key or kw in low_val for kw in _SENSITIVE_KW)


def _safe_value(key: str, value: object) -> str:
    if key in _BLOCKED_FIELDS:
        return "[REDACTED]"
    if _is_sensitive(key, value):
        return "[REDACTED]"
    v = str(value) if value is not None else ""
    return v if v else "-"


# ── pending ──────────────────────────────────────────────────────────────────


def cmd_pending() -> int:
    records = dev_reg_approval.list_pending()
    now = _utc_now()

    print("\n[PENDING APPROVALS]")
    if not records:
        print("  (없음)")
        print()
        print("RESULT: PASS")
        return EXIT_PASS

    _hr()
    print(
        f"{'TASK_ID':<20} {'PROVIDER':<10} {'ACTION':<22} {'RISK':<8} {'EXPIRES':<22} {'AGE':<12} {'REQUESTED_BY':<16}"
    )
    _hr()

    warn = False
    for r in records:
        task_id = str(r.get("task_id", ""))
        provider = r.get("provider", "-")
        action = r.get("action_type", "-")
        risk = r.get("risk_level", "-")
        exp_raw = r.get("expires_at", "")
        exp_fmt = _fmt_dt(exp_raw)
        age = _age(r.get("created_at", ""))
        req_by = r.get("requested_by", "-")

        exp_dt = _parse_iso(exp_raw)
        suffix = " [EXPIRED]" if exp_dt and exp_dt < now else ""
        if suffix:
            warn = True

        print(
            f"{_col(task_id, 20)} {_col(provider, 10)} {_col(action, 22)} "
            f"{_col(risk, 8)} {_col(exp_fmt, 22)} {_col(age, 12)} {_col(req_by, 16)}"
            f"{suffix}"
        )

    _hr()
    print(f"  total pending: {len(records)}")
    print()

    if warn:
        print("RESULT: WARN")
        return EXIT_WARN
    print("RESULT: PASS")
    return EXIT_PASS


# ── history ──────────────────────────────────────────────────────────────────


def cmd_history(limit: int) -> int:
    records = dev_reg_approval.list_history(limit=limit)

    print(f"\n[APPROVAL HISTORY] (latest {limit})")
    if not records:
        print("  (없음)")
        print()
        print("RESULT: WARN")
        return EXIT_WARN

    _hr()
    print(f"{'TASK_ID':<20} {'STATUS':<10} {'PROVIDER':<10} {'ACTION':<22} {'CREATED':<22} {'DECIDED':<22}")
    _hr()

    fail_seen = False
    for r in records:
        task_id = str(r.get("task_id", ""))
        status = r.get("status", "-")
        provider = r.get("provider", "-")
        action = r.get("action_type", "-")
        created = _fmt_dt(r.get("created_at", ""))
        decided = _fmt_dt(r.get("decided_at", "") or r.get("executed_at", ""))

        if status == "failed":
            fail_seen = True

        print(
            f"{_col(task_id, 20)} {_col(status, 10)} {_col(provider, 10)} "
            f"{_col(action, 22)} {_col(created, 22)} {_col(decided, 22)}"
        )

    _hr()
    print(f"  showing: {len(records)} record(s)")
    print()

    if fail_seen:
        print("RESULT: WARN")
        return EXIT_WARN
    print("RESULT: PASS")
    return EXIT_PASS


# ── detail ───────────────────────────────────────────────────────────────────


def cmd_detail(task_id: str) -> int:
    rec = dev_reg_approval.get_detail(task_id)

    print(f"\n[TASK DETAIL: {task_id}]")

    if rec is None:
        print(f"  ERROR: task_id '{task_id}' 를 찾을 수 없습니다.")
        print()
        print("RESULT: FAIL")
        return EXIT_FAIL

    _hr()
    field_order = [
        "task_id",
        "status",
        "provider",
        "action_type",
        "risk_level",
        "requested_by",
        "approved_by",
        "reject_reason",
        "created_at",
        "expires_at",
        "decided_at",
        "executed_at",
        "summary",
        "target_url",
        "result",
        "error",
        "telegram_message_id",
    ]

    shown: set[str] = set()
    for key in field_order:
        if key in rec:
            shown.add(key)
            print(f"  {key:<26} {_safe_value(key, rec[key])}")

    for key, val in rec.items():
        if key not in shown:
            print(f"  {key:<26} {_safe_value(key, val)}")

    _hr()
    print()

    status = rec.get("status", "")
    if status in ("failed", "expired"):
        print("RESULT: WARN")
        return EXIT_WARN
    print("RESULT: PASS")
    return EXIT_PASS


# ── expire ───────────────────────────────────────────────────────────────────


def cmd_expire(task_id: str) -> int:
    print(f"\n[FORCE EXPIRE: {task_id}]")
    _hr()

    rec = dev_reg_approval.get(task_id)
    if rec is None:
        print(f"  ERROR: task_id '{task_id}' 를 찾을 수 없습니다.")
        print()
        print("RESULT: FAIL")
        return EXIT_FAIL

    if rec.status != "pending":
        print(f"  ERROR: 현재 상태 '{rec.status}' 는 만료 처리 대상이 아닙니다.")
        print("         (expire 는 pending 상태에서만 허용됩니다)")
        print()
        print("RESULT: FAIL")
        return EXIT_FAIL

    # 1. 하위 승인 토큰 revoke (실패해도 진행)
    if rec.token_id:
        try:
            revoke_token(rec.token_id)
        except Exception as e:  # noqa: BLE001 - cmd_expire(강제 만료) 중 하위 승인 토큰 revoke 실패를 경고만 남기고 계속 진행 - 이후 dev_reg 레코드를 expired로 마킹하는 거부/만료 방향 흐름이라 승인 우회가 아니며, revoke 실패가 오히려 상태를 더 안전한(만료) 쪽으로 이끎
            print(f"  WARN: 토큰 revoke 실패 (계속 진행): {e}")

    # 2. dev_reg 레코드 만료 처리
    updated = dev_reg_approval.mark_expired_internal(task_id)
    if updated is None:
        print("  ERROR: 만료 처리 실패 (스토어에서 record 를 찾지 못했습니다)")
        print()
        print("RESULT: FAIL")
        return EXIT_FAIL

    # 3. 대기 중인 runner 즉시 해제
    dev_reg_approval.signal_approval_event(task_id)

    decided = updated.decided_at or _utc_now().isoformat()
    print(f"  task_id      : {task_id}")
    print("  이전 상태     : pending")
    print("  현재 상태     : expired (강제 만료)")
    print(f"  처리 시각     : {_fmt_dt(decided)}")
    _hr()
    print()
    print("RESULT: PASS")
    return EXIT_PASS


# ── summary ──────────────────────────────────────────────────────────────────


def cmd_summary() -> int:
    now = _utc_now()
    window_24h = now - timedelta(hours=24)

    all_records = dev_reg_approval.list_history(limit=10_000)
    pending_records = [r for r in all_records if r.get("status") == "pending"]

    pending_count = len(pending_records)
    expired_pending = sum(1 for r in pending_records if (dt := _parse_iso(r.get("expires_at", ""))) and dt < now)

    recent_window = [r for r in all_records if (dt := _parse_iso(r.get("created_at", ""))) and dt >= window_24h]
    recent_executed = sum(1 for r in recent_window if r.get("status") == "executed")
    recent_failed = sum(1 for r in recent_window if r.get("status") in ("failed", "rejected"))

    sorted_all = sorted(
        all_records,
        key=lambda r: r.get("created_at", ""),
        reverse=True,
    )
    last_activity = _fmt_dt(sorted_all[0].get("created_at", "")) if sorted_all else "-"

    recent_runs = dev_reg_audit_log.load_recent_runs(n=1)
    last_audit_result = recent_runs[0].get("result", "-") if recent_runs else "-"
    last_audit_time = _fmt_dt(recent_runs[0].get("run_at", "")) if recent_runs else "-"

    # 판정
    warnings: list[str] = []
    if expired_pending > 0:
        warnings.append(f"만료된 pending {expired_pending}건 존재")
    if pending_count > 10:
        warnings.append(f"pending 과다 ({pending_count}건 > 10)")
    if recent_failed > 0:
        warnings.append(f"최근 24h 실패/거절 {recent_failed}건")

    if not warnings:
        result = "PASS"
    elif expired_pending > 0 and pending_count > 20:
        result = "FAIL"
    else:
        result = "WARN"

    print("\n[STATUS SUMMARY]")
    _hr()
    print(f"  {'pending_count':<32} {pending_count}")
    print(f"  {'expired_pending':<32} {expired_pending}")
    print(f"  {'recent_executed (24h)':<32} {recent_executed}")
    print(f"  {'recent_failed (24h)':<32} {recent_failed}")
    print(f"  {'last_activity':<32} {last_activity}")
    print(f"  {'last_audit_result':<32} {last_audit_result}")
    print(f"  {'last_audit_time':<32} {last_audit_time}")

    if warnings:
        _hr()
        print("  [경고]")
        for w in warnings:
            print(f"    - {w}")

    _hr()
    print()
    print(f"RESULT: {result}")

    return {
        "PASS": EXIT_PASS,
        "WARN": EXIT_WARN,
        "FAIL": EXIT_FAIL,
    }[result]


# ── main ─────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dev_reg_cli",
        description="개발자 등록 승인 게이트 운영 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
명령어 예시:
  python dev_reg_cli.py pending
  python dev_reg_cli.py history --limit 20
  python dev_reg_cli.py detail dr-a1b2c3d4e5f6
  python dev_reg_cli.py expire dr-a1b2c3d4e5f6
  python dev_reg_cli.py summary

보안: approve/reject/submit 금지. 민감정보 출력 금지. expire 는 pending 상태에서만 허용.
""",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("pending", help="pending 승인 목록 조회")

    hist_p = sub.add_parser("history", help="승인 히스토리 조회")
    hist_p.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="최대 표시 건수 (기본 20)",
    )

    det_p = sub.add_parser("detail", help="단일 task 상세 조회")
    det_p.add_argument("task_id", help="조회할 task_id")

    exp_p = sub.add_parser("expire", help="pending task 강제 만료 (관리자용)")
    exp_p.add_argument("task_id", help="만료 처리할 task_id")

    sub.add_parser("summary", help="상태 요약")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    dispatch = {
        "pending": lambda: cmd_pending(),
        "history": lambda: cmd_history(args.limit),
        "detail": lambda: cmd_detail(args.task_id),
        "expire": lambda: cmd_expire(args.task_id),
        "summary": lambda: cmd_summary(),
    }

    fn = dispatch.get(args.cmd)
    if fn is None:
        parser.print_help()
        sys.exit(EXIT_FAIL)

    sys.exit(fn())


if __name__ == "__main__":
    main()
