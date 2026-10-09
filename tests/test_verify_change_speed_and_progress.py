"""verify_change — CI 가 90분 상한에 걸려 실패한 사고(2026-10-08 PR #160)의 재발 방지.

원인: 이 도구는 끝날 때까지 출력이 없어 어느 단계에서 멈췄는지 로그로 알 수 없었고, 변경 파일 1065개에 대한 mypy 가
파일마다 따로(전역 잠금으로 직렬) 돌았으며, 시험 한 건이 멈춰도 상한이 없었다. 이 시험은 고친 세 가지를 고정한다:
진행 로그, 일괄 mypy(기준 폴더별 1회), 시험별 시간 상한·병렬 인자.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

from tools import verify_change as vc


def test_log_prints_elapsed_prefix_and_flushes(capsys):
    vc._log("단계 시작")
    out = capsys.readouterr().out
    assert out.startswith("[verify +") and "s] 단계 시작" in out


def test_pytest_extra_args_follow_installed_plugins(monkeypatch):
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a, **k: object() if name in {"pytest_timeout", "xdist"} else real(name, *a, **k),
    )
    assert vc._pytest_extra_args() == [f"--timeout={vc.PER_TEST_TIMEOUT_S}", "-n", str(vc.MAX_XDIST_WORKERS)]
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a, **k: None if name in {"pytest_timeout", "xdist"} else real(name, *a, **k),
    )
    assert vc._pytest_extra_args() == []  # 플러그인이 없는 PC 에서도 인자 오류로 전부 실패하지 않는다


def test_pytest_passes_the_extra_args_to_the_pytest_command(monkeypatch, tmp_path):
    seen: list[list[str]] = []

    def fake_run(cmd, cwd, timeout=0):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(vc, "run", fake_run)
    monkeypatch.setattr(vc, "_pytest_extra_args", lambda: ["--timeout=300", "-n", "4"])
    assert vc._pytest(tmp_path, ["tests/test_a.py"], 60) == []
    assert "--timeout=300" in seen[0] and seen[0][-1] == "tests/test_a.py"
    assert seen[0].index("-n") < seen[0].index("tests/test_a.py")  # 인자는 시험 파일 앞에


def test_audit_kit_findings_run_mypy_in_batches_not_per_file(monkeypatch, tmp_path):
    """mypy 는 head·base 각각 일괄 1회(mypy_keys_batch)이고, 파일 수만큼 따로 돌리지 않는다."""
    from tools.hooks import audit_kit_gate as gate

    head, base = tmp_path / "head", tmp_path / "base"
    for tree in (head, base):
        (tree / "pkg").mkdir(parents=True)
        for name in ("a.py", "b.py", "c.py"):
            (tree / "pkg" / name).write_text("x = 1\n", encoding="utf-8")
    batches: list[tuple[str, int]] = []

    def fake_batch(py, paths, root=None):
        batches.append((Path(root).name, len(paths)))
        return {p: ({"err"} if p.name == "b.py" and Path(root).name == "head" else set()) for p in paths}

    monkeypatch.setattr(gate, "find_audit_kit", lambda root=None, env=None: ["audit-kit"])
    monkeypatch.setattr(gate, "raw_findings", lambda kit, path, root=None: [])
    monkeypatch.setattr(gate, "mypy_python", lambda kit: "py")
    monkeypatch.setattr(gate, "is_real_kit", lambda kit: True)
    monkeypatch.setattr(gate, "mypy_keys_batch", fake_batch)
    monkeypatch.setattr(
        gate, "mypy_new", lambda *a, **k: (_ for _ in ()).throw(AssertionError("파일별 mypy_new 를 부르면 안 된다"))
    )
    found, note = vc._audit_kit_new_findings(["pkg/a.py", "pkg/b.py", "pkg/c.py"], base, head)
    assert batches == [("head", 3), ("base", 3)]
    assert note == "" and len(found) == 1 and found[0].startswith("pkg/b.py:") and "err" in found[0]
