from scripts.ops import changed_functions as cf
from scripts.ops import summarize_mutation as sm

DIFF = """+++ b/scripts/ops/a.py
@@ -1,0 +5,2 @@
+x
+y
+++ b/README.md
@@ -1 +1 @@
"""

SRC = """def top():
    return 1


class C:
    def m(self):
        return 2

    def other(self):
        return 3
"""


def test_parse_diff_only_python_added_lines():
    assert cf.parse_diff(DIFF) == {"scripts/ops/a.py": {5, 6}}


def test_module_dotted_path_handles_init():
    assert cf.module_dotted_path("scripts/ops/a.py") == "scripts.ops.a"
    assert cf.module_dotted_path("ai_orchestrator/x/__init__.py") == "ai_orchestrator.x"


def test_functions_touching_names_methods():
    assert cf.functions_touching(SRC, {1}) == ["top"]
    assert cf.functions_touching(SRC, {7}) == ["C.m"]
    assert cf.functions_touching("def (", {1}) == []


def test_patterns_for_diff():
    patterns = cf.patterns_for_diff({"scripts/ops/a.py": {6}}, read=lambda p: SRC)
    assert patterns == ["scripts.ops.a.xǁCǁm__mutmut_*"]


def test_summary_uses_killed_plus_survived_and_reports_truncation():
    text = sm.render({"killed": 3, "survived": 1, "total": 99}, total_targets=50, limit=40)
    assert "75.0%" in text and "3/4" in text
    assert "50개 중 40개" in text
    assert "n/a" in sm.render({})


def test_mutant_pattern_function_and_method():
    assert cf.mutant_pattern("a.b", "f") == "a.b.x_f__mutmut_*"
    assert cf.mutant_pattern("a.b", "C.m") == "a.b.xǁCǁm__mutmut_*"


def test_files_for_diff_and_rewrite_source_paths():
    ranges = {"scripts/ops/a.py": {1}, "scripts/ops/b.py": {99}}
    assert cf.files_for_diff(ranges, read=lambda p: SRC) == ["scripts/ops/a.py"]
    text = '[tool.mutmut]\nsource_paths = ["x/", "y/"]\nalso_copy = ["z"]\n'
    out = cf.rewrite_source_paths(text, ["scripts/ops/a.py"])
    assert 'source_paths = ["scripts/ops/a.py"]' in out and "also_copy" in out


def test_summary_warns_when_no_mutant_ran():
    assert "실행된 변이체 0" in sm.render({"killed": 0, "survived": 0, "total": 466457})


def test_tests_for_files_picks_direct_references_only():
    texts = {
        "tests/test_a.py": "from scripts.ops import a\n",
        "tests/test_b.py": "import unrelated\n",
        "tests/test_c.py": "from scripts.ops.a import f\n",
    }
    got = cf.tests_for_files(["scripts/ops/a.py"], list(texts), read=lambda p: texts[p])
    assert got == ["tests/test_a.py", "tests/test_c.py"]


def test_rewrite_toml_list_replaces_only_that_key():
    text = 'a = ["1"]\nalso_copy = ["x", "y"]\n'
    assert cf.rewrite_toml_list(text, "also_copy", ["z"]) == 'a = ["1"]\nalso_copy = ["z"]\n'



def test_parse_diff_boundaries():
    diff = (
        "+++ b/scripts/x.py\n"
        "@@ -3,2 +3,0 @@\n"  # 삭제만 있는 hunk(추가 0줄)
        "@@ -9 +10 @@\n"  # 개수 생략 = 1줄
        "@@ -20,0 +21,3 @@\n"
        "+++ /dev/null\n"  # 삭제된 파일은 b/ 접두가 없다
        "@@ -1,2 +0,0 @@\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
    )
    assert cf.parse_diff(diff) == {"scripts/x.py": {10, 21, 22, 23}}
    assert cf.parse_diff("@@ -1 +1 @@\n") == {}  # 헤더 이전 hunk 는 무시


def test_parse_diff_keeps_each_file_separate():
    diff = "+++ b/a.py\n@@ -1 +1,2 @@\n+++ b/b.py\n@@ -5 +7 @@\n"
    assert cf.parse_diff(diff) == {"a.py": {1, 2}, "b.py": {7}}


def test_changed_line_ranges_runs_git_diff_on_source_roots(monkeypatch):
    seen = {}

    class _Done:
        stdout = "+++ b/scripts/x.py\n@@ -1 +4,2 @@\n"

    def fake_run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return _Done()

    monkeypatch.setattr(cf.subprocess, "run", fake_run)
    assert cf.changed_line_ranges("base", "head") == {"scripts/x.py": {4, 5}}
    cmd = seen["cmd"]
    assert cmd[:5] == ["git", "diff", "-U0", "--diff-filter=ACMR", "base"] and cmd[5] == "head"
    assert cmd[-len(cf.SOURCE_ROOTS) :] == list(cf.SOURCE_ROOTS) and "--" in cmd
    assert seen["kw"]["check"] is True and seen["kw"]["capture_output"] is True


def test_main_prints_patterns_with_limit(monkeypatch, capsys):
    monkeypatch.setattr(cf, "changed_line_ranges", lambda base, head: {"scripts/ops/a.py": {1, 6}})
    monkeypatch.setattr(cf, "patterns_for_diff", lambda ranges: ["p1", "p2", "p3"])
    assert cf.main(["base", "--limit", "2"]) == 0
    out = capsys.readouterr()
    assert out.out.split() == ["p1", "p2"] and "3개 중 앞 2개" in out.err
    assert cf.main([]) == 2
