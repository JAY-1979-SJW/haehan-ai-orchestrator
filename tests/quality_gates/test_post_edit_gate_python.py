"""post_edit_fast_gate._project_python — 훅이 어떤 python 으로 불려도 하위 프로세스는 프로젝트 버전(3.14)."""

import subprocess
import sys

from tools.hooks import post_edit_fast_gate as gate


def test_uses_current_interpreter_when_already_project_version(monkeypatch):
    monkeypatch.setattr(gate.sys, "version_info", (3, 14, 0))
    assert gate._project_python() == [sys.executable]


def test_uses_current_interpreter_without_py_launcher(monkeypatch):
    monkeypatch.setattr(gate.sys, "version_info", (3, 11, 0))
    monkeypatch.setattr(gate.shutil, "which", lambda name: None)
    assert gate._project_python() == [sys.executable]


def test_switches_to_py_314_when_called_from_other_version(monkeypatch):
    monkeypatch.setattr(gate.sys, "version_info", (3, 11, 0))
    monkeypatch.setattr(gate.shutil, "which", lambda name: "C:/Windows/py.exe")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    assert gate._project_python() == ["py", "-3.14"]
    assert calls == [["py", "-3.14", "-c", "pass"]]  # 실제로 실행 가능한지 확인한다


def test_falls_back_when_py_314_is_not_installed(monkeypatch):
    monkeypatch.setattr(gate.sys, "version_info", (3, 11, 0))
    monkeypatch.setattr(gate.shutil, "which", lambda name: "C:/Windows/py.exe")
    monkeypatch.setattr(gate.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 103))
    assert gate._project_python() == [sys.executable]


def test_gate_commands_use_project_python():
    """ruff·query·pytest 하위 프로세스 명령이 sys.executable 을 직접 쓰지 않는다."""
    import pathlib

    src = pathlib.Path(gate.__file__).read_text(encoding="utf-8")
    body = src.split("def _project_python", 1)[1].split("\ndef ", 1)[1]  # 헬퍼 정의 이후 코드
    assert "sys.executable" not in body
    assert body.count("*_project_python()") >= 3
