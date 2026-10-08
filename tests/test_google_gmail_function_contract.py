from __future__ import annotations

from scripts.google.common.gmail_api import GmailAPI
from scripts.google.audit_gmail_function_contract import audit


def test_google_gmail_function_contract_passes() -> None:
    ok, findings = audit()

    assert ok, findings


def test_gmail_delete_is_blocked_without_browser_action() -> None:
    api = GmailAPI(page=object())  # type: ignore[arg-type]

    result = api.delete(0)

    assert result["ok"] is False
    assert result["mode"] == "blocked"
    assert result["reason"] == "gmail_delete_requires_user_final_approval"
