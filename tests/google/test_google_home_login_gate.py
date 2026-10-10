from __future__ import annotations

from tools.audits.google import audit_google_home_login_gate


def test_google_home_login_gate_passes() -> None:
    assert audit_google_home_login_gate.audit() == []
