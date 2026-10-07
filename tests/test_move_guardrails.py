"""이동 가드레일 도구(G1 move_preflight · G6 run_impacted_tests) 테스트.

negative 검증: 2026-10-07 실제 회귀 두 건(hiworks 경로 로드·dashboard 직접 실행)을 같은 모양으로 재현해
shim 없이 이동하면 preflight 가 잡고(막음), make_shim 으로 shim 을 만들면 통과하는지 본다.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.ops import move_preflight as mp
from scripts.ops import run_impacted_tests as rit
from scripts.ops.make_shim import make_shim


def _w(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", check=True
    ).stdout


@pytest.fixture()
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    # hiworks 모양: 루트 모듈을 다른 쪽이 파일 경로로 로드한다
    _w(tmp_path, "reader.py", "def fetch():\n    return 1\n")
    _w(
        tmp_path,
        "pkg/router.py",
        "import importlib.util\nfrom pathlib import Path\n\n"
        "def load():\n"
        "    spec = importlib.util.spec_from_file_location('reader', Path(__file__).parents[1] / 'reader.py')\n"
        "    mod = importlib.util.module_from_spec(spec)\n    spec.loader.exec_module(mod)\n    return mod\n",
    )
    # dashboard 모양: __main__ 블록이 있는 직접 실행 파일, 참조는 import 뿐
    _w(tmp_path, "dash.py", "def run():\n    return 2\n\nif __name__ == '__main__':\n    run()\n")
    _w(tmp_path, "user.py", "import dash\n")
    # import 만 있고 __main__ 없는 파일
    _w(tmp_path, "plain.py", "X = 1\n")
    _w(tmp_path, "uses_plain.py", "from plain import X\n")
    _w(tmp_path, "configs/module_registry.json", '{"plain.py": {}, "reader.py": {}}\n')
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _kinds(rows):
    return {r["kind"] for r in rows[0]["references"]}


def test_preflight_catches_hiworks_path_load(repo):
    rows = mp.report(["reader.py"], repo)
    assert "path_load" in _kinds(rows)
    assert rows[0]["recommendation"]["shim"] == "execution-forward"
    assert any(b["kind"] == "path_load" for b in rows[0]["blocking"])


def test_preflight_catches_dashboard_direct_execution(repo):
    rows = mp.report(["dash.py"], repo)
    assert rows[0]["has_main"] is True
    assert any(b["kind"] == "direct_exec" for b in rows[0]["blocking"])
    assert rows[0]["recommendation"]["shim"] == "execution-forward"


def test_import_only_and_registry_refs_do_not_block(repo):
    rows = mp.report(["plain.py"], repo)
    assert "import" in _kinds(rows) and "registry" in _kinds(rows)
    assert rows[0]["blocking"] == []
    assert rows[0]["recommendation"]["shim"] == "alias"


def test_adjacent_filename_is_not_a_reference(repo):
    _w(repo, "tool.py", "print('x')\n")
    _w(repo, "scripts/run.sh", "python analytics_tool.py\npython tool.py\n")
    rows = mp.report(["tool.py"], repo)
    lines = [(r["file"], r["line"]) for r in rows[0]["references"] if r["file"] == "scripts/run.sh"]
    assert lines == [("scripts/run.sh", 2)]


def test_direct_exec_in_batch_and_config(repo):
    _w(repo, "run_reader.bat", "python reader.py --once\n")
    _w(repo, "configs/entrypoints_manual.json", '{"entry": "reader.py"}\n')
    _w(repo, ".claude/settings.json", '{"hooks": {"x": "python reader.py"}}\n')
    kinds = {r["kind"] for r in mp.report(["reader.py"], repo)[0]["references"]}
    assert {"direct_exec", "config_path", "hook"} <= kinds


def test_run_module_and_module_flag_detected(repo):
    _w(repo, "scripts/x.py", "import runpy\nrunpy.run_module('dash', run_name='__main__')\n")
    _w(repo, "start.cmd", "python -m dash\n")
    refs = mp.report(["dash.py"], repo)[0]["references"]
    assert {"runpy", "direct_exec"} <= {r["kind"] for r in refs}


def test_staged_rename_blocked_without_shim_and_passes_with_shim(repo, capsys):
    _git(repo, "mv", "reader.py", "pkg/reader.py")
    assert mp.staged_renames(repo) == {"reader.py": "pkg/reader.py"}
    assert mp.main(["--staged-renames", "--root", str(repo)]) == 1  # path_load 가 남아 있고 shim 없음
    err = capsys.readouterr().err
    assert "make_shim.py reader.py pkg/reader.py" in err
    make_shim("reader.py", "pkg/reader.py", repo)
    _git(repo, "add", "-A")
    assert mp.main(["--staged-renames", "--root", str(repo)]) == 0


def test_staged_rename_with_main_blocked_until_shim(repo):
    _git(repo, "mv", "dash.py", "pkg/dash.py")
    assert mp.main(["--staged-renames", "--root", str(repo)]) == 1
    make_shim("dash.py", "pkg/dash.py", repo)
    assert "run_module" in (repo / "dash.py").read_text(encoding="utf-8")
    assert mp.main(["--staged-renames", "--root", str(repo)]) == 0


def test_staged_import_only_rename_passes(repo):
    _git(repo, "mv", "plain.py", "pkg/plain.py")
    assert mp.main(["--staged-renames", "--root", str(repo)]) == 0


def test_wrong_shim_target_does_not_count(repo):
    _git(repo, "mv", "reader.py", "pkg/reader.py")
    _w(repo, "reader.py", "# haehan-shim: other.module\nimport importlib as _il\n")
    assert mp.main(["--staged-renames", "--root", str(repo)]) == 1


def test_json_output_and_cannot_move(repo, capsys):
    _w(repo, "pkg/__init__.py", "")
    assert mp.main(["pkg/__init__.py", "--json", "--root", str(repo)]) == 0
    row = json.loads(capsys.readouterr().out)[0]
    assert row["recommendation"]["shim"] == "cannot move"


# ── G6 run_impacted_tests ────────────────────────────────────────────────


def _map(tmp_path: Path, edges: dict) -> Path:
    p = tmp_path / "map.json"
    p.write_text(json.dumps({"import_edges": edges}), encoding="utf-8")
    return p


def test_refuses_when_no_impacted_tests(tmp_path, capsys):
    m = _map(tmp_path, {})
    rc = rit.main(["src/a.py", "--map", str(m), "--root", str(tmp_path)])
    assert rc == 2
    assert "0개" in capsys.readouterr().err


def test_refuses_when_map_missing(tmp_path):
    rc = rit.main(["src/a.py", "--map", str(tmp_path / "nope.json"), "--root", str(tmp_path)])
    assert rc == 2


def test_runs_only_explicit_existing_files_with_baseline_compare(tmp_path):
    _w(tmp_path, "tests/test_a.py", "def test_ok():\n    assert True\n")
    m = _map(tmp_path, {"tests/test_a.py": ["src/a.py"], "tests/test_missing.py": ["src/a.py"]})
    seen = {}

    def runner(tests, timeout, root, junit):
        seen.update(tests=tests, timeout=timeout)
        junit.write_text(
            '<testsuite><testcase classname="tests.test_a" name="test_ok"/>'
            '<testcase classname="tests.test_a" name="test_bad"><failure/></testcase></testsuite>',
            encoding="utf-8",
        )
        return 1, "1 failed, 1 passed"

    out = tmp_path / "res.json"
    rc = rit.main(
        ["src/a.py", "--map", str(m), "--root", str(tmp_path), "--out", str(out), "--timeout", "7"], runner=runner
    )
    assert seen == {"tests": ["tests/test_a.py"], "timeout": 7}  # 없는 테스트 파일은 제외
    assert rc == 1
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["results"] == {"tests.test_a::test_ok": "passed", "tests.test_a::test_bad": "failed"}

    # 기준선에도 같은 실패가 있으면 '새 실패' 가 아니다
    out2 = tmp_path / "res2.json"
    rc2 = rit.main(
        ["src/a.py", "--map", str(m), "--root", str(tmp_path), "--out", str(out2), "--baseline", str(out)],
        runner=runner,
    )
    assert rc2 == 0
    assert json.loads(out2.read_text(encoding="utf-8"))["comparison"]["new_failures"] == []


def test_compare_flags_pass_to_fail():
    cmp_ = rit.compare({"a": "failed", "b": "passed"}, {"a": "passed", "b": "failed", "c": "passed"})
    assert cmp_["new_failures"] == ["a"] and cmp_["fixed"] == ["b"] and cmp_["missing_vs_baseline"] == ["c"]


def test_real_pytest_command_shape(tmp_path):
    """실제 pytest 호출: 명시 파일 + --timeout + -p no:cacheprovider (전체 실행 아님)."""
    _w(tmp_path, "tests/test_ok.py", "def test_ok():\n    assert True\n")
    junit = tmp_path / "j.xml"
    rc, _ = rit.run_pytest(["tests/test_ok.py"], 30, tmp_path, junit)
    assert rc == 0 and rit.parse_junit(junit) == {"tests.test_ok::test_ok": "passed"}
    assert not (tmp_path / ".pytest_cache").exists()


def test_pytest_runs_with_the_current_interpreter():
    """CI 회귀 방지: py 런처가 다른 3.14 를 가리켜도(의존성 없는 인터프리터) 현재 인터프리터로 돌린다."""
    import sys

    assert rit._pyexe() == [sys.executable]
