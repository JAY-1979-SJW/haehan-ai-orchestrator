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
