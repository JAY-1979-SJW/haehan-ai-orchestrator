"""커밋 훅의 필수 게이트 연결이 빠지지 않게 고정한다.

2026-10-08 사고: 세션 시작 훅이 돌린 install_git_hooks.py 가 추적 파일 .githooks/pre-commit.orig 를 오래된 내장 템플릿으로
덮어썼고, `git add -A` 가 그것을 실어 PR #162 로 병합돼 이동 사전점검·G11·G15·G17·G16·G5·R1·G12 연결 96줄이 master 에서 사라졌다.
"""

from pathlib import Path

from tools.hooks import install_git_hooks as ih
from tools.quality import module_quality_gate_checks_repo as checks

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_GATES = (
    "move_preflight.py",
    "tool_home_gate.py",
    "flat_root_gate.py",
    "bundle_path_gate.py",
    "folder_gate.py",
    "root_calc_gate.py",
    "audit_r1_api_contract_gate.py",
    "dup_gate.py",
)


def test_pre_commit_orig_wires_every_required_gate():
    text = (ROOT / ".githooks" / "pre-commit.orig").read_text(encoding="utf-8")
    assert text.strip() and REQUIRED_GATES  # 파일이 비었거나 목록이 비어 공허하게 통과하는 것을 막는다
    missing = [g for g in REQUIRED_GATES if g not in text]
    assert not missing, f".githooks/pre-commit.orig 에 게이트 연결이 없다: {missing}"


def test_required_hook_needles_list_every_gate():
    needles = dict(checks._REQUIRED_HOOK_NEEDLES)["pre-commit.orig"]
    assert REQUIRED_GATES and needles  # 비교 대상이 비어 공허하게 통과하는 것을 막는다
    assert all(g.removesuffix(".py") in needles for g in REQUIRED_GATES)


def test_installer_never_overwrites_an_existing_hook(tmp_path, monkeypatch):
    monkeypatch.setattr(ih, "HOOKS_DIR", tmp_path)
    (tmp_path / "pre-commit.orig").write_text("TRACKED CONTENT", encoding="utf-8")
    ih.install("pre-commit.orig", "STALE TEMPLATE")
    assert (tmp_path / "pre-commit.orig").read_text(encoding="utf-8") == "TRACKED CONTENT"


def test_installer_creates_a_missing_hook(tmp_path, monkeypatch):
    monkeypatch.setattr(ih, "HOOKS_DIR", tmp_path)
    ih.install("pre-push", "NEW HOOK")
    assert (tmp_path / "pre-push").read_text(encoding="utf-8") == "NEW HOOK"
