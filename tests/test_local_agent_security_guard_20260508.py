"""로컬 에이전트 보안 guard 테스트"""

from __future__ import annotations

from ai_orchestrator.contracts.local_task_protocol import build_task
from core.agent_runtime.runtime.security_guard import (
    block_forbidden_action,
    detect_user_direct_required,
    sanitize_runtime_result,
    validate_task_before_run,
)


def _task(action: str = "open_url", **kw) -> dict:
    t = build_task(action, "https://www.g2b.go.kr/notice")
    t.update(kw)
    return t


# ── validate_task_before_run ───────────────────────────────────────────────────


def test_open_url_allowed():
    r = validate_task_before_run(_task("open_url"))
    assert r["allowed"] is True


def test_read_page_allowed():
    r = validate_task_before_run(_task("read_page"))
    assert r["allowed"] is True


def test_auto_bid_submit_blocked():
    t = _task("open_url")
    t["action"] = "auto_bid_submit"
    r = validate_task_before_run(t)
    assert r["allowed"] is False


def test_auto_sign_blocked():
    t = _task("open_url")
    t["action"] = "auto_sign"
    r = validate_task_before_run(t)
    assert r["allowed"] is False


def test_auto_payment_blocked():
    t = _task("open_url")
    t["action"] = "auto_payment"
    r = validate_task_before_run(t)
    assert r["allowed"] is False


def test_collect_cookie_blocked():
    t = _task("open_url")
    t["action"] = "collect_cookie"
    r = validate_task_before_run(t)
    assert r["allowed"] is False


def test_collect_otp_blocked():
    t = _task("open_url")
    t["action"] = "collect_otp"
    r = validate_task_before_run(t)
    assert r["allowed"] is False


def test_collect_password_blocked():
    t = _task("open_url")
    t["action"] = "collect_password"
    r = validate_task_before_run(t)
    assert r["allowed"] is False


def test_cert_file_blocked():
    t = _task("open_url")
    t["action"] = "read_certificate_file"
    r = validate_task_before_run(t)
    assert r["allowed"] is False


def test_cert_password_input_user_direct():
    t = _task("open_url")
    t["action"] = "cert_password_input"
    r = validate_task_before_run(t)
    assert r["user_direct_required"] is True


def test_otp_input_user_direct():
    t = _task("open_url")
    t["action"] = "otp_input"
    r = validate_task_before_run(t)
    assert r["user_direct_required"] is True


def test_sensitive_field_in_task_blocked():
    t = _task("open_url")
    t["password"] = "secret"
    r = validate_task_before_run(t)
    assert r["allowed"] is False


def test_cookie_in_task_blocked():
    t = _task("open_url")
    t["cookie"] = "sess=abc"
    r = validate_task_before_run(t)
    assert r["allowed"] is False


# ── detect_user_direct_required ────────────────────────────────────────────────


def test_otp_signal_user_direct():
    r = detect_user_direct_required(_task("open_url"), "otp_detected")
    assert r["user_direct_required"] is True


def test_e_sign_signal_user_direct():
    r = detect_user_direct_required(_task("open_url"), "e_signature_detected")
    assert r["user_direct_required"] is True


def test_bid_signal_user_direct():
    r = detect_user_direct_required(_task("open_url"), "bid_submit_detected")
    assert r["user_direct_required"] is True


def test_no_signal_allowed():
    r = detect_user_direct_required(_task("open_url"), None)
    assert r["allowed"] is True


# ── block_forbidden_action ─────────────────────────────────────────────────────


def test_block_forbidden_returns_blocked():
    t = _task("open_url")
    t["action"] = "auto_bid_submit"
    r = block_forbidden_action(t)
    assert r["blocked"] is True


def test_block_safe_returns_not_blocked():
    r = block_forbidden_action(_task("open_url"))
    assert r["blocked"] is False


# ── sanitize_runtime_result ────────────────────────────────────────────────────


def test_sanitize_removes_cookie():
    raw = {"task_id": "t1", "cookie": "sess=abc", "title_hint": "test", "status": "COMPLETED"}
    safe = sanitize_runtime_result(raw)
    assert "cookie" not in safe or safe.get("cookie") in (None, False, "", [], {})


def test_sanitize_fixed_fields_set():
    raw = {"task_id": "t1", "title_hint": "test", "status": "COMPLETED"}
    safe = sanitize_runtime_result(raw)
    assert safe["cookie_exported"] is False
    assert safe["password_collected"] is False
