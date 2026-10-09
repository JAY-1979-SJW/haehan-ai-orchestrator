"""audit_kit_batch / audit_kit_gate.batch_raw_findings — 파일마다 hook 을 따로 부르지 않고 그래프를 프로세스당 1회만 만든다 (PR #160 verify 정지 재발 방지).

진짜 audit-kit 은 가상환경에만 있으므로, 시험은 같은 이름의 가짜 `audit_kit.hook` 패키지를 PYTHONPATH 에 두고 실제 스크립트를 자식 프로세스로 돌린다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tools.hooks import audit_kit_gate as gate

FAKE_HOOK = """
import os
import sys
import uuid
from pathlib import Path
BUILDS_DIR = Path(__file__).parent / "builds"
BUILDS_DIR.mkdir(exist_ok=True)

class Graph:
    def __init__(self):
        self.calls = 0
    def cycles(self):
        self.calls += 1
        return []

def build_project_graph(cfg):
    # 프로세스마다 자기 이름의 마커 파일을 만든다 — 공유 파일에 여러 프로세스가 동시에
    # append 하면(Windows, 바이러스 백신 간섭 등) 쓰기가 가끔 사라지는 레이스가 있었다(CI run
    # 38001279922, 로컬 20회 중 2회 재현).
    (BUILDS_DIR / f"build-{os.getpid()}-{uuid.uuid4().hex}").write_text("build", encoding="utf-8")
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

SCRIPT = Path(gate.__file__).resolve().parents[1] / "audit_kit_batch.py"  # tools/hooks/ 의 한 단계 위(tools/)


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
    return tree, pkg / "builds"


def test_batch_builds_the_graph_once_per_process_not_once_per_file(fake_audit_kit):
    tree, builds = fake_audit_kit
    found = gate.batch_raw_findings(["audit-kit"], tree, ["a.py", "b.py", "c.py"], workers=1)
    assert set(found) == {"a.py", "b.py", "c.py"} and all(v == [] for v in found.values())
    assert len(list(builds.iterdir())) == 1  # 파일 3개인데 그래프는 1번


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
    assert len(list(builds.iterdir())) == 2  # 프로세스 2개 = 그래프 2번


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


# ── mypy 일괄 검사: 명령줄 길이 한도 (PR #160 WinError 206 → 전 파일 '실행 못 함') ───────────


def test_split_by_command_length_keeps_each_part_under_the_budget(monkeypatch):
    monkeypatch.setattr(gate, "_CMD_CHAR_BUDGET", 100)
    paths = [Path(f"repo/pkg/module_{i:04d}.py") for i in range(30)]
    parts = gate._split_by_command_length(paths)
    assert len(parts) > 1 and [p for part in parts for p in part] == paths  # 순서·구성 보존
    assert all(sum(len(str(p)) + 1 for p in part) <= 100 or len(part) == 1 for part in parts)


def test_mypy_keys_batch_runs_one_mypy_per_part_and_merges(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "_CMD_CHAR_BUDGET", 120)
    seen: list[int] = []

    def fake_group(py, group, root):
        seen.append(len(group))
        return {p: {"e"} for p in group}

    monkeypatch.setattr(gate, "_mypy_group", fake_group)
    paths = [tmp_path / f"m{i:03d}.py" for i in range(20)]
    result = gate.mypy_keys_batch("py", paths, tmp_path)
    assert set(result) == set(paths) and len(seen) > 1 and sum(seen) == 20
