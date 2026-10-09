"""skeleton_gate.py(① 커밋 게이트) + registry_sync.py(② 동기화 도구) 검증(깨뜨리기) 테스트.

docs/specs/2026-09-24_skeleton_map_crosscheck_gate.md '검증(깨뜨리기)' 항목을 그대로 재현한다.
실제 저장소가 아니라 tmp_path 에 만든 독립 git 저장소에서 돈다(속도·격리 목적).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.code_map import registry_sync, skeleton_gate  # noqa: E402


def _git(repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    run_env = {**os.environ, **env} if env else None
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=run_env,
    )


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

    monkeypatch.setattr("scripts.common.op_log.log_op", fake_log_op, raising=False)
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


# ── 리뷰 반영 신규 테스트 ────────────────────────────────────────────────


def test_cp949_env_no_crash_with_korean_filename(repo: Path):
    """PYTHONUTF8=0(+ cp949 IO) 환경에서도 한글 파일명/내용이 깨지거나 크래시하지 않는다."""
    env = {"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp949", "PYTHONLEGACYWINDOWSSTDIO": "1"}
    _write(repo, "한글모듈.py", "# 한글 주석\nx = 1\n")
    _git(repo, "add", "-A", env=env)

    # 평가 자체는 파이썬 프로세스 내부 실행(subprocess 로 git 만 부름) — 크래시 없이 완주해야 한다
    ok, results = skeleton_gate.evaluate(root=repo)
    assert ok is False  # 정본 미등록이라 FAIL 이지만, 크래시가 아니라 정상 판정이어야 함
    all_fails = [f for _n, _ok, fails in results for f in fails]
    assert any("한글모듈.py" in f for f in all_fails)

    registry_sync.fix(root=repo)
    _git(repo, "add", "-A")
    ok2, _ = skeleton_gate.evaluate(root=repo)
    assert ok2 is True


def test_perf_smoke_200_staged_files(repo: Path):
    """200개 스테이지 .py 파일이 있어도 평가가 합리적인 시간(넉넉하게 10초) 안에 끝난다."""
    for i in range(200):
        _write(repo, f"gen/mod_{i:04d}.py", f"x = {i}\n")
    _git(repo, "add", "-A")
    registry_sync.fix(root=repo)
    _git(repo, "add", "-A")

    t0 = time.perf_counter()
    ok, _results = skeleton_gate.evaluate(root=repo)
    elapsed = time.perf_counter() - t0

    assert ok is True
    assert elapsed < 10.0, f"200개 파일 평가에 {elapsed:.2f}s — 너무 느립니다"


def test_forbidden_import_scan_skips_irrelevant_files(repo: Path):
    """금지 import 쌍의 소스 prefix 와 무관한 파일은 내용 스캔 대상에서 제외된다(성능 최적화 확인)."""
    _write(repo, "some/random/module.py", "import os\n")
    _git(repo, "add", "-A")
    fails = skeleton_gate.check_forbidden_imports(repo, skeleton_gate._name_status(repo))
    assert fails == []


def test_bypass_logs_to_main_repo_root_not_worktree(repo: Path, monkeypatch):
    """git worktree 안에서 실행돼도 우회 로그는 메인 저장소의 data/logs/ops.log 에 남는다."""
    # repo 를 '메인 저장소'로 두고, 그 worktree(별도 디렉터리)에서 skeleton_gate 를 돌린다.
    _git(repo, "commit", "--allow-empty", "-q", "-m", "base for worktree")
    worktree_dir = repo.parent / "wt_bypass"
    wt = _git(repo, "worktree", "add", "-q", str(worktree_dir), "-b", "wt-branch")
    assert wt.returncode == 0, wt.stderr

    _write(worktree_dir, "foo.py")
    _git(worktree_dir, "add", "-A")

    monkeypatch.setenv("SKELETON_GATE_SKIP_REASON", "worktree 테스트 우회")
    exit_code = skeleton_gate.run(root=worktree_dir)
    assert exit_code == 0

    main_log = repo / "data" / "logs" / "ops.log"
    wt_log = worktree_dir / "data" / "logs" / "ops.log"
    assert main_log.exists(), "메인 저장소 ops.log 에 우회 기록이 남아야 합니다"
    assert "worktree 테스트 우회" in main_log.read_text(encoding="utf-8", errors="replace")
    assert not wt_log.exists(), "worktree 자신의 data/logs 에는 남으면 안 됩니다"


def test_internal_exception_without_bypass_reason_fails_cleanly(repo: Path, monkeypatch):
    """evaluate() 가 예상 못한 예외를 던지면(우회 사유 없음) FAIL(1) 로 처리하고 죽지 않는다."""

    def boom(root):
        raise RuntimeError("simulated internal bug")

    monkeypatch.setattr(skeleton_gate, "evaluate", boom)
    monkeypatch.delenv("SKELETON_GATE_SKIP_REASON", raising=False)
    exit_code = skeleton_gate.run(root=repo)
    assert exit_code == 1


def test_internal_exception_with_bypass_reason_passes(repo: Path, monkeypatch):
    """evaluate() 가 내부 오류를 던져도 SKELETON_GATE_SKIP_REASON 이 있으면 우회(exit 0)한다."""

    def boom(root):
        raise RuntimeError("simulated internal bug")

    monkeypatch.setattr(skeleton_gate, "evaluate", boom)
    monkeypatch.setenv("SKELETON_GATE_SKIP_REASON", "내부 오류 우회 테스트")
    exit_code = skeleton_gate.run(root=repo)
    assert exit_code == 0
