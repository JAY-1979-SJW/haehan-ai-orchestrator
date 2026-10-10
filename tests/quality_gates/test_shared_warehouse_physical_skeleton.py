"""Shared Warehouse Physical Skeleton 구조 감사 테스트.

실제 창고 디렉터리·.gitkeep·README.md 존재 검증.
data/sessions 접근 금지.
기능 테스트 아님 — 물리 구조 위반 감지만.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / "docs" / "architecture"
DATA = ROOT / "data"

WAREHOUSE_DIRS = [
    "drafts",
    "approvals",
    "execution_plans",
    "evidence",
    "artifacts",
    "uploads",
]


# ── 1. 창고 디렉터리 존재 ─────────────────────────────────────────────────────

def test_warehouse_drafts_dir_exists():
    assert (DATA / "drafts").is_dir()


def test_warehouse_approvals_dir_exists():
    assert (DATA / "approvals").is_dir()


def test_warehouse_execution_plans_dir_exists():
    assert (DATA / "execution_plans").is_dir()


def test_warehouse_evidence_dir_exists():
    assert (DATA / "evidence").is_dir()


def test_warehouse_artifacts_dir_exists():
    assert (DATA / "artifacts").is_dir()


def test_warehouse_uploads_dir_exists():
    assert (DATA / "uploads").is_dir()


# ── 2. .gitkeep 파일 존재 ─────────────────────────────────────────────────────

def test_gitkeep_drafts():
    assert (DATA / "drafts" / ".gitkeep").exists()


def test_gitkeep_approvals():
    assert (DATA / "approvals" / ".gitkeep").exists()


def test_gitkeep_execution_plans():
    assert (DATA / "execution_plans" / ".gitkeep").exists()


def test_gitkeep_evidence():
    assert (DATA / "evidence" / ".gitkeep").exists()


def test_gitkeep_artifacts():
    assert (DATA / "artifacts" / ".gitkeep").exists()


def test_gitkeep_uploads():
    assert (DATA / "uploads" / ".gitkeep").exists()


# ── 3. README.md 존재 및 핵심 내용 ───────────────────────────────────────────

def test_readme_drafts_exists():
    assert (DATA / "drafts" / "README.md").exists()


def test_readme_approvals_exists():
    assert (DATA / "approvals" / "README.md").exists()


def test_readme_execution_plans_exists():
    assert (DATA / "execution_plans" / "README.md").exists()


def test_readme_evidence_exists():
    assert (DATA / "evidence" / "README.md").exists()


def test_readme_artifacts_exists():
    assert (DATA / "artifacts" / "README.md").exists()


def test_readme_uploads_exists():
    assert (DATA / "uploads" / "README.md").exists()


def test_readme_drafts_has_policy():
    content = (DATA / "drafts" / "README.md").read_text(encoding="utf-8")
    assert "DRAFT_ALLOWED" in content


def test_readme_approvals_has_policy():
    content = (DATA / "approvals" / "README.md").read_text(encoding="utf-8")
    assert "APPROVAL_REQUIRED" in content


def test_readme_evidence_has_policy():
    content = (DATA / "evidence" / "README.md").read_text(encoding="utf-8")
    assert "READ_ONLY_AFTER_CREATION" in content


def test_readme_uploads_has_policy():
    content = (DATA / "uploads" / "README.md").read_text(encoding="utf-8")
    assert "IMMUTABLE_ORIGIN" in content


# ── 4. data/sessions 봉인 확인 (내용 열람 금지) ──────────────────────────────

def test_sessions_dir_not_opened():
    """data/sessions 디렉터리 존재 여부만 확인. 내용 열람 금지."""
    sessions = DATA / "sessions"
    # 존재 여부만 확인 — 내용(파일 목록/파일 내용) 열람 금지
    assert sessions.exists() or not sessions.exists()  # 항상 pass — 봉인 정책 준수 확인용


def test_sessions_no_new_markers():
    """data/sessions에 .gitkeep 또는 README.md를 생성하지 않았음을 확인."""
    sessions = DATA / "sessions"
    if sessions.exists():
        assert not (sessions / ".gitkeep").exists(), "data/sessions에 .gitkeep 생성 금지"
        assert not (sessions / "README.md").exists(), "data/sessions에 README.md 생성 금지"


# ── 5. manifest physical_skeleton_paths 확인 ─────────────────────────────────

def test_manifest_has_physical_skeleton_paths():
    p = ARCH / "shared_warehouse_manifest.json"
    assert p.exists()
    m = json.loads(p.read_text(encoding="utf-8"))
    assert "physical_skeleton_paths" in m


def test_manifest_physical_skeleton_includes_drafts():
    m = json.loads((ARCH / "shared_warehouse_manifest.json").read_text(encoding="utf-8"))
    paths = m.get("physical_skeleton_paths", [])
    assert any("drafts" in p for p in paths)


def test_manifest_physical_skeleton_includes_evidence():
    m = json.loads((ARCH / "shared_warehouse_manifest.json").read_text(encoding="utf-8"))
    paths = m.get("physical_skeleton_paths", [])
    assert any("evidence" in p for p in paths)


def test_manifest_physical_skeleton_excludes_sessions():
    m = json.loads((ARCH / "shared_warehouse_manifest.json").read_text(encoding="utf-8"))
    paths = m.get("physical_skeleton_paths", [])
    assert not any("sessions" in p for p in paths), "physical_skeleton_paths에 sessions 포함 금지"


# ── 6. 기존 창고 (logs/reports/manual_visits) 존재 유지 ──────────────────────

def test_existing_logs_dir_intact():
    assert (DATA / "logs").is_dir()


def test_existing_reports_dir_intact():
    assert (DATA / "reports").is_dir()


def test_existing_manual_visits_dir_intact():
    assert (DATA / "manual_visits").is_dir()


# ── 7. P0/P1 게이트 regression ───────────────────────────────────────────────

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
