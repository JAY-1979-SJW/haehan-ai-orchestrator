"""skeleton_gate.py(① 커밋 게이트) + registry_sync.py(② 동기화 도구) 검증(깨뜨리기) 테스트.

docs/specs/2026-09-24_skeleton_map_crosscheck_gate.md '검증(깨뜨리기)' 항목을 그대로 재현한다.
실제 저장소가 아니라 tmp_path 에 만든 독립 git 저장소에서 돈다(속도·격리 목적).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ops.code_map import registry_sync, skeleton_gate  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)


def _write(repo: Path, rel: str, content: str = "x = 1\n") -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _registry(repo: Path) -> dict:
    return {"files": {}}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "test@example.com")
    _git(r, "config", "user.name", "Test")
    (r / "configs").mkdir()
    (r / "configs" / "module_registry.json").write_text(
        json.dumps(_registry(r), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    (r / "configs" / "module_boundaries.json").write_text(
        json.dumps({"modules": []}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


def _evaluate_ok(repo: Path) -> bool:
    ok, _results = skeleton_gate.evaluate(root=repo)
    return ok


# ── 1. 새 .py 추가 + 정본 미갱신 → FAIL ────────────────────────────────
def test_new_file_without_registry_entry_fails(repo: Path):
    _write(repo, "foo.py")
    _git(repo, "add", "-A")
    assert _evaluate_ok(repo) is False


# ── --fix 후 → PASS ────────────────────────────────────────────────
def test_fix_then_passes(repo: Path):
    _write(repo, "foo.py")
    _git(repo, "add", "-A")
    assert _evaluate_ok(repo) is False

    assert registry_sync.fix(root=repo) == 0
    _git(repo, "add", "-A")
    assert _evaluate_ok(repo) is True


# ── 파일 삭제 + 정본 유지 → FAIL ───────────────────────────────────
def test_delete_file_keep_registry_entry_fails(repo: Path):
    _write(repo, "foo.py")
    _git(repo, "add", "-A")
    registry_sync.fix(root=repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add foo")
    assert _evaluate_ok(repo) is True

    (repo / "foo.py").unlink()
    _git(repo, "add", "-A")  # stages deletion; registry entry for foo.py untouched
    assert _evaluate_ok(repo) is False


# ── 이동 → FAIL → fix → PASS (정본 값 유지) ─────────────────────────
def test_rename_fails_then_fix_preserves_value(repo: Path):
    _write(repo, "foo.py")
    _git(repo, "add", "-A")
    registry_sync.fix(root=repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add foo")

    doc = registry_sync.load_registry(repo)
    old_value = dict(doc["files"]["foo.py"])
    # 사람이 확정한 값처럼 override 로 표시(값 보존 확인용)
    old_value["reason"] = "커스텀 확정값"
    doc["files"]["foo.py"] = old_value
    registry_sync.save_registry(doc, repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "custom classify")

    _git(repo, "mv", "foo.py", "bar.py")
    assert _evaluate_ok(repo) is False

    assert registry_sync.fix(root=repo) == 0
    _git(repo, "add", "-A")
    assert _evaluate_ok(repo) is True

    doc2 = registry_sync.load_registry(repo)
    assert "foo.py" not in doc2["files"]
    assert doc2["files"]["bar.py"]["reason"] == "커스텀 확정값"


# ── 선언 모듈 경로 없음 → FAIL ──────────────────────────────────────
def test_missing_declared_module_boundary_path_fails(repo: Path):
    bounds = {
        "modules": [
            {"name": "demo", "paths": ["does_not_exist.py"]},
        ]
    }
    (repo / "configs" / "module_boundaries.json").write_text(
        json.dumps(bounds, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    assert _evaluate_ok(repo) is False


# ── 우회: trailer/환경변수 → PASS + 감사 기록 ───────────────────────
def test_bypass_env_var_passes_and_logs(repo: Path, monkeypatch):
    _write(repo, "foo.py")
    _git(repo, "add", "-A")
    assert _evaluate_ok(repo) is False

    logged = {}

    def fake_log_op(op_name, **kw):
        logged["op_name"] = op_name
        logged.update(kw)

    monkeypatch.setattr("scripts.op_log.log_op", fake_log_op, raising=False)
    monkeypatch.setenv("SKELETON_GATE_SKIP_REASON", "테스트 우회")

    exit_code = skeleton_gate.run(root=repo)
    assert exit_code == 0
    assert logged.get("op_name") == "skeleton_gate_bypass"
    assert "테스트 우회" in logged.get("message", "")


# ── 2회 실행 동일(멱등) ──────────────────────────────────────────────
def test_idempotent_double_run(repo: Path):
    _write(repo, "foo.py")
    _git(repo, "add", "-A")
    registry_sync.fix(root=repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add foo")

    ok1, results1 = skeleton_gate.evaluate(root=repo)
    ok2, results2 = skeleton_gate.evaluate(root=repo)
    assert ok1 is True and ok2 is True
    assert [r[0:2] for r in results1] == [r[0:2] for r in results2]

    # registry_sync --check 도 두 번 실행 동일
    assert registry_sync.check(root=repo) == registry_sync.check(root=repo) == 0


def test_registry_sync_check_reports_missing_and_ghost(repo: Path):
    _write(repo, "foo.py")
    _git(repo, "add", "-A")
    assert registry_sync.check(root=repo) == 1  # foo.py missing from registry

    registry_sync.fix(root=repo)
    _git(repo, "add", "-A")
    assert registry_sync.check(root=repo) == 0

    # ghost: registry entry without a tracked file
    doc = registry_sync.load_registry(repo)
    doc["files"]["ghost.py"] = {"layer": "L4", "role": "generic", "domain": "common"}
    registry_sync.save_registry(doc, repo)
    assert registry_sync.check(root=repo) == 1
