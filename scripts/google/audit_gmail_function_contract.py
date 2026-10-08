"""Read-only audit for Gmail function safety."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GMAIL_CLI = ROOT / "scripts" / "google" / "common" / "gmail.py"
GMAIL_API = ROOT / "scripts" / "google" / "common" / "gmail_api.py"
GMAIL_ANALYSIS = ROOT / "scripts" / "google" / "common" / "gmail_analysis.py"
GOOGLE_ROUTER = ROOT / "scripts" / "google" / "router.py"


def _check_files_exist() -> list[str]:
    return [
        f"missing file: {path.relative_to(ROOT)}"
        for path in (GMAIL_CLI, GMAIL_API, GMAIL_ANALYSIS, GOOGLE_ROUTER)
        if not path.exists()
    ]


def _load_combined_source() -> str:
    cli = GMAIL_CLI.read_text(encoding="utf-8", errors="replace") if GMAIL_CLI.exists() else ""
    api = GMAIL_API.read_text(encoding="utf-8", errors="replace") if GMAIL_API.exists() else ""
    analysis = GMAIL_ANALYSIS.read_text(encoding="utf-8", errors="replace") if GMAIL_ANALYSIS.exists() else ""
    router = GOOGLE_ROUTER.read_text(encoding="utf-8", errors="replace") if GOOGLE_ROUTER.exists() else ""
    return cli + "\n" + api + "\n" + analysis + "\n" + router


def _check_forbidden_tokens(combined: str) -> list[str]:
    forbidden = (
        "send_btn.click",
        "MAIL_SEND",
        'mode="gmail_send"',
        'mode="gmail_reply"',
        'mode="gmail_delete"',
    )
    return [f"forbidden Gmail final-action token remains: {token}" for token in forbidden if token in combined]


def _check_required_phrases(combined: str) -> list[str]:
    required = (
        "draft_only_no_final_submit",
        "reply_draft_only_no_final_submit",
        "final_send_clicked",
        "gmail_delete_requires_user_final_approval",
        "Gmail delete is disabled in automation",
        "sender_present=",
        'input[name="q"]',
        "mail analyze",
        "read_analyze_no_state_change",
    )
    return [f"required Gmail safety phrase missing: {phrase}" for phrase in required if phrase not in combined]


def _check_gmail_send_action() -> list[str]:
    from scripts.google.common import workflows

    failures = []
    action = workflows.get_action("gmail_send_email")
    if not action.requires_approval:
        failures.append("gmail_send_email must require approval")
    if action.operation != "send":
        failures.append(f"gmail_send_email operation changed: {action.operation}")
    return failures


def _check_gmail_live_input_coverage() -> list[str]:
    from scripts.google.common import live_inputs

    supported = {item["action_key"]: item for item in live_inputs.build_live_input_coverage()["supported"]}
    gmail = supported.get("gmail_send_email")
    if not gmail:
        return ["gmail_send_email missing from live input coverage"]
    if gmail.get("final_state_policy") != "no_final_submit_only":
        return ["gmail_send_email live input must remain no_final_submit_only"]
    return []


def audit() -> tuple[bool, list[str]]:
    # 2026-09-29 STD-08(복잡도) 리팩터: 독립 체크들을 _check_*() 함수로 분리(순서·조건·문자열
    # 그대로) — #48 과 같은 계열.
    failures: list[str] = []
    failures.extend(_check_files_exist())

    combined = _load_combined_source()
    failures.extend(_check_forbidden_tokens(combined))
    failures.extend(_check_required_phrases(combined))
    failures.extend(_check_gmail_send_action())
    failures.extend(_check_gmail_live_input_coverage())

    return not failures, failures or [
        "Gmail list/search/read paths remain available",
        "Gmail send/reply are draft-only no-final-submit",
        "Gmail delete/star state changes are blocked",
        "gmail_send_email remains approval-gated in Google workflow coverage",
    ]


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "GOOGLE_GMAIL_FUNCTION_CONTRACT")


if __name__ == "__main__":
    raise SystemExit(main())
