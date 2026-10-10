"""proc_tree.run_tree_killed — 파이프를 문 자손 프로세스가 있어도 시간 초과 때 멈추지 않는다 (PR #160 verify 90분 정지 재발 방지)."""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

from tools.code_map import proc_tree

# 부모는 자식 하나(파이프를 상속해 오래 사는 '데몬')를 띄우고 자신도 오래 잔다 → 일반 subprocess.run(timeout) 은 파이프 EOF 를 못 받아 멈춘다
PARENT_WITH_PIPE_HOLDING_CHILD = (
    "import subprocess, sys, time\n"
    "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
    "time.sleep(120)\n"
)


def test_returns_output_and_returncode_like_subprocess_run():
    result = proc_tree.run_tree_killed(
        [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"], timeout=30
    )
    assert (result.returncode, result.stdout.strip(), result.stderr.strip()) == (3, "out", "err")


def test_timeout_kills_the_whole_tree_and_does_not_hang(monkeypatch):
    monkeypatch.setattr(proc_tree, "PIPE_GRACE_S", 10)
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        proc_tree.run_tree_killed([sys.executable, "-c", PARENT_WITH_PIPE_HOLDING_CHILD], timeout=2)
    assert (
        time.monotonic() - started < 40
    )  # 자손이 파이프를 물고 있어도 트리를 죽여 EOF 를 받거나, 못 받으면 포기하고 돌아온다


def test_gives_up_on_a_pipe_that_never_closes(monkeypatch):
    """트리 종료가 듣지 않는 경우(kill_tree 무력화)에도 PIPE_GRACE_S 뒤에는 돌아온다."""
    monkeypatch.setattr(proc_tree, "kill_tree", lambda pid: None)
    monkeypatch.setattr(proc_tree, "PIPE_GRACE_S", 1)
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        proc_tree.run_tree_killed([sys.executable, "-c", PARENT_WITH_PIPE_HOLDING_CHILD], timeout=1)
    assert time.monotonic() - started < 30


def test_bytes_mode_passes_stdin_and_returns_bytes():
    code = "import sys; data = sys.stdin.buffer.read(); sys.stdout.buffer.write(data.upper()); sys.exit(2)"
    result = proc_tree.run_tree_killed([sys.executable, "-c", code], input=b"abc", text=False, timeout=30)
    assert (result.returncode, result.stdout, result.stderr) == (2, b"ABC", b"")


def test_audit_kit_raw_findings_returns_none_instead_of_hanging_when_the_kit_leaves_a_pipe_holder(
    monkeypatch, tmp_path
):
    """PR #160 verify: audit-kit hook 이 자손을 남겨 파이프를 물면 subprocess.run(timeout) 이 영원히 멈췄다 → 트리째 종료하고 None(검사 못 함)."""
    from tools.hooks import audit_kit_gate as gate

    fake_kit = tmp_path / "fake_kit.py"
    fake_kit.write_text(PARENT_WITH_PIPE_HOLDING_CHILD, encoding="utf-8")
    monkeypatch.setattr(gate, "PER_FILE_TIMEOUT_S", 2)
    monkeypatch.setattr(proc_tree, "PIPE_GRACE_S", 10)
    started = time.monotonic()
    assert gate.raw_findings([sys.executable, str(fake_kit)], tmp_path / "x.py", tmp_path) is None
    assert time.monotonic() - started < 40
