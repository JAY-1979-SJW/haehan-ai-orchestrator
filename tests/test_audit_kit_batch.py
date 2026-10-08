"""audit_kit_batch / audit_kit_gate.batch_raw_findings — 파일마다 hook 을 따로 부르지 않고 그래프를 프로세스당 1회만 만든다 (PR #160 verify 정지 재발 방지).

진짜 audit-kit 은 가상환경에만 있으므로, 시험은 같은 이름의 가짜 `audit_kit.hook` 패키지를 PYTHONPATH 에 두고 실제 스크립트를 자식 프로세스로 돌린다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.ops import audit_kit_gate as gate

FAKE_HOOK = """
import sys
from pathlib import Path
BUILDS = Path(__file__).parent / "builds.log"

class Graph:
    def __init__(self):
        self.calls = 0
    def cycles(self):
        self.calls += 1
        return []

def build_project_graph(cfg):
    BUILDS.open("a", encoding="utf-8").write("build\\n")
    return Graph()

class Cfg:
    root = Path(".").resolve()

def check_file(path):
    graph = build_project_graph(Cfg())  # 진짜 hook 처럼 파일마다 그래프를 만든다 — 스크립트가 이를 1회로 줄여야 한다
    if path.name == "boom.py":
        raise RuntimeError("검사 실패")
    if path.name == "bad.py":
        return ["[표준 STD-02] bad.py:1 절대경로 하드코딩", "[mypy import-not-found] x", "잡음 줄"]
    return []
"""

SCRIPT = Path(gate.__file__).with_name("audit_kit_batch.py")


@pytest.fixture()
def fake_audit_kit(tmp_path, monkeypatch):
    pkg = tmp_path / "fakepkg" / "audit_kit"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "hook.py").write_text(FAKE_HOOK, encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "fakepkg"))
    monkeypatch.setattr(
        gate, "mypy_python", lambda kit: sys.executable
    )  # '진짜 kit 의 가상환경 python' 자리에 현재 python
    tree = tmp_path / "tree"
    tree.mkdir()
    for name in ("a.py", "b.py", "c.py", "bad.py", "boom.py"):
        (tree / name).write_text("x = 1" + chr(10), encoding="utf-8")
    return tree, pkg / "builds.log"


def test_batch_builds_the_graph_once_per_process_not_once_per_file(fake_audit_kit):
    tree, builds = fake_audit_kit
    found = gate.batch_raw_findings(["audit-kit"], tree, ["a.py", "b.py", "c.py"], workers=1)
    assert set(found) == {"a.py", "b.py", "c.py"} and all(v == [] for v in found.values())
    assert builds.read_text(encoding="utf-8").count("build") == 1  # 파일 3개인데 그래프는 1번


def test_batch_filters_lines_like_raw_findings_and_skips_failed_files(fake_audit_kit):
    tree, _builds = fake_audit_kit
    found = gate.batch_raw_findings(["audit-kit"], tree, ["bad.py", "boom.py", "a.py"], workers=1)
    assert found["bad.py"] == ["[표준 STD-02] bad.py:1 절대경로 하드코딩"]  # '['로 시작하지 않는 줄·환경 잡음 줄은 뺀다
    assert "boom.py" not in found  # 예외가 난 파일은 결과에서 빠져, 호출 쪽이 단독 호출로 다시 시도한다
    assert found["a.py"] == []


def test_batch_splits_files_across_processes(fake_audit_kit):
    tree, builds = fake_audit_kit
    found = gate.batch_raw_findings(["audit-kit"], tree, ["a.py", "b.py", "c.py", "bad.py"], workers=2)
    assert set(found) == {"a.py", "b.py", "c.py", "bad.py"}
    assert builds.read_text(encoding="utf-8").count("build") == 2  # 프로세스 2개 = 그래프 2번


def test_batch_returns_empty_for_a_fake_kit_or_no_files(monkeypatch, tmp_path):
    monkeypatch.setattr(
        gate, "mypy_python", lambda kit: None
    )  # 진짜 audit-kit 이 아니다 → 묶음 실행 안 함(단독 호출로 처리)
    assert gate.batch_raw_findings(["fake"], tmp_path, ["a.py"]) == {}
    monkeypatch.setattr(gate, "mypy_python", lambda kit: sys.executable)
    assert gate.batch_raw_findings(["audit-kit"], tmp_path, []) == {}


def test_batch_script_prints_json_to_stdout(fake_audit_kit):
    import os
    import subprocess

    tree, _builds = fake_audit_kit
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(tree)],
        input=json.dumps(["a.py", "bad.py"]).encode("utf-8"),
        capture_output=True,
        env={**os.environ},
        check=False,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout.decode("utf-8"))
    assert data["a.py"] == [] and data["bad.py"][0].startswith("[표준 STD-02]")
