from __future__ import annotations

from scripts.ops import audit_google_home_login_gate


def test_google_home_login_gate_passes() -> None:
    assert audit_google_home_login_gate.audit() == []
