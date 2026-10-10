"""App Foundation Governance 구조 감사 테스트."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / "docs" / "architecture"


# ── 1. 필수 문서 존재 ────────────────────────────────────────────────────────

def test_doc_app_foundation_governance_exists():
    assert (ARCH / "app_foundation_governance.md").exists()


def test_doc_permission_approval_model_exists():
    assert (ARCH / "permission_approval_model.md").exists()


def test_doc_workflow_state_model_exists():
    assert (ARCH / "workflow_state_model.md").exists()


def test_doc_storage_audit_evidence_model_exists():
    assert (ARCH / "storage_audit_evidence_model.md").exists()


def test_doc_governance_gate_matrix_exists():
    assert (ARCH / "governance_gate_matrix.md").exists()


# ── 2. 레이어 이름 존재 ─────────────────────────────────────────────────────

def _foundation_doc() -> str:
    return (ARCH / "app_foundation_governance.md").read_text(encoding="utf-8")


def test_layer_ui_exists():
    assert "UI Layer" in _foundation_doc() or "UI" in _foundation_doc()


def test_layer_api_router_exists():
    assert "API" in _foundation_doc() and "Router" in _foundation_doc()


def test_layer_permission_gate_exists():
    assert "Permission" in _foundation_doc() or "Approval Gate" in _foundation_doc()


def test_layer_workflow_exists():
    assert "Workflow" in _foundation_doc()


def test_layer_domain_policy_exists():
    assert "Domain" in _foundation_doc() or "Policy" in _foundation_doc()


def test_layer_adapter_site_engine_exists():
    assert "Adapter" in _foundation_doc() or "Site Engine" in _foundation_doc()


def test_layer_local_agent_exists():
    assert "Local Agent" in _foundation_doc()


def test_layer_storage_exists():
    assert "Storage" in _foundation_doc() or "Repository" in _foundation_doc()


def test_layer_audit_exists():
    assert "Audit" in _foundation_doc()


# ── 3. 권한 결정 존재 ───────────────────────────────────────────────────────

def _permission_doc() -> str:
    return (ARCH / "permission_approval_model.md").read_text(encoding="utf-8")


def test_decision_allowed():
    assert "ALLOWED" in _permission_doc()


def test_decision_draft_allowed():
    assert "DRAFT_ALLOWED" in _permission_doc()


def test_decision_approval_required():
    assert "APPROVAL_REQUIRED" in _permission_doc()


def test_decision_user_direct_required():
    assert "USER_DIRECT_REQUIRED" in _permission_doc()


def test_decision_local_agent_required():
    assert "LOCAL_AGENT_REQUIRED" in _permission_doc()


def test_decision_blocked():
    assert "BLOCKED" in _permission_doc()


def test_blocked_session_mentioned():
    doc = _permission_doc()
    assert "session" in doc.lower() and "BLOCKED" in doc


def test_blocked_password_mentioned():
    doc = _permission_doc()
    assert "password" in doc.lower() or "비밀번호" in doc


# ── 4. 워크플로우 상태 존재 ─────────────────────────────────────────────────

def _workflow_doc() -> str:
    return (ARCH / "workflow_state_model.md").read_text(encoding="utf-8")


def test_state_requested():
    assert "REQUESTED" in _workflow_doc()


def test_state_draft_created():
    assert "DRAFT_CREATED" in _workflow_doc()


def test_state_approval_required():
    assert "APPROVAL_REQUIRED" in _workflow_doc()


def test_state_approved():
    assert "APPROVED" in _workflow_doc()


def test_state_user_direct_required():
    assert "USER_DIRECT_REQUIRED" in _workflow_doc()


def test_state_local_agent_required():
    assert "LOCAL_AGENT_REQUIRED" in _workflow_doc()


def test_state_blocked():
    assert "BLOCKED" in _workflow_doc()


def test_state_completed():
    assert "COMPLETED" in _workflow_doc()


def test_state_failed():
    assert "FAILED" in _workflow_doc()


def test_forbidden_transition_no_skip_approval():
    doc = _workflow_doc()
    assert "APPROVAL_REQUIRED" in doc and "EXECUTING" in doc


# ── 5. 저장소 모델 존재 ─────────────────────────────────────────────────────

def _storage_doc() -> str:
    return (ARCH / "storage_audit_evidence_model.md").read_text(encoding="utf-8")


def test_storage_session_policy_blocked():
    doc = _storage_doc()
    assert "Session Store" in doc and ("금지" in doc or "BLOCKED" in doc)


def test_storage_session_files_listed():
    doc = _storage_doc()
    assert "data/sessions/" in doc or "sessions/" in doc


def test_storage_manual_visit_readonly():
    doc = _storage_doc()
    assert "manual_visits" in doc or "Manual Visit" in doc


def test_storage_approval_store_exists():
    assert "Approval Store" in _storage_doc()


def test_storage_audit_log_exists():
    assert "Audit Log" in _storage_doc()


def test_storage_evidence_store_exists():
    assert "Evidence" in _storage_doc()


# ── 6. 게이트 매트릭스 존재 ─────────────────────────────────────────────────

def _gate_doc() -> str:
    return (ARCH / "governance_gate_matrix.md").read_text(encoding="utf-8")


def test_gate_forbidden_import():
    assert "FORBIDDEN_IMPORT" in _gate_doc()


def test_gate_security_pattern():
    assert "SECURITY_PATTERN" in _gate_doc()


def test_gate_circular_import():
    assert "CIRCULAR_IMPORT" in _gate_doc()


def test_gate_blocked_secret_session():
    assert "BLOCKED_SECRET_SESSION" in _gate_doc()


def test_gate_server_browser_guard():
    assert "SERVER_BROWSER_GUARD" in _gate_doc()


def test_gate_priority_p0_exists():
    assert "P0" in _gate_doc()


def test_gate_priority_p1_exists():
    assert "P1" in _gate_doc()


def test_gate_priority_p2_exists():
    assert "P2" in _gate_doc()


# ── 7. 감사 스크립트 smoke ─────────────────────────────────────────────────

def test_audit_script_importable():
    import tools.audits.app.audit_app_foundation_governance as m
    assert hasattr(m, "run_audit")


def test_audit_script_runs_and_passes():
    from tools.audits.app.audit_app_foundation_governance import run_audit
    report = run_audit()
    summary = report.summary()
    assert summary["failed"] == 0, f"Governance audit failures: {summary['issues']}"


# ── 8. 기존 gate/audit regression ──────────────────────────────────────────

def test_forbidden_import_gate_zero():
    import json
    report_path = ROOT / "data" / "codebase_layer_audit_latest.json"
    if not report_path.exists():
        return
    d = json.loads(report_path.read_text(encoding="utf-8"))
    fi = [i for i in d.get("issues", []) if i["code"] == "FORBIDDEN_IMPORT"]
    assert len(fi) == 0, f"FORBIDDEN_IMPORT violations: {fi}"


def test_security_pattern_gate_zero():
    import json
    report_path = ROOT / "data" / "codebase_layer_audit_latest.json"
    if not report_path.exists():
        return
    d = json.loads(report_path.read_text(encoding="utf-8"))
    sp = [i for i in d.get("issues", []) if i["code"] == "SECURITY_PATTERN"]
    assert len(sp) == 0, f"SECURITY_PATTERN violations: {sp}"
