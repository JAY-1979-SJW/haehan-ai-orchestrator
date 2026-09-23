"""USER_FIELD_TEST_01 — 12+ 테스트."""

from __future__ import annotations

import json
from pathlib import Path

REPORT = Path("data/inspection/local_agent_user_field_test/user_field_test_report.json")
CHECKSUMS = Path("data/inspection/local_agent_user_field_test/checksums.json")
SUMMARY = Path("data/inspection/local_agent_user_field_test/user_field_test_summary.md")
RUNBOOK = Path("docs/ops/local_agent_external_field_runbook.md")


# ── 1) 산출물 존재 ────────────────────────────────────────────


def test_report_exists():
    assert REPORT.exists()


def test_checksums_exists():
    assert CHECKSUMS.exists()


def test_summary_exists():
    assert SUMMARY.exists()


def test_runbook_exists():
    assert RUNBOOK.exists()


# ── 2) report 스키마 ──────────────────────────────────────────


def test_report_is_valid_json():
    json.loads(REPORT.read_text(encoding="utf-8"))


def test_report_has_required_steps():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    steps = d.get("steps", {})
    for k in (
        "01_extract_zip_to_clean_folder",
        "02_self_test_python_free",
        "03_diagnostics_python_free",
        "04_gui_launch",
        "05_registration_with_code",
        "06_credential_manager_storage",
        "07_wss_auth_ok",
        "08_heartbeat",
        "09_reexecute_auto_reconnect",
        "10_error_token_not_stored",
        "11_error_register_no_env",
        "12_smartscreen_antivirus",
        "13_user_feedback",
    ):
        assert k in steps, f"missing step: {k}"


def test_report_artifacts_have_sha256():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    art = d.get("artifacts", {})
    assert len(art.get("exe_sha256", "")) == 64
    assert len(art.get("zip_sha256", "")) == 64


def test_report_required_steps_passed():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    steps = d["steps"]
    for k in (
        "01_extract_zip_to_clean_folder",
        "02_self_test_python_free",
        "03_diagnostics_python_free",
        "04_gui_launch",
        "05_registration_with_code",
        "07_wss_auth_ok",
        "09_reexecute_auto_reconnect",
        "10_error_token_not_stored",
        "11_error_register_no_env",
    ):
        assert steps[k]["ok"] is True, f"step {k} not ok"


# ── 3) leak 검사 ─────────────────────────────────────────────


def test_no_token_leak_in_report():
    import re

    text = REPORT.read_text(encoding="utf-8")
    assert not re.search(r'"device_token"\s*:\s*"[A-Za-z0-9._\-]{8,}"', text)
    assert not re.search(r'"registration_code"\s*:\s*"[A-Za-z0-9._\-]{8,}"', text)


def test_no_token_leak_in_summary():
    import re

    text = SUMMARY.read_text(encoding="utf-8")
    assert not re.search(r'"device_token"\s*:\s*"[A-Za-z0-9._\-]{8,}"', text)


def test_no_token_leak_in_runbook():
    import re

    text = RUNBOOK.read_text(encoding="utf-8")
    # 코드 예시의 "여기에-코드-붙여넣기" 같은 placeholder 만 허용
    matches = re.findall(r'"device_token"\s*:\s*"([^"]{8,})"', text)
    real = [m for m in matches if "<" not in m and "여기" not in m and m != "[REDACTED]"]
    assert real == []


# ── 4) agent_id 마스킹 ──────────────────────────────────────


def test_agent_id_masked_in_report():
    """agent_id 가 raw 형태로 노출되면 안 됨 — 마스킹 형태만."""
    text = REPORT.read_text(encoding="utf-8")
    # la-XXX***YYYY 패턴은 OK, la-[a-f0-9]{12} 전체 raw 는 금지
    import re

    raw = re.findall(r"la-[a-f0-9]{12}", text)
    # 단, agent_id mask 안에는 4자리 hex 끝부분 허용 (예: 22df)
    # 정확 검증: 완전 12자 hex 가 노출되면 NG
    assert raw == [], f"raw agent_id leaked: {raw}"


def test_credential_manager_value_not_exported():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    s = d["steps"]["06_credential_manager_storage"]
    assert s["credential_value_in_report"] is False


# ── 5) desktop/ui 미수정 확인 ──────────────────────────────


def test_report_marks_desktop_ui_unchanged():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    s = d.get("desktop_ui_react_unchanged", {})
    assert s.get("verified") is True


# ── 6) runbook 필수 항목 ──────────────────────────────────


def test_runbook_has_sha256_verification():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "Get-FileHash" in text or "certutil" in text


def test_runbook_has_powershell_commands():
    text = RUNBOOK.read_text(encoding="utf-8")
    for keyword in (
        "--self-test",
        "--diagnostics",
        "--register",
        "--agent-id",
        "--gui",
        "HAEHAN_AGENT_WS_ENABLED",
        "HAEHAN_AGENT_SERVER",
        "HAEHAN_AGENT_CODE",
    ):
        assert keyword in text, f"runbook missing: {keyword}"


def test_runbook_has_smartscreen_section():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "SmartScreen" in text


def test_runbook_warns_against_secret_leak():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "registration_code 원문" in text or "device_token" in text


# ── 7) audit ────────────────────────────────────────────


def test_audit_module_imports():
    from scripts.ops import audit_local_agent_user_field_test as a

    assert hasattr(a, "judge_field_test")


def test_audit_warn_same_machine():
    from scripts.ops import audit_local_agent_user_field_test as a

    v = a.judge_field_test(desktop_ui_unchanged_signal=True)
    # 본 환경 외부 PC 미사용 → WARN_SAME_MACHINE_TEST_ONLY 가 정상
    assert v.code in ("PASS_USER_FIELD_TEST", "WARN_SAME_MACHINE_TEST_ONLY")


def test_audit_fail_desktop_ui_touched():
    from scripts.ops import audit_local_agent_user_field_test as a

    v = a.judge_field_test(desktop_ui_unchanged_signal=False)
    assert v.code == "FAIL_DESKTOP_UI_TOUCHED"


def test_audit_fail_report_missing(tmp_path):
    from scripts.ops import audit_local_agent_user_field_test as a

    v = a.judge_field_test(report_path=tmp_path / "missing.json")
    assert v.code == "FAIL_REPORT_MISSING"


# ── 8) 회귀 가드 ────────────────────────────────────────


def test_regression_gui_impl_audit_imports():
    from scripts.ops import audit_local_agent_gui_implementation as a

    assert hasattr(a, "judge_impl")


def test_regression_desktop_launcher_intact():
    from local_agent import desktop_launcher

    for sym in ("main", "self_test", "register_flow", "connect_flow"):
        assert hasattr(desktop_launcher, sym)


def test_regression_gui_app_pages_intact():
    from local_agent import gui_app

    for p in ("PAGE_DASHBOARD", "PAGE_REGISTRATION", "PAGE_LOGS", "PAGE_SETTINGS"):
        assert hasattr(gui_app, p)
