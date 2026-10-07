"""도구 분리 B2(instagram) 이동 시험 — ig_batch 를 도구 집으로 옮겨도 옛 경로 실행·부트스트랩 루트·발행 훅 패턴이 그대로인지 고정한다."""

from __future__ import annotations

import importlib
import subprocess
import sys

import pytest

from scripts.app_paths import repo_root

ROOT = repo_root()


def test_ig_batch_bootstrap_root_is_the_repo_root():
    mod = importlib.import_module("scripts.instagram.ops.ig_batch")
    assert mod._ROOT == ROOT


@pytest.mark.parametrize("script", ["scripts/ops/ig_batch.py", "scripts/instagram/ops/ig_batch.py"])
def test_ig_batch_runs_from_old_and_new_path(script):
    """직접 실행(--help)이 옛 경로(shim)와 새 경로 모두에서 같은 사용법을 보여 준다(실제 발행·브라우저 접근 없음)."""
    proc = subprocess.run(
        [sys.executable, script, "--help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0
    assert "--confirmed" in proc.stdout and "--confirm" in proc.stdout


@pytest.mark.parametrize("path", ["scripts/ops/ig_batch.py", "scripts/instagram/ops/ig_batch.py"])
def test_publish_guard_hook_still_matches_both_paths(path):
    """PreToolUse 훅(guard_instagram_publish)의 'ig_batch.py ... --confirmed' 패턴이 옛·새 경로 모두에 걸린다."""
    guard = importlib.import_module("scripts.ops.guard_instagram_publish")
    cmd = f"python {path} --confirmed"
    assert any(p.search(cmd) for p in guard.TRIGGER_PATTERNS)


def test_ig_batch_shim_is_tiny():
    shim = (ROOT / "scripts/ops/ig_batch.py").read_text(encoding="utf-8")
    assert "from scripts.instagram.ops.ig_batch import main" in shim and len(shim.splitlines()) <= 16
