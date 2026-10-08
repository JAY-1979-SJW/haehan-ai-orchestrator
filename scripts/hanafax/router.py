"""하나팩스 CLI 라우터.

명령:
    hanafax status                     — 로그인 상태 + 잔액 확인
    hanafax send <팩스번호> <제목>       — 단건 발송 (테스트용)
    hanafax batch-send                  — 큐 기반 dry-run 플랜 출력
    hanafax batch-send N               — N건 dry-run
    hanafax batch-send --approved --confirm=HANAFAX_APPROVED_BATCH  — 실 발송
"""

from __future__ import annotations

from scripts.hanafax.batch import (
    APPROVAL_CONFIRM_TEXT,
    DEFAULT_QUEUE,
    build_batch_plan,
    execute_batch,
    print_plan,
    print_result,
)
from scripts.common.logger import get_logger

log = get_logger(__name__)


def run_hanafax(task: str | None, sub: str | None, args: list[str]) -> None:
    match task or "status":
        case "status" | "login" | "test":
            _cmd_status()
        case "send":
            _cmd_send(sub, args)
        case "batch-send" | "batch_send" | "batch":
            _cmd_batch_send(sub, args)
        case "queue":
            _cmd_queue(sub)
        case _:
            _print_help()


def _cmd_status() -> None:
    from scripts.hanafax.auth import test_login

    print("=" * 60)
    print("하나팩스 상태 확인")
    print("=" * 60)
    result = test_login()
    if result["ok"]:
        print("✔ 로그인 성공")
        info = result.get("info", "")
        for keyword in ["잔액", "팩스번호", "요금제", "회원상태", "신재우", "skyjwshin"]:
            for line in info.splitlines():
                if keyword in line:
                    print(f"  {line.strip()}")
                    break
    else:
        print(f"✘ 로그인 실패: {result['message']}")


def _cmd_send(sub: str | None, args: list[str]) -> None:
    """단건 발송: hanafax send <팩스번호> <제목>"""
    from scripts.hanafax.sender import send_fax

    confirm = next((a.split("=", 1)[1] for a in args if a.startswith("--confirm=")), None)
    args = [a for a in args if not a.startswith("--confirm=")]
    fax_no = sub or (args[0] if args else "")
    subject = args[0] if (sub and args) else (args[1] if len(args) > 1 else "")
    body = args[-1] if len(args) > 2 else subject

    if not fax_no or not subject:
        raise SystemExit("사용법: hanafax send <팩스번호> <제목> [본문] --confirm=<승인 문구(직접 입력)>")

    from scripts.common.gate import GateBlocked, require_approved

    try:
        require_approved("hanafax_send", confirm, via="hanafax_cli_send")
    except GateBlocked as exc:
        raise SystemExit(f"발송 차단: {exc.result.reason} (사용자가 직접 입력한 승인 문구가 필요합니다)") from exc

    print(f"팩스 발송: {fax_no} / {subject}")
    result = send_fax(receiver_fax=fax_no, subject=subject, body=body)
    mark = "✔" if result["success"] else "✘"
    print(f"{mark} {result['message']}")
    if result.get("job_id"):
        print(f"  접수번호: {result['job_id']}")


def _cmd_batch_send(sub: str | None, args: list[str]) -> None:
    dry_run = "--dry-run" in args or sub in (None, "dry-run") or "--approved" not in args
    approved = "--approved" in args
    confirm = next((a.split("=", 1)[1] for a in args if a.startswith("--confirm=")), "")

    limit = 10
    delay = 30
    for a in ([sub] if sub else []) + list(args):
        txt = str(a)
        if txt.isdigit():
            limit = int(txt)
        elif txt.startswith("--limit="):
            limit = int(txt.split("=", 1)[1])
        elif txt.startswith("--delay="):
            delay = int(txt.split("=", 1)[1])

    if approved and not dry_run:
        if confirm != APPROVAL_CONFIRM_TEXT:
            raise SystemExit(f"실 발송 시 --confirm={APPROVAL_CONFIRM_TEXT} 필요")
        plan = build_batch_plan(limit=limit, delay_seconds=delay)
        print_plan(plan)
        print()
        print("실 발송 시작...")
        result = execute_batch(plan)
        print_result(result)
        return

    # dry-run
    plan = build_batch_plan(limit=limit, delay_seconds=delay)
    print_plan(plan)
    print()
    print("실 발송하려면: hanafax batch-send --approved --confirm=HANAFAX_APPROVED_BATCH")


def _cmd_queue(sub: str | None) -> None:
    limit = int(sub) if sub and sub.isdigit() else 10
    if not DEFAULT_QUEUE.exists():
        print(f"큐 파일 없음: {DEFAULT_QUEUE}")
        print(
            '큐 파일 형식(JSONL): {"receiver_fax":"02-XXXX-XXXX", "receiver_name":"업체명", "subject":"공고명 외주 문의", "bid_name":"공고명"}'
        )
        return

    from scripts.hanafax.batch import load_queue

    rows = load_queue(limit=limit)
    print("=" * 60)
    print(f"하나팩스 큐 ({len(rows)}건)")
    print("=" * 60)
    for i, row in enumerate(rows, 1):
        print(
            f"  {i:>2}. {row.get('receiver_name', ''):<16} {row.get('receiver_fax', '')}  | {row.get('subject', '')[:40]}"
        )


def _print_help() -> None:
    print("""하나팩스 명령:
  status                              로그인 상태 + 잔액 확인
  send <팩스번호> <제목>               단건 팩스 발송
  batch-send [N]                      큐 N건 dry-run 플랜 출력
  batch-send --approved               실 발송 (--confirm 필요)
    --confirm=HANAFAX_APPROVED_BATCH
    --limit=N  --delay=초
  queue [N]                           큐 미리보기

큐 파일: data/hanafax_queue.jsonl
자격증명: python scripts/entry/cdp_cli.py cred set hanafax""")
