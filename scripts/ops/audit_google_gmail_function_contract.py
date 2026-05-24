"""Read-only audit for Gmail function safety."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GMAIL_CLI = ROOT / "scripts" / "google" / "gmail.py"
GMAIL_API = ROOT / "scripts" / "google" / "gmail_api.py"


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    for path in (GMAIL_CLI, GMAIL_API):
        if not path.exists():
            failures.append(f"missing file: {path.relative_to(ROOT)}")

    cli = GMAIL_CLI.read_text(encoding="utf-8", errors="replace") if GMAIL_CLI.exists() else ""
    api = GMAIL_API.read_text(encoding="utf-8", errors="replace") if GMAIL_API.exists() else ""
    combined = cli + "\n" + api

    forbidden = (
        "send_btn.click",
        "MAIL_SEND",
        "mode=\"gmail_send\"",
        "mode=\"gmail_reply\"",
        "mode=\"gmail_delete\"",
    )
    for token in forbidden:
        if token in combined:
            failures.append(f"forbidden Gmail final-action token remains: {token}")

    required = (
        "draft_only_no_final_submit",
        "reply_draft_only_no_final_submit",
        "final_send_clicked",
        "gmail_delete_requires_user_final_approval",
        "Gmail delete is disabled in automation",
        "sender_present=",
        "input[name=\"q\"]",
    )
    for phrase in required:
        if phrase not in combined:
            failures.append(f"required Gmail safety phrase missing: {phrase}")

    from scripts.google import live_inputs, workflows

    action = workflows.get_action("gmail_send_email")
    if not action.requires_approval:
        failures.append("gmail_send_email must require approval")
    if action.operation != "send":
        failures.append(f"gmail_send_email operation changed: {action.operation}")

    supported = {
        item["action_key"]: item
        for item in live_inputs.build_live_input_coverage()["supported"]
    }
    gmail = supported.get("gmail_send_email")
    if not gmail:
        failures.append("gmail_send_email missing from live input coverage")
    elif gmail.get("final_state_policy") != "no_final_submit_only":
        failures.append("gmail_send_email live input must remain no_final_submit_only")

    return not failures, failures or [
        "Gmail list/search/read paths remain available",
        "Gmail send/reply are draft-only no-final-submit",
        "Gmail delete/star state changes are blocked",
        "gmail_send_email remains approval-gated in Google workflow coverage",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_GOOGLE_GMAIL_FUNCTION_CONTRACT' if ok else 'FAIL_GOOGLE_GMAIL_FUNCTION_CONTRACT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
