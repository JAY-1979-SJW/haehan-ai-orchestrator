"""공통 task protocol 테스트"""

from __future__ import annotations

import pytest

from ai_orchestrator.contracts.local_task_protocol import (
    ALLOWED_TASK_ACTIONS,
    EXEC_MODE_LOCAL_PLAYWRIGHT,
    STATUS_COMPLETED,
    TASK_TYPE_BROWSER,
    build_result,
    build_task,
    validate_result,
    validate_task,
)

# ── build_task ─────────────────────────────────────────────────────────────────


def test_build_task_basic():
    t = build_task("open_url", "https://www.g2b.go.kr/notice")
    assert t["task_type"] == TASK_TYPE_BROWSER
    assert t["execution_mode"] == EXEC_MODE_LOCAL_PLAYWRIGHT
    assert t["action"] == "open_url"
    assert t["readonly"] is True


def test_build_task_id_auto_generated():
    t = build_task("read_page", "https://www.g2b.go.kr")
    assert t["task_id"]


def test_build_task_id_custom():
    t = build_task("open_url", "https://www.g2b.go.kr", task_id="custom-123")
    assert t["task_id"] == "custom-123"


def test_build_task_invalid_action():
    with pytest.raises(ValueError):
        build_task("login_with_password", "https://www.g2b.go.kr")


def test_build_task_no_forbidden_fields():
    t = build_task("open_url", "https://www.g2b.go.kr")
    for f in ("cookie", "session", "password", "otp", "token"):
        assert f not in t


def test_build_task_created_at_present():
    t = build_task("open_url", "https://www.g2b.go.kr")
    assert t["created_at"]


# ── build_result ───────────────────────────────────────────────────────────────


def test_build_result_fixed_safe_fields():
    r = build_result("t1", True, STATUS_COMPLETED)
    assert r["cookie_exported"] is False
    assert r["session_exported"] is False
    assert r["password_collected"] is False
    assert r["otp_collected"] is False
    assert r["certificate_password_collected"] is False
    assert r["sensitive_data_collected"] is False


def test_build_result_extra_sensitive_removed():
    r = build_result("t1", True, STATUS_COMPLETED, extra={"cookie": "abc", "safe_key": "val"})
    assert "cookie" not in r or r.get("cookie") in (None, False, "", [], {})
    assert r.get("safe_key") == "val"


def test_build_result_invalid_status():
    with pytest.raises(ValueError):
        build_result("t1", True, "UNKNOWN_STATUS")


# ── validate_task ──────────────────────────────────────────────────────────────


def test_validate_task_ok():
    t = build_task("open_url", "https://www.g2b.go.kr/notice")
    assert validate_task(t) == []


def test_validate_task_missing_task_id():
    t = build_task("open_url", "https://www.g2b.go.kr")
    t["task_id"] = ""
    v = validate_task(t)
    assert any("task_id" in e for e in v)


def test_validate_task_forbidden_field():
    t = build_task("open_url", "https://www.g2b.go.kr")
    t["password"] = "secret"
    v = validate_task(t)
    assert any("password" in e for e in v)


def test_validate_task_invalid_action():
    t = build_task("open_url", "https://www.g2b.go.kr")
    t["action"] = "auto_bid"
    v = validate_task(t)
    assert any("action" in e for e in v)


# ── validate_result ────────────────────────────────────────────────────────────


def test_validate_result_ok():
    r = build_result("t1", True, STATUS_COMPLETED)
    assert validate_result(r) == []


def test_validate_result_sensitive_field():
    r = build_result("t1", True, STATUS_COMPLETED)
    r["cookie"] = "session=abc"
    v = validate_result(r)
    assert any("cookie" in e for e in v)


def test_validate_result_fixed_field_tampered():
    r = build_result("t1", True, STATUS_COMPLETED)
    r["password_collected"] = True
    v = validate_result(r)
    assert any("password_collected" in e for e in v)


# ── allowed actions 포함 확인 ──────────────────────────────────────────────────


def test_all_allowed_actions_buildable():
    for action in ALLOWED_TASK_ACTIONS:
        t = build_task(action, "https://www.g2b.go.kr")
        assert t["action"] == action


# ── LOCAL_BROWSER_DEFAULT → LOCAL_PLAYWRIGHT 변환 ─────────────────────────────


def test_local_browser_default_maps_to_local_playwright():
    t = build_task("open_url", "https://www.g2b.go.kr/notice")
    assert t["execution_mode"] == EXEC_MODE_LOCAL_PLAYWRIGHT
