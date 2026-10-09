"""git 훅 설치 스크립트의 core.hooksPath 자동 설정 — 가짜 git 설정 함수로 확인한다(실제 저장소 설정을 바꾸지 않는다)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.hooks import install_git_hooks as ih


def fake_git(initial: str | None, fail_set: bool = False):
    state: dict[str, Any] = {"value": initial, "calls": []}

    def run(_root, *args):
        state["calls"].append(args)
        if args == ("--get", "core.hooksPath"):
            return (0, state["value"]) if state["value"] else (1, "")
        if args[0] == "core.hooksPath":
            if fail_set:
                return 1, "error: could not lock config file"
            state["value"] = args[1]
            return 0, ""
        raise AssertionError(args)

    return run, state


def test_sets_hooks_path_when_empty(capsys):
    run, state = fake_git(None)
    assert ih.ensure_hooks_path(Path("."), run) == "set" and state["value"] == ".githooks"
    assert "비어 있어 훅이 동작하지 않았음" in capsys.readouterr().out


def test_leaves_correct_value_alone():
    run, state = fake_git(".githooks")
    assert ih.ensure_hooks_path(Path("."), run) == "ok"
    assert all(call == ("--get", "core.hooksPath") for call in state["calls"])  # 쓰기 호출 없음


def test_never_overrides_a_different_value(capsys):
    run, state = fake_git("custom-hooks-dir")
    assert ih.ensure_hooks_path(Path("."), run) == "other" and state["value"] == "custom-hooks-dir"
    assert "바꾸지 않았습니다" in capsys.readouterr().out


def test_reports_failure_instead_of_pretending(capsys):
    run, _ = fake_git(None, fail_set=True)
    assert ih.ensure_hooks_path(Path("."), run) == "failed"
    assert "설정 실패" in capsys.readouterr().out
