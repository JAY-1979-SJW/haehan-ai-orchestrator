from scripts.common.security import (
    REDACTED,
    is_sensitive_key,
    mask_identifier,
    redact_mapping,
    safe_preview,
)


def test_sensitive_key_matching_covers_common_secret_shapes():
    assert is_sensitive_key("client_secret")
    assert is_sensitive_key("refreshToken")
    assert is_sensitive_key("storage_state_path")
    assert is_sensitive_key("authorization")


def test_redact_mapping_handles_nested_lists_and_tuples():
    payload = {
        "visible": "contact skyjwshin@example.com",
        "nested": [
            {"access_token": "secret-token-123", "ok": "yes"},
            ("keep", {"session_id": "sid-123"}),
        ],
    }

    redacted = redact_mapping(payload)

    assert redacted["visible"] == "contact sk***@example.com"
    assert redacted["nested"][0]["access_token"] == REDACTED
    assert redacted["nested"][0]["ok"] == "yes"
    assert redacted["nested"][1][1]["session_id"] == REDACTED
    assert "secret-token-123" not in str(redacted)


def test_safe_preview_masks_inline_sensitive_patterns():
    text = "user@example.com Bearer abcdefghijklmnop 900101-1234567 1234-5678-9012-3456"

    preview = safe_preview(text)

    assert "user@example.com" not in preview
    assert "abcdefghijklmnop" not in preview
    assert "900101-1234567" not in preview
    assert "1234-5678-9012-3456" not in preview


def test_mask_identifier_does_not_return_raw_id():
    assert mask_identifier("skyjwshin@example.com") == "sk***@example.com"
    assert mask_identifier("local-admin") == "lo***in"
