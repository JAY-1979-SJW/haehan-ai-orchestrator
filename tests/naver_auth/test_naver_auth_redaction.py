from scripts.naver.common.auth import _redact_input_result


def test_redact_input_result_removes_raw_password_values():
    result = {
        "ok": False,
        "action": "replaced",
        "before": "old-secret",
        "after": "new-secret",
        "reason": "value_mismatch",
    }

    redacted = _redact_input_result(result)

    assert "old-secret" not in str(redacted)
    assert "new-secret" not in str(redacted)
    assert redacted["before"] == "[REDACTED]"
    assert redacted["after"] == "[REDACTED]"
    assert redacted["before_len"] == len("old-secret")
    assert redacted["after_len"] == len("new-secret")
