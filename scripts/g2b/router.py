"""G2B (나라장터/조달청) 서비스 라우터.

router 역할: command dispatch, validator 호출, gate 호출, response formatting만 담당.
실제 G2B 접속, 로그인, 투찰, 전자서명 구현 없음.
"""

from __future__ import annotations

from scripts.common.gate import check as gate_check
from scripts.common.logger import get_logger

__status__ = {
    "tasks": {
        "discover (공개공고 URL 탐색)": "partial",
        "download (첨부파일 다운로드)": "partial",
        "suite (Read-Only 라이브)": "partial",
        "status (세대 상태 조회)": "skeleton",
        "gate (gate 판정)": "skeleton",
        "analysis-draft (입찰분석 초안)": "skeleton",
        "submit-draft (제출 초안)": "skeleton",
    },
    "note": "G2B 세대 골격 생성 완료. 실제 스크립트 검증은 다음 단계에서 수행.",
}

ROUTER_COMMANDS: tuple[str, ...] = (
    "status",
    "search",
    "detail",
    "attachment",
    "analysis-draft",
    "submit-draft",
    "gate",
    "discover",
    "download",
    "suite",
)

ROUTER_RESPONSE_KEYS: tuple[str, ...] = (
    "command",
    "status",
    "decision",
    "reason",
    "user_direct_required",
    "local_agent_required",
    "approval_required",
    "blocked",
    "next_step",
    "evidence_policy",
    "report_policy",
)

_log = get_logger(__name__)


def run_g2b(task: str | None, sub: str | None, args: list[str]) -> None:
    """G2B 서비스 라우팅.

    task: status | search | detail | attachment | analysis-draft | submit-draft
          | gate | discover | download | suite
    """
    match task or "help":
        case "status":
            _cmd_status()
        case "gate":
            _cmd_gate(args)
        case "analysis-draft":
            _cmd_analysis_draft(args)
        case "submit-draft":
            _cmd_submit_draft(args)
        case "discover":
            _cmd_discover(args)
        case "download":
            _cmd_download(args)
        case "suite":
            _cmd_suite(args)
        case _:
            _print_help()


def _cmd_status() -> None:
    from scripts.g2b.site_profile import G2B_SITE_PROFILE

    result = _build_response(
        command="status",
        status="ok",
        decision="READ_ONLY_ALLOWED",
        reason="G2B 세대 골격 상태 조회",
        next_step="scripts/g2b/ 내 profile/gates/validators/router 확인",
        evidence_policy=G2B_SITE_PROFILE.get("evidence_warehouse", {}),
        report_policy={"root": "docs/reports/", "prefix": "g2b_"},
    )
    import json

    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cmd_gate(args: list[str]) -> None:
    from scripts.g2b.gates import evaluate_g2b_action_gate

    action = args[0] if args else ""
    if not action:
        print("[G2B gate] action 인수 필요. 예: g2b gate search_notice")
        return
    result = evaluate_g2b_action_gate(action)
    response = _build_response(
        command="gate",
        status="ok",
        **result,
        next_step=None,
        evidence_policy=None,
        report_policy=None,
    )
    import json

    print(json.dumps(response, ensure_ascii=False, indent=2))


def _print_draft_gate(action: str, command: str, next_step: str, evidence_path: str) -> None:
    """초안 작성 명령 공용 — action gate 평가 결과를 응답 형식(JSON)으로 출력한다."""
    from scripts.g2b.gates import evaluate_g2b_action_gate

    gate = evaluate_g2b_action_gate(action)
    response = _build_response(
        command=command,
        status="ok",
        **gate,
        next_step=next_step,
        evidence_policy={"path": evidence_path},
        report_policy=None,
    )
    import json

    print(json.dumps(response, ensure_ascii=False, indent=2))


def _cmd_analysis_draft(args: list[str]) -> None:
    _print_draft_gate("create_bid_analysis_draft", "analysis-draft", "초안 작성 후 사용자 검토 필요", "data/g2b/bid_analysis/")


def _cmd_submit_draft(args: list[str]) -> None:
    _print_draft_gate(
        "create_submit_draft", "submit-draft", "초안 생성 후 실제 제출은 사용자 직접 수행 필요", "data/g2b/submit_drafts/"
    )


def _build_response(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    command: str,
    status: str,
    decision: str = "",
    reason: str = "",
    user_direct_required: bool = False,
    local_agent_required: bool = False,
    approval_required: bool = False,
    blocked: bool = False,
    draft_allowed: bool = False,
    read_only_allowed: bool = False,
    next_step: object = None,
    evidence_policy: object = None,
    report_policy: object = None,
    **_: object,
) -> dict[str, object]:
    return {
        "command": command,
        "status": status,
        "decision": decision,
        "reason": reason,
        "user_direct_required": user_direct_required,
        "local_agent_required": local_agent_required,
        "approval_required": approval_required,
        "blocked": blocked,
        "next_step": next_step,
        "evidence_policy": evidence_policy,
        "report_policy": report_policy,
    }


def _cmd_discover(args: list[str]) -> None:
    gate_check("goto")
    print("[G2B] 공개 공고 유효 URL 탐색")
    from scripts.g2b.discover_valid_public_notice_urls import main

    main()


def _cmd_download(args: list[str]) -> None:
    gate_check("file_delete")  # 파일 다운로드 = notify
    print("[G2B] 첨부파일 배치 다운로드")
    from scripts.g2b.download_g2b_direct_attachment_urls import main

    main()


def _cmd_suite(args: list[str]) -> None:
    gate_check("goto")
    print("[G2B] 공개 공고 Read-Only 라이브 스위트 실행")
    from scripts.g2b.run_public_notice_readonly_live_suite import main

    main()


def _print_help() -> None:
    print("""G2B 사용법:
  python scripts/entry/cdp_cli.py g2b status              세대 상태 조회
  python scripts/entry/cdp_cli.py g2b gate <action>       gate 판정
  python scripts/entry/cdp_cli.py g2b analysis-draft      입찰분석 초안
  python scripts/entry/cdp_cli.py g2b submit-draft        제출 초안
  python scripts/entry/cdp_cli.py g2b discover            공개 공고 URL 탐색
  python scripts/entry/cdp_cli.py g2b download            첨부파일 배치 다운로드
  python scripts/entry/cdp_cli.py g2b suite               Read-Only 라이브 스위트""")
