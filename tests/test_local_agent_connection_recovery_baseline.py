from tools.audits.agent import audit_local_agent_connection_recovery_baseline as audit


def test_local_agent_connection_recovery_baseline_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_auth_failed_recovery_is_user_confirmed_reregister():
    from core.agent_runtime.connection import connection_diagnostics as cd

    plan = cd.build_recovery_plan(
        state=cd.STATE_AUTH_FAILED,
        last_error_code="AUTH_FAILED_4401",
        token_present=True,
    )

    assert plan.next_action == "RE_REGISTER_REQUIRED"
    assert plan.requires_user_confirmation is True
    assert plan.can_auto_retry is False
    assert plan.should_delete_token is False


def test_heartbeat_recovery_allows_auto_reconnect():
    from core.agent_runtime.connection import connection_diagnostics as cd

    plan = cd.build_recovery_plan(
        state=cd.STATE_DISCONNECTED,
        last_error_code="HEARTBEAT_LOST",
        token_present=True,
    )

    assert plan.next_action == "AUTO_RECONNECT"
    assert plan.can_auto_retry is True
    assert plan.should_delete_token is False


def test_connection_recovery_rendering_redacts_sensitive_words():
    from core.agent_runtime.connection import connection_diagnostics as cd

    plan = cd.build_recovery_plan(
        state=cd.STATE_AUTH_FAILED,
        last_error_code="AUTH_FAILED_4401",
        token_present=True,
    )
    rendered = cd.render_recovery_block(plan)

    assert "AUTH_FAILED_4401" in rendered
    assert "Bearer " not in rendered
    assert "registration_code=" not in rendered
    assert "device_token" not in rendered
