"""Shared Warehouse Policy 구조 감사 테스트.

공용창고 정책 문서 존재·manifest 검사·금지 경로·domain 배정 검증.
기능 테스트 아님 — 정책 위반 감지 테스트만 포함.
data/sessions 파일 내용 열람 금지.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / "docs" / "architecture"


def _read(path: Path) -> str:
    assert path.exists(), f"문서 없음: {path}"
    return path.read_text(encoding="utf-8")


def _manifest() -> dict:
    p = ARCH / "shared_warehouse_manifest.json"
    assert p.exists(), "shared_warehouse_manifest.json 없음"
    return json.loads(p.read_text(encoding="utf-8"))


# ── 1. 필수 문서 존재 ────────────────────────────────────────────────────────

def test_doc_shared_warehouse_model_exists():
    assert (ARCH / "shared_warehouse_model.md").exists()


def test_doc_domain_warehouse_allocation_exists():
    assert (ARCH / "domain_warehouse_allocation.md").exists()


def test_doc_storage_boundary_policy_exists():
    assert (ARCH / "storage_boundary_policy.md").exists()


def test_doc_shared_warehouse_manifest_exists():
    assert (ARCH / "shared_warehouse_manifest.json").exists()


# ── 2. Manifest JSON parse ────────────────────────────────────────────────────

def test_manifest_is_parseable():
    m = _manifest()
    assert isinstance(m, dict)
    assert "version" in m


def test_manifest_has_warehouses():
    m = _manifest()
    assert "warehouses" in m
    assert isinstance(m["warehouses"], dict)


def test_manifest_has_blocked_paths():
    m = _manifest()
    assert "blocked_paths" in m


def test_manifest_has_blocked_file_patterns():
    m = _manifest()
    assert "blocked_file_patterns" in m


# ── 3. 필수 창고 존재 ────────────────────────────────────────────────────────

def test_warehouse_draft_exists():
    assert "draft" in _manifest()["warehouses"]


def test_warehouse_approval_exists():
    assert "approval" in _manifest()["warehouses"]


def test_warehouse_execution_plan_exists():
    assert "execution_plan" in _manifest()["warehouses"]


def test_warehouse_evidence_exists():
    assert "evidence" in _manifest()["warehouses"]


def test_warehouse_report_human_exists():
    assert "report_human" in _manifest()["warehouses"]


def test_warehouse_report_machine_exists():
    assert "report_machine" in _manifest()["warehouses"]


def test_warehouse_artifact_exists():
    assert "artifact" in _manifest()["warehouses"]


def test_warehouse_upload_exists():
    assert "upload" in _manifest()["warehouses"]


def test_warehouse_audit_log_exists():
    assert "audit_log" in _manifest()["warehouses"]


def test_warehouse_manual_visit_exists():
    assert "manual_visit" in _manifest()["warehouses"]


def test_warehouse_session_store_exists():
    assert "session_store" in _manifest()["warehouses"]


# ── 4. blocked_paths에 data/sessions 포함 ────────────────────────────────────

def test_blocked_paths_contains_sessions():
    assert "data/sessions" in _manifest()["blocked_paths"]


def test_session_policy_is_blocked():
    assert _manifest()["session_policy"] == "BLOCKED"


def test_session_store_warehouse_policy_blocked():
    m = _manifest()
    assert m["warehouses"]["session_store"]["policy"] == "BLOCKED"


# ── 5. manual_visit_policy READ_ONLY_EVIDENCE ────────────────────────────────

def test_manual_visit_policy_read_only_evidence():
    assert _manifest()["manual_visit_policy"] == "READ_ONLY_EVIDENCE"


def test_manual_visit_warehouse_read_only():
    m = _manifest()
    assert m["warehouses"]["manual_visit"]["policy"] == "READ_ONLY_EVIDENCE"


# ── 6. required task_id scoped paths ─────────────────────────────────────────

def test_required_task_scoped_paths_exist():
    paths = _manifest().get("required_task_scoped_paths", [])
    assert len(paths) >= 4


def test_task_scoped_drafts():
    paths = _manifest().get("required_task_scoped_paths", [])
    assert any("data/drafts" in p for p in paths)


def test_task_scoped_evidence():
    paths = _manifest().get("required_task_scoped_paths", [])
    assert any("data/evidence" in p for p in paths)


def test_task_scoped_artifacts():
    paths = _manifest().get("required_task_scoped_paths", [])
    assert any("data/artifacts" in p for p in paths)


def test_task_scoped_uploads():
    paths = _manifest().get("required_task_scoped_paths", [])
    assert any("data/uploads" in p for p in paths)


# ── 7. report/evidence/artifact 분리 ─────────────────────────────────────────

def test_report_paths_human_readable():
    rp = _manifest().get("report_paths", {})
    assert "docs/reports/" in rp.get("human_readable", "")


def test_report_paths_machine_readable():
    rp = _manifest().get("report_paths", {})
    assert "data/reports/" in rp.get("machine_readable", "")


def test_evidence_paths_exist():
    ep = _manifest().get("evidence_paths", {})
    assert "data/evidence/" in ep.get("standard", "")


# ── 8. domain allocation에 gabia/g2b 포함 ────────────────────────────────────

def test_domain_allocation_gabia():
    assert "gabia" in _read(ARCH / "domain_warehouse_allocation.md")


def test_domain_allocation_g2b():
    assert "g2b" in _read(ARCH / "domain_warehouse_allocation.md")


def test_domain_allocation_hiworks():
    assert "hiworks" in _read(ARCH / "domain_warehouse_allocation.md")


def test_domain_allocation_google():
    assert "google" in _read(ARCH / "domain_warehouse_allocation.md")


def test_domain_allocation_youtube():
    assert "youtube" in _read(ARCH / "domain_warehouse_allocation.md")


def test_domain_allocation_eum():
    assert "eum" in _read(ARCH / "domain_warehouse_allocation.md")


# ── 9. cad/hwpx/document_automation/safety_docs 포함 ─────────────────────────

def test_domain_allocation_cad():
    assert "cad" in _read(ARCH / "domain_warehouse_allocation.md")


def test_domain_allocation_hwpx():
    assert "hwpx" in _read(ARCH / "domain_warehouse_allocation.md")


def test_domain_allocation_document_automation():
    assert "document_automation" in _read(ARCH / "domain_warehouse_allocation.md")


def test_domain_allocation_safety_docs():
    assert "safety_docs" in _read(ARCH / "domain_warehouse_allocation.md")


# ── 10. blocked_file_patterns ────────────────────────────────────────────────

def test_blocked_pattern_cookie():
    assert "*cookie*" in _manifest()["blocked_file_patterns"]


def test_blocked_pattern_session():
    assert "*session*" in _manifest()["blocked_file_patterns"]


def test_blocked_pattern_token():
    assert "*token*" in _manifest()["blocked_file_patterns"]


def test_blocked_pattern_password():
    assert "*password*" in _manifest()["blocked_file_patterns"]


def test_blocked_pattern_env():
    assert "*.env" in _manifest()["blocked_file_patterns"]


def test_blocked_pattern_pem():
    assert "*.pem" in _manifest()["blocked_file_patterns"]


def test_blocked_pattern_key():
    assert "*.key" in _manifest()["blocked_file_patterns"]


# ── 11. secret/env/pem/key 저장 금지 문구 ────────────────────────────────────

def test_storage_boundary_policy_session_forbidden():
    doc = _read(ARCH / "storage_boundary_policy.md")
    assert "data/sessions" in doc and "BLOCKED" in doc


def test_storage_boundary_policy_session_cookie_token_password():
    doc = _read(ARCH / "storage_boundary_policy.md")
    assert "session/cookie/token/password 저장 금지" in doc


def test_storage_boundary_policy_storage_boundary_gate():
    assert "STORAGE_BOUNDARY" in _read(ARCH / "storage_boundary_policy.md")


def test_shared_warehouse_model_session_forbidden():
    doc = _read(ARCH / "shared_warehouse_model.md")
    assert "BLOCKED" in doc and "봉인" in doc


def test_shared_warehouse_model_session_cookie_token():
    assert "session/cookie/token/password" in _read(ARCH / "shared_warehouse_model.md")


# ── 12. data/sessions read 금지 문구 ─────────────────────────────────────────

def test_model_sessions_read_forbidden():
    doc = _read(ARCH / "shared_warehouse_model.md")
    assert "읽기" in doc and "data/sessions" in doc


def test_boundary_sessions_parsing_forbidden():
    doc = _read(ARCH / "storage_boundary_policy.md")
    assert "파싱" in doc or "재사용" in doc


# ── 13. 감사 스크립트 PASS ────────────────────────────────────────────────────

def test_warehouse_audit_script_importable():
    import tools.audits.app.audit_shared_warehouse_policy as m
    assert hasattr(m, "run_audit")


def test_warehouse_audit_script_runs_and_passes():
    from tools.audits.app.audit_shared_warehouse_policy import run_audit
    report = run_audit()
    summary = report.summary()
    assert summary["failed"] == 0, f"Warehouse audit 실패: {summary['issues']}"


# ── 14. 기존 governance 문서 충돌 없음 ───────────────────────────────────────

def test_storage_audit_evidence_model_still_exists():
    assert (ARCH / "storage_audit_evidence_model.md").exists()


def test_governance_gate_matrix_still_has_storage_boundary():
    doc = _read(ARCH / "governance_gate_matrix.md")
    assert "STORAGE_BOUNDARY" in doc


def test_approval_policy_fields_in_manifest():
    approval = _manifest().get("approval_policy", {})
    for field in ("approver", "timestamp", "scope", "expiry", "decision"):
        assert field in approval.get("required_fields", []), f"approval_policy 필드 누락: {field}"


def test_audit_policy_append_only():
    audit_p = _manifest().get("audit_policy", {})
    assert audit_p.get("mode") == "APPEND_ONLY"
    assert audit_p.get("deletion") == "BLOCKED"


# ── 15. P0/P1 게이트 regression ──────────────────────────────────────────────

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


def test_p1_storage_boundary_still_zero_new_violations():
    p = ROOT / "data" / "codebase_layer_audit_latest.json"
    if not p.exists():
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    w = [i for i in d.get("issues", []) if i["code"] == "STORAGE_BOUNDARY" and i["severity"] == "warn"]
    assert len(w) == 0, f"STORAGE_BOUNDARY 신규 위반: {w}"
