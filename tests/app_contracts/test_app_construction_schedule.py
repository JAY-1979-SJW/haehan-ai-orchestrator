"""App Construction Schedule 문서 구조 감사 테스트.

공정 문서 존재·내용·Phase 완료 기준 검증.
기능 테스트 아님 — 문서 정책 위반 감지만.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / "docs" / "architecture"
REPORTS = ROOT / "docs" / "reports"


def _read(path: Path) -> str:
    assert path.exists(), f"문서 없음: {path}"
    return path.read_text(encoding="utf-8")


# ── 1. 필수 문서 존재 ────────────────────────────────────────────────────────

def test_master_schedule_exists():
    assert (ARCH / "app_construction_master_schedule.md").exists()


def test_as_built_matrix_exists():
    assert (ARCH / "app_construction_as_built_matrix.md").exists()


def test_completion_checklist_exists():
    assert (ARCH / "app_construction_completion_checklist.md").exists()


def test_next_sequence_exists():
    assert (ARCH / "app_construction_next_sequence.md").exists()


def test_punch_list_report_exists():
    assert (REPORTS / "app_construction_punch_list_20260515.md").exists()


def test_schedule_report_exists():
    assert (REPORTS / "app_construction_schedule_documentation_20260515.md").exists()


# ── 2. Master Schedule Phase 목록 ────────────────────────────────────────────

def test_master_has_phase_a():
    assert "Phase A" in _read(ARCH / "app_construction_master_schedule.md")


def test_master_has_phase_b():
    assert "Phase B" in _read(ARCH / "app_construction_master_schedule.md")


def test_master_has_phase_c():
    assert "Phase C" in _read(ARCH / "app_construction_master_schedule.md")


def test_master_has_phase_d():
    assert "Phase D" in _read(ARCH / "app_construction_master_schedule.md")


def test_master_has_phase_e_to_i():
    doc = _read(ARCH / "app_construction_master_schedule.md")
    for phase in ["Phase E", "Phase F", "Phase G", "Phase H", "Phase I"]:
        assert phase in doc, f"{phase} 없음"


def test_master_has_foundation_code():
    assert "FOUNDATION" in _read(ARCH / "app_construction_master_schedule.md")


def test_master_has_structural_code():
    assert "STRUCTURAL" in _read(ARCH / "app_construction_master_schedule.md")


def test_master_has_dod():
    assert "DoD" in _read(ARCH / "app_construction_master_schedule.md")


# ── 3. Phase A/B 완료 표시 ───────────────────────────────────────────────────

def test_phase_a_shows_complete():
    doc = _read(ARCH / "app_construction_master_schedule.md")
    assert "완료" in doc and "Phase A" in doc


def test_phase_a_has_layer_audit():
    assert "codebase_layer_audit.py" in _read(ARCH / "app_construction_master_schedule.md")


def test_phase_b_has_warehouse_model():
    assert "shared_warehouse_model.md" in _read(ARCH / "app_construction_master_schedule.md")


def test_phase_b_has_storage_boundary():
    assert "storage_boundary_policy.md" in _read(ARCH / "app_construction_master_schedule.md")


# ── 4. As-Built Matrix 도메인 포함 ───────────────────────────────────────────

def test_as_built_has_gabia():
    assert "gabia" in _read(ARCH / "app_construction_as_built_matrix.md").lower()


def test_as_built_has_hiworks():
    assert "hiworks" in _read(ARCH / "app_construction_as_built_matrix.md").lower()


def test_as_built_has_eum():
    assert "eum" in _read(ARCH / "app_construction_as_built_matrix.md").lower()


def test_as_built_has_g2b():
    assert "g2b" in _read(ARCH / "app_construction_as_built_matrix.md").lower()


def test_as_built_has_warehouse_section():
    doc = _read(ARCH / "app_construction_as_built_matrix.md")
    assert "drafts" in doc and "evidence" in doc


def test_as_built_session_blocked():
    doc = _read(ARCH / "app_construction_as_built_matrix.md")
    assert "BLOCKED" in doc and "sessions" in doc


# ── 5. Completion Checklist Phase 포함 ───────────────────────────────────────

def test_checklist_has_all_phases():
    doc = _read(ARCH / "app_construction_completion_checklist.md")
    for phase in ["Phase A", "Phase B", "Phase C", "Phase D", "Phase E", "Phase F", "Phase G", "Phase H", "Phase I"]:
        assert phase in doc, f"{phase} 없음"


def test_checklist_has_forbidden_import_condition():
    assert "FORBIDDEN_IMPORT=0" in _read(ARCH / "app_construction_completion_checklist.md")


def test_checklist_has_security_pattern_condition():
    assert "SECURITY_PATTERN=0" in _read(ARCH / "app_construction_completion_checklist.md")


def test_checklist_has_dod_declaration():
    assert "완료 선언 조건" in _read(ARCH / "app_construction_completion_checklist.md")


# ── 6. Next Sequence 키워드 ──────────────────────────────────────────────────

def test_next_sequence_has_g2b():
    assert "G2B" in _read(ARCH / "app_construction_next_sequence.md")


def test_next_sequence_has_eum():
    assert "Eum" in _read(ARCH / "app_construction_next_sequence.md")


def test_next_sequence_has_gabia():
    assert "Gabia" in _read(ARCH / "app_construction_next_sequence.md")


def test_next_sequence_has_dod():
    assert "DoD" in _read(ARCH / "app_construction_next_sequence.md")


# ── 7. Punch List 내용 ───────────────────────────────────────────────────────

def test_punch_list_has_high_priority():
    assert "HIGH" in _read(REPORTS / "app_construction_punch_list_20260515.md")


def test_punch_list_has_g2b():
    assert "G2B" in _read(REPORTS / "app_construction_punch_list_20260515.md")


def test_punch_list_has_eum():
    doc = _read(REPORTS / "app_construction_punch_list_20260515.md")
    assert "Eum" in doc or "eum" in doc


# ── 8. 감사 스크립트 ──────────────────────────────────────────────────────────

def test_audit_script_importable():
    import tools.audits.app.audit_app_construction_schedule as m
    assert hasattr(m, "run_audit")


def test_audit_script_runs_and_passes():
    from tools.audits.app.audit_app_construction_schedule import run_audit
    report = run_audit()
    summary = report.summary()
    assert summary["failed"] == 0, f"Construction schedule audit 실패: {summary['issues']}"


# ── 9. 기존 거버넌스 문서 충돌 없음 ─────────────────────────────────────────

def test_governance_gate_matrix_intact():
    assert (ARCH / "governance_gate_matrix.md").exists()


def test_shared_warehouse_model_intact():
    assert (ARCH / "shared_warehouse_model.md").exists()


def test_domain_room_allocation_rule_intact():
    assert (ARCH / "domain_room_allocation_rule.md").exists()


# ── 10. P0/P1 게이트 regression ──────────────────────────────────────────────

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
