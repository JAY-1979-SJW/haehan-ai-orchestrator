import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / ".."))

from ai_orchestrator.core.logging_utils import mask_sensitive, safe_json, safe_log_dict, truncate_large_text

# ── mask_sensitive ─────────────────────────────────────────────


def test_api_key_masked():
    data = {"api_key": "supersecretkey12345"}
    result = mask_sensitive(data)
    assert result["api_key"] != "supersecretkey12345"
    assert "***" in result["api_key"]
    assert "supersecretkey12345" not in result["api_key"]


def test_token_masked():
    data = {"token": "eyJhbGciOiJIUzI1NiJ9.payload"}
    result = mask_sensitive(data)
    assert "***" in result["token"]
    assert "eyJhbGciOiJIUzI1NiJ9" not in result["token"]


def test_non_sensitive_key_untouched():
    data = {"task_id": "t-001", "action_type": "read_file"}
    result = mask_sensitive(data)
    assert result["task_id"] == "t-001"
    assert result["action_type"] == "read_file"


def test_nested_token_masked():
    data = {
        "outer": {
            "token": "inner_secret_token_xyz",
            "visible": "public_info",
        }
    }
    result = mask_sensitive(data)
    assert "***" in result["outer"]["token"]
    assert result["outer"]["visible"] == "public_info"


def test_list_with_sensitive_dict():
    data = [{"password": "abc123"}, {"normal": "value"}]
    result = mask_sensitive(data)
    assert "***" in result[0]["password"]
    assert result[1]["normal"] == "value"


def test_short_value_masked():
    data = {"secret": "ab"}
    result = mask_sensitive(data)
    assert result["secret"] == "***"


def test_password_masked():
    data = {"password": "mypassword"}
    result = mask_sensitive(data)
    assert result["password"] != "mypassword"
    assert "***" in result["password"]


# ── truncate_large_text ────────────────────────────────────────


def test_short_text_not_truncated():
    text = "hello world"
    assert truncate_large_text(text, max_len=500) == text


def test_long_text_truncated():
    text = "x" * 600
    result = truncate_large_text(text, max_len=500)
    assert len(result) < 600
    assert "truncated" in result


def test_truncate_shows_cut_count():
    text = "a" * 600
    result = truncate_large_text(text, max_len=500)
    assert "100" in result  # 600 - 500 = 100 chars cut


# ── safe_log_dict ──────────────────────────────────────────────


def test_safe_log_dict_masks_token():
    result = safe_log_dict(task_id="t-001", token="mysecrettoken", action="read")
    assert "***" in result["token"]
    assert result["task_id"] == "t-001"


def test_safe_log_dict_returns_dict():
    result = safe_log_dict(a=1, b="two")
    assert isinstance(result, dict)


# ── safe_json ─────────────────────────────────────────────────


def test_safe_json_handles_non_serializable():
    from datetime import datetime

    result = safe_json({"dt": datetime(2026, 1, 1)})
    assert "2026" in result
