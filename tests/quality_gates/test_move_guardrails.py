"""이동 가드레일 도구(G1 move_preflight · G6 run_impacted_tests) 테스트.

negative 검증: 2026-10-07 실제 회귀 두 건(hiworks 경로 로드·dashboard 직접 실행)을 같은 모양으로 재현해
shim 없이 이동하면 preflight 가 잡고(막음), make_shim 으로 shim 을 만들면 통과하는지 본다.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.devflow import move_preflight as mp
from tools.devflow import run_impacted_tests as rit
from tools.devflow.make_shim import make_shim


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


def test_full_path_string_to_a_different_same_name_file_is_not_a_reference(repo):
    """2026-10-08 실제 회귀: tools/gates/policy.py 를 이동할 때 preflight 가
    ai_orchestrator/browser_tool/policy.py(완전히 다른 파일, 그냥 이름만 같음)를 가리키는
    전체 경로 문자열을 이동 대상 참조로 잘못 판정해 막았다. 문자열이 가리키는 폴더가 이동
    대상의 실제 부모 폴더와 다르면 참조가 아니어야 한다."""
    _w(repo, "pkg_a/__init__.py", "")
    _w(repo, "pkg_a/policy.py", "X = 1\n")
    _w(repo, "pkg_b/policy.py", "Y = 2\n")
    _w(repo, "other.py", '"pkg_b/policy.py"\n')  # 다른 폴더의 같은 이름 파일을 가리키는 전체 경로
    _w(repo, "real_user.py", "from pkg_a.policy import X\n")  # 진짜 참조(모집단이 비어 있지 않음을 보장)
    rows_a = mp.report(["pkg_a/policy.py"], repo)
    assert rows_a[0]["references"], "sanity: 스캔 결과 모집단 자체가 비어 있음(아래 필터 assert 가 무의미해짐)"
    hits_a = [r for r in rows_a[0]["references"] if r["file"] == "other.py"]
    assert hits_a == [], f"다른 파일(pkg_b/policy.py)을 가리키는 문자열인데 참조로 잡힘: {hits_a}"
    # 양성 대조: 같은 문자열이 실제로 가리키는 pkg_b/policy.py 를 대상으로 돌리면 잡혀야 한다
    # (스캐너 자체가 꺼져서 hits_a 가 그냥 항상 비는 게 아님을 증명).
    rows_b = mp.report(["pkg_b/policy.py"], repo)
    hits_b = [r for r in rows_b[0]["references"] if r["file"] == "other.py"]
    assert hits_b, "양성 대조 실패 — pkg_b/policy.py 를 가리키는 문자열인데도 안 잡힘(스캐너 자체 문제)"


def test_bare_filename_string_ambiguous_with_other_same_name_file_is_not_blocked(repo):
    """basename 만 있는 문자열(디렉터리 없음)이고, 저장소에 같은 이름의 **다른** 파일이 있으면
    그 문자열이 어느 파일을 가리키는지 확정할 수 없다 — bare 매칭 신뢰도를 낮춰 참조로 안 봄."""
    _w(repo, "pkg_a/__init__.py", "")
    _w(repo, "pkg_a/policy.py", "X = 1\n")
    _w(repo, "pkg_b/policy.py", "Y = 2\n")
    _w(repo, "other2.py", "import pkg_a\nPARENT_HINT = 'pkg_a'\nNAME = 'policy.py'\n")
    _w(repo, "real_user2.py", "from pkg_a.policy import X\n")  # 진짜 참조(모집단이 비어 있지 않음을 보장)
    rows = mp.report(["pkg_a/policy.py"], repo)
    assert rows[0]["references"], "sanity: 스캔 결과 모집단 자체가 비어 있음(아래 필터 assert 가 무의미해짐)"
    hits = [r for r in rows[0]["references"] if r["file"] == "other2.py" and r["kind"] == "path_string"]
    assert hits == [], f"같은 이름의 다른 파일(pkg_b/policy.py)이 있어 모호한데 bare 매칭으로 잡힘: {hits}"
    # 양성 대조: 모호함을 없애면(같은 이름의 다른 파일 제거) 같은 문자열이 다시 잡혀야 한다
    # (bare 매칭 자체가 꺼진 게 아니라 모호성 때문에만 안 잡혔음을 증명).
    (repo / "pkg_b" / "policy.py").unlink()
    rows_unambiguous = mp.report(["pkg_a/policy.py"], repo)
    hits_unambiguous = [
        r for r in rows_unambiguous[0]["references"] if r["file"] == "other2.py" and r["kind"] == "path_string"
    ]
    assert hits_unambiguous, "양성 대조 실패 — 모호성을 없앴는데도 bare 매칭이 안 잡힘(판정 자체 문제)"


def test_bare_filename_string_without_ambiguity_still_blocked_as_before(repo):
    """basename 만 있는 문자열이고 저장소에 그 이름을 가진 파일이 하나뿐이면(모호하지 않음),
    Path 조인 체인(디렉터리 문자열이 같은 파일 다른 줄에 있음) 판정은 그대로 유지돼야 한다
    (기존 회귀 방지 — 이번 수정이 정탐까지 지워버리면 안 됨)."""
    _w(repo, "solo_mod.py", "def f():\n    return 1\n")
    _w(
        repo,
        "loader.py",
        "import importlib.util\nfrom pathlib import Path\n\n"
        "PARENT = ''\n"
        "def load(name):\n"
        "    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / name)\n",
    )
    _w(repo, "caller.py", "from loader import load\nload('solo_mod.py')\n")
    rows = mp.report(["solo_mod.py"], repo)
    hits = [r for r in rows[0]["references"] if r["file"] == "caller.py"]
    assert hits, "모호하지 않은 bare 파일명 + 호출부는 그대로 참조로 잡혀야 함(과교정 방지)"


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







# ── 하위 패키지 이동: `from . import <패키지>` · bare `import <패키지>` · 폴더 인자 ─────────────────


@pytest.fixture()
def pkg_repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _w(
        tmp_path,
        "scripts/auto/__init__.py",
        "from . import smartstore\nimport smartstore\nfrom smartstore import mod_a\nfrom scripts.auto import smartstore as ss2\n",
    )
    _w(tmp_path, "scripts/auto/smartstore/__init__.py", "from .mod_a import run\n")
    _w(tmp_path, "scripts/auto/smartstore/mod_a.py", "def run():\n    return 1\n")
    _w(tmp_path, "scripts/auto/smartstore/mod_b.py", "from . import mod_a\n")
    _w(
        tmp_path, "scripts/other/__init__.py", "import smartstore\n"
    )  # 다른 폴더의 같은 이름 import 는 이 패키지 참조가 아니다
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _import_lines(rows, target):
    row = next(r for r in rows if r["file"] == target)
    return {(r["file"], r["line"]) for r in row["references"] if r["kind"] == "import"}


def test_subpackage_init_is_referenced_by_relative_absolute_and_bare_imports(pkg_repo):
    rows = mp.report(["scripts/auto/smartstore/__init__.py"], pkg_repo)
    refs = _import_lines(rows, "scripts/auto/smartstore/__init__.py")
    # from . import smartstore / import smartstore(bare) / from smartstore import x(bare) / from scripts.auto import smartstore
    assert {("scripts/auto/__init__.py", n) for n in (1, 2, 3, 4)} <= refs
    assert not any(f == "scripts/other/__init__.py" for f, _ in refs)  # 다른 폴더의 bare import 는 제외


def test_bare_import_of_a_module_in_the_same_folder_is_detected(pkg_repo):
    _w(pkg_repo, "scripts/auto/smartstore/runner.py", "import mod_a\nfrom mod_a import run\n")
    refs = _import_lines(mp.report(["scripts/auto/smartstore/mod_a.py"], pkg_repo), "scripts/auto/smartstore/mod_a.py")
    assert {("scripts/auto/smartstore/runner.py", 1), ("scripts/auto/smartstore/runner.py", 2)} <= refs
    assert ("scripts/auto/smartstore/mod_b.py", 1) in refs  # from . import mod_a


def test_directory_argument_expands_to_all_files_including_init(pkg_repo, capsys):
    assert mp.expand_targets(["scripts/auto/smartstore/"], pkg_repo) == [
        "scripts/auto/smartstore/__init__.py",
        "scripts/auto/smartstore/mod_a.py",
        "scripts/auto/smartstore/mod_b.py",
    ]
    assert mp.main(["scripts/auto/smartstore", "--json", "--root", str(pkg_repo)]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["file"] == "scripts/auto/smartstore/__init__.py"
    init_row = rows[0]
    assert any(r["file"] == "scripts/auto/__init__.py" and r["kind"] == "import" for r in init_row["references"])


# ── 확인 목록(configs/move_preflight_ack.json): 암묵 직접 실행 차단만 풀고 명시 참조는 계속 막는다 ──────────


def _ack(repo, *files, reason="참조 전수 수정 확인"):
    _w(repo, "configs/move_preflight_ack.json", json.dumps({"acked": [{"file": f, "reason": reason} for f in files]}))


def test_ack_lifts_only_the_implicit_main_block(repo):
    _git(repo, "mv", "dash.py", "pkg/dash.py")
    assert mp.main(["--staged-renames", "--root", str(repo)]) == 1  # 기본: __main__ 있는 파일은 shim 없으면 차단
    _ack(repo, "dash.py")
    assert mp.main(["--staged-renames", "--root", str(repo)]) == 0  # 확인 목록에 있으면 통과


def test_ack_without_reason_is_ignored(repo):
    _git(repo, "mv", "dash.py", "pkg/dash.py")
    _w(repo, "configs/move_preflight_ack.json", json.dumps({"acked": [{"file": "dash.py"}]}))
    assert mp.main(["--staged-renames", "--root", str(repo)]) == 1  # 사유 없는 항목은 무효


# ── maps\*.csv(old_path,new_path): 이미 새 경로로 고친 참조는 해결 처리, 파일명만 같고 디렉터리가
# 다르면(옛 경로 잔존 가능성) 여전히 차단 ─────────────────────────────────────────────


def test_new_paths_resolves_full_match_but_not_bare_filename(repo):
    _w(repo, "pkg/mod_x.py", "def f():\n    return 1\n")
    _w(
        repo,
        "caller_fixed.py",
        "import importlib.util\nspec = importlib.util.spec_from_file_location('mod_x', 'pkg2/mod_x.py')\n",
    )
    _w(
        repo,
        "caller_stale.py",
        "_NOTE = 'pkg'\nimport importlib.util\nspec = importlib.util.spec_from_file_location('mod_x', 'mod_x.py')\n",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add mod_x callers")
    new_paths = {"pkg/mod_x.py": "pkg2/mod_x.py"}
    rows = mp.report(["pkg/mod_x.py"], repo, new_paths)
    blocking_files = {b["file"] for b in rows[0]["blocking"]}
    assert "caller_fixed.py" not in blocking_files  # new_path(디렉터리 포함) 와 완전히 일치 → 해결
    assert "caller_stale.py" in blocking_files  # 파일명만 같고 디렉터리 없음(옛 경로일 수도) → 그대로 차단


def test_new_paths_resolves_path_join_chain_by_full_reconstructed_path(repo):
    """ROOT / "tools" / "mod_x.py" 처럼 쪼개진 체인은 마지막 세그먼트만 보면 디렉터리를 잃는다 —
    전체 체인을 이어붙인 경로가 new_path 와 일치할 때만 해결, 옛 경로 체인은 그대로 차단."""
    _w(repo, "pkg/mod_x.py", "def f():\n    return 1\n")
    _w(
        repo,
        "caller_chain_fixed.py",
        "from pathlib import Path\nimport importlib.util\n"
        "ROOT = Path('.')\n"
        "spec = importlib.util.spec_from_file_location('mod_x', ROOT / 'pkg2' / 'mod_x.py')\n",
    )
    _w(
        repo,
        "caller_chain_stale.py",
        "from pathlib import Path\nimport importlib.util\n"
        "ROOT = Path('.')\n"
        "spec = importlib.util.spec_from_file_location('mod_x', ROOT / 'pkg' / 'mod_x.py')\n",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add mod_x chain callers")
    new_paths = {"pkg/mod_x.py": "pkg2/mod_x.py"}
    rows = mp.report(["pkg/mod_x.py"], repo, new_paths)
    blocking_files = {b["file"] for b in rows[0]["blocking"]}
    assert "caller_chain_fixed.py" not in blocking_files  # 체인 전체 경로가 new_path 와 일치 → 해결
    assert "caller_chain_stale.py" in blocking_files  # 체인이 옛 경로(pkg/mod_x.py) 그대로 → 차단


def test_maps_csv_flag_feeds_new_paths_for_staged_renames(repo, tmp_path):
    _git(repo, "mv", "reader.py", "pkg/reader.py")
    maps_csv = tmp_path / "batch.csv"
    maps_csv.write_text("old_path,new_path\nreader.py,pkg/reader.py\n", encoding="utf-8")
    # --maps 는 --staged-renames 가 이미 아는 old->new 와 같으므로 결과도 같아야 한다(멱등 지원 확인).
    assert mp.main(["--staged-renames", "--maps", str(maps_csv), "--root", str(repo)]) == 1


def test_ack_does_not_hide_explicit_references(repo):
    _w(repo, "run_dash.bat", "python dash.py\n")  # 명시적 직접 실행 참조
    _git(repo, "add", "-A")
    _git(repo, "mv", "dash.py", "pkg/dash.py")
    _ack(repo, "dash.py")
    assert mp.main(["--staged-renames", "--root", str(repo)]) == 1  # 명시 참조가 남아 있으면 확인 목록과 무관하게 차단
