"""Domain Room Allocation 구조 감사 테스트.

집 배정 문서 존재·방 구조·금지 정책·게이트 결정 검증.
기능 테스트 아님 — 구조/정책 위반 감지 테스트만 포함.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / "docs" / "architecture"
UNITS = ARCH / "domain_units"


# ── 공통 헬퍼 ────────────────────────────────────────────────────────────────

def _read(path: Path) -> str:
    assert path.exists(), f"문서 없음: {path}"
    return path.read_text(encoding="utf-8")


def _audit_summary() -> dict:
    p = ROOT / "data" / "domain_room_allocation_audit_latest.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


# ── 1. 필수 문서 존재 ────────────────────────────────────────────────────────

def test_doc_domain_room_allocation_rule_exists():
    assert (ARCH / "domain_room_allocation_rule.md").exists()


def test_doc_gabia_room_allocation_exists():
    assert (UNITS / "gabia_room_allocation.md").exists()


def test_doc_g2b_room_allocation_exists():
    assert (UNITS / "g2b_room_allocation.md").exists()


def test_doc_common_domain_room_allocation_exists():
    assert (UNITS / "common_domain_room_allocation.md").exists()


def test_doc_shared_facility_allocation_exists():
    assert (ARCH / "shared_facility_allocation.md").exists()


# ── 2. 방 구조 키워드 ────────────────────────────────────────────────────────

def test_room_structure_entrance_router():
    assert "entrance/router" in _read(ARCH / "domain_room_allocation_rule.md")


def test_room_structure_profile():
    assert "resident-card/profile" in _read(ARCH / "domain_room_allocation_rule.md")


def test_room_structure_gates():
    assert "security-door/gates" in _read(ARCH / "domain_room_allocation_rule.md")


def test_room_structure_validators():
    assert "inspection/validators" in _read(ARCH / "domain_room_allocation_rule.md")


def test_room_structure_usecase():
    assert "living-room/usecase" in _read(ARCH / "domain_room_allocation_rule.md")


def test_room_structure_adapter():
    assert "external-door/adapter" in _read(ARCH / "domain_room_allocation_rule.md")


def test_room_structure_workflow():
    assert "parking/workflow" in _read(ARCH / "domain_room_allocation_rule.md")


def test_room_structure_storage():
    assert "warehouse/storage" in _read(ARCH / "domain_room_allocation_rule.md")


def test_room_structure_audit():
    assert "cctv/audit" in _read(ARCH / "domain_room_allocation_rule.md")


def test_room_structure_tests():
    assert "alarm/tests" in _read(ARCH / "domain_room_allocation_rule.md")


def test_room_structure_docs():
    assert "rulebook/docs" in _read(ARCH / "domain_room_allocation_rule.md")


# ── 3. 집 경계 금지선 ────────────────────────────────────────────────────────

def test_rule_cross_domain_import_forbidden():
    doc = _read(ARCH / "domain_room_allocation_rule.md")
    assert "다른 Domain Unit 직접 import 금지" in doc


def test_rule_router_no_db():
    doc = _read(ARCH / "domain_room_allocation_rule.md")
    assert "router에서 DB 직접 접근 금지" in doc


def test_rule_session_forbidden():
    doc = _read(ARCH / "domain_room_allocation_rule.md")
    assert "session" in doc and "금지" in doc


def test_rule_payment_sign_blocked():
    doc = _read(ARCH / "domain_room_allocation_rule.md")
    assert "USER_DIRECT_REQUIRED" in doc


# ── 4. Gabia 집 배정 ─────────────────────────────────────────────────────────

def test_gabia_domain_registration_unit():
    assert "gabia/domain-registration" in _read(UNITS / "gabia_room_allocation.md")


def test_gabia_dns_management_unit():
    assert "gabia/dns-management" in _read(UNITS / "gabia_room_allocation.md")


def test_gabia_hosting_management_unit():
    assert "gabia/hosting-management" in _read(UNITS / "gabia_room_allocation.md")


def test_gabia_mail_management_unit():
    assert "gabia/mail-management" in _read(UNITS / "gabia_room_allocation.md")


def test_gabia_account_readonly_unit():
    assert "gabia/account-readonly" in _read(UNITS / "gabia_room_allocation.md")


def test_gabia_payment_billing_unit():
    assert "gabia/payment-billing" in _read(UNITS / "gabia_room_allocation.md")


def test_gabia_cross_domain_prohibition():
    assert "cross-domain 직접 import 금지" in _read(UNITS / "gabia_room_allocation.md")


def test_gabia_user_direct_required_declared():
    assert "USER_DIRECT_REQUIRED" in _read(UNITS / "gabia_room_allocation.md")


def test_gabia_blocked_session_declared():
    doc = _read(UNITS / "gabia_room_allocation.md")
    assert "BLOCKED" in doc and "session" in doc


def test_gabia_server_browser_guard_declared():
    assert "SERVER_BROWSER_GUARD" in _read(UNITS / "gabia_room_allocation.md")


# ── 5. G2B 집 배정 ──────────────────────────────────────────────────────────

def test_g2b_public_notice_unit():
    assert "g2b/public-notice" in _read(UNITS / "g2b_room_allocation.md")


def test_g2b_notice_detail_unit():
    assert "g2b/notice-detail" in _read(UNITS / "g2b_room_allocation.md")


def test_g2b_attachment_download_unit():
    assert "g2b/attachment-download" in _read(UNITS / "g2b_room_allocation.md")


def test_g2b_openapi_collector_unit():
    assert "g2b/openapi-collector" in _read(UNITS / "g2b_room_allocation.md")


def test_g2b_login_restricted_unit():
    assert "g2b/login-restricted" in _read(UNITS / "g2b_room_allocation.md")


def test_g2b_bid_analysis_unit():
    assert "g2b/bid-analysis" in _read(UNITS / "g2b_room_allocation.md")


def test_g2b_bid_submit_unit():
    assert "g2b/bid-submit" in _read(UNITS / "g2b_room_allocation.md")


def test_g2b_e_sign_unit():
    assert "g2b/e-sign" in _read(UNITS / "g2b_room_allocation.md")


def test_g2b_evidence_report_unit():
    assert "g2b/evidence-report" in _read(UNITS / "g2b_room_allocation.md")


def test_g2b_cross_domain_prohibition():
    assert "cross-domain 직접 import 금지" in _read(UNITS / "g2b_room_allocation.md")


def test_g2b_bid_submit_blocked():
    doc = _read(UNITS / "g2b_room_allocation.md")
    assert "BLOCKED" in doc and "투찰" in doc


def test_g2b_e_sign_blocked():
    doc = _read(UNITS / "g2b_room_allocation.md")
    assert "전자서명 자동화" in doc


def test_g2b_server_browser_guard_declared():
    assert "SERVER_BROWSER_GUARD" in _read(UNITS / "g2b_room_allocation.md")


# ── 6. 공통 도메인 집 배정 ───────────────────────────────────────────────────

def test_common_hiworks_declared():
    assert "Hiworks" in _read(UNITS / "common_domain_room_allocation.md")


def test_common_google_declared():
    assert "Google" in _read(UNITS / "common_domain_room_allocation.md")


def test_common_youtube_declared():
    assert "YouTube" in _read(UNITS / "common_domain_room_allocation.md")


def test_common_cad_declared():
    assert "CAD" in _read(UNITS / "common_domain_room_allocation.md")


def test_common_hwpx_declared():
    assert "HWPX" in _read(UNITS / "common_domain_room_allocation.md")


def test_common_doc_automation_declared():
    assert "문서 자동화" in _read(UNITS / "common_domain_room_allocation.md")


def test_common_attendance_declared():
    assert "출퇴근" in _read(UNITS / "common_domain_room_allocation.md")


def test_common_risk_assessment_declared():
    assert "위험성평가" in _read(UNITS / "common_domain_room_allocation.md")


def test_common_cross_domain_prohibition():
    assert "cross-domain 직접 import 금지" in _read(UNITS / "common_domain_room_allocation.md")


# ── 7. 공용시설 배정 ─────────────────────────────────────────────────────────

def test_facility_action_registry():
    assert "Action Registry" in _read(ARCH / "shared_facility_allocation.md")


def test_facility_approval_gate():
    assert "Approval Gate" in _read(ARCH / "shared_facility_allocation.md")


def test_facility_permission_model():
    assert "Permission Model" in _read(ARCH / "shared_facility_allocation.md")


def test_facility_workflow_task():
    assert "Workflow" in _read(ARCH / "shared_facility_allocation.md")


def test_facility_local_agent_gateway():
    assert "Local Agent Gateway" in _read(ARCH / "shared_facility_allocation.md")


def test_facility_browser_execution_gateway():
    assert "Browser Execution Gateway" in _read(ARCH / "shared_facility_allocation.md")


def test_facility_evidence_store():
    assert "Evidence Store" in _read(ARCH / "shared_facility_allocation.md")


def test_facility_report_store():
    assert "Report Store" in _read(ARCH / "shared_facility_allocation.md")


def test_facility_audit_log():
    assert "Audit Log" in _read(ARCH / "shared_facility_allocation.md")


def test_facility_admin_ops():
    assert "Admin Ops Center" in _read(ARCH / "shared_facility_allocation.md")


def test_facility_notification_center():
    assert "Notification Center" in _read(ARCH / "shared_facility_allocation.md")


# ── 8. 감사 스크립트 ─────────────────────────────────────────────────────────

def test_audit_script_importable():
    import tools.audits.app.audit_domain_room_allocation as m
    assert hasattr(m, "run_audit")


def test_audit_script_runs_and_passes():
    from tools.audits.app.audit_domain_room_allocation import run_audit
    report = run_audit()
    summary = report.summary()
    assert summary["failed"] == 0, f"Room allocation audit 실패: {summary['issues']}"


# ── 9. P0 게이트 regression ──────────────────────────────────────────────────

def test_forbidden_import_still_zero():
    p = ROOT / "data" / "codebase_layer_audit_latest.json"
    if not p.exists():
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    fi = [i for i in d.get("issues", []) if i["code"] == "FORBIDDEN_IMPORT"]
    assert len(fi) == 0, f"FORBIDDEN_IMPORT 위반: {fi}"


def test_security_pattern_still_zero():
    p = ROOT / "data" / "codebase_layer_audit_latest.json"
    if not p.exists():
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    sp = [i for i in d.get("issues", []) if i["code"] == "SECURITY_PATTERN"]
    assert len(sp) == 0, f"SECURITY_PATTERN 위반: {sp}"


def test_p1_router_thinness_still_zero_new_violations():
    p = ROOT / "data" / "codebase_layer_audit_latest.json"
    if not p.exists():
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    w = [i for i in d.get("issues", []) if i["code"] == "ROUTER_THINNESS" and i["severity"] == "warn"]
    assert len(w) == 0, f"ROUTER_THINNESS 신규 위반: {w}"


def test_p1_storage_boundary_still_zero_new_violations():
    p = ROOT / "data" / "codebase_layer_audit_latest.json"
    if not p.exists():
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    w = [i for i in d.get("issues", []) if i["code"] == "STORAGE_BOUNDARY" and i["severity"] == "warn"]
    assert len(w) == 0, f"STORAGE_BOUNDARY 신규 위반: {w}"
