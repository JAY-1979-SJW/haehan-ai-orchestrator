from tools.audits.agent import audit_local_agent_e2e_baseline_contract as audit


def test_local_agent_e2e_baseline_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_local_agent_e2e_baseline_is_locked():
    text = audit.LOCAL_AGENT_BASELINE.read_text(encoding="utf-8")

    assert "Status: LOCKED" in text
    assert "Baseline ID: HAEHAN-LOCAL-AGENT-E2E-BASELINE-01" in text


def test_local_agent_e2e_baseline_locks_auth_and_dispatch_boundaries():
    text = audit.LOCAL_AGENT_BASELINE.read_text(encoding="utf-8")

    assert "Local-agent WebSocket must require `agent_id + device_token`." in text
    assert "receiving only server-dispatched tasks" in text
    assert "A local agent must not receive tasks for another agent id." in text
    assert "Unapproved high-risk tasks must not appear in the local-agent dispatch queue." in text
    assert "A single local-agent WebSocket session must receive at most one active task" in text
    assert "Concurrent server submissions must remain queued and drain one by one" in text
    assert "True simultaneous local execution requires multiple registered agents" in text


def test_local_agent_e2e_baseline_blocks_secret_and_user_direct_shortcuts():
    text = audit.LOCAL_AGENT_BASELINE.read_text(encoding="utf-8")

    assert "execute server-contract-bypassing user-direct commands" in text
    assert "return raw secrets, tokens, cookies, sessions, passwords, OTP values, or auth" in text
    assert "start browser or AI work that was not dispatched by the server" in text
