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


# ---- 변이체 사멸용 보강(정확한 출력·인자·경계값) ----
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

USAGE = "usage: changed_functions.py BASE [HEAD] [--limit N] [--files] [--tests] [--write-source-paths PYPROJECT]\n"


def _spy(monkeypatch, name):
    calls = []
    orig = getattr(Path, name)

    def wrapper(self, *a, **k):
        calls.append((self.name, a, k))
        return orig(self, *a, **k)

    monkeypatch.setattr(Path, name, wrapper)
    return calls


def test_changed_line_ranges_exact_git_invocation(monkeypatch):
    seen = {}

    class _Done:
        stdout = "+++ b/scripts/x.py\n@@ -1 +4,2 @@\n"

    def fake_run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return _Done()

    monkeypatch.setattr(cf.subprocess, "run", fake_run)
    cf.changed_line_ranges("B", "H")
    assert seen["cmd"] == ["git", "diff", "-U0", "--diff-filter=ACMR", "B", "H", "--", "ai_orchestrator", "scripts", "local_agent", "orchestrator_v1"]
    assert seen["kw"] == {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace", "check": True}
    assert cf.SOURCE_ROOTS == ("ai_orchestrator", "scripts", "local_agent", "orchestrator_v1")


def test_changed_line_ranges_propagates_git_failure(monkeypatch):
    def boom(cmd, **kw):
        raise subprocess.CalledProcessError(128, cmd)

    monkeypatch.setattr(cf.subprocess, "run", boom)
    with pytest.raises(subprocess.CalledProcessError):
        cf.changed_line_ranges("a", "b")


def test_parse_diff_path_handling():
    # git 은 공백이 든 경로 뒤에 탭을 붙인다 -> strip 필요
    assert cf.parse_diff("+++ b/a b.py\t\n@@ -1 +1 @@\n") == {"a b.py": {1}}
    # 첫 두 글자만 제거(b/ 가 경로 안에 또 있어도 유지)
    assert cf.parse_diff("+++ b/b/x.py\n@@ -1 +2 @@\n") == {"b/x.py": {2}}
    # b/ 접두가 없으면 무시, .py 가 아니면 무시(.pyc 포함)
    assert cf.parse_diff("+++ a/x.py\n@@ -1 +1 @@\n") == {}
    assert cf.parse_diff("+++ b/x.pyc\n@@ -1 +1 @@\n") == {}
    assert cf.parse_diff("+++ b/x.txt\n@@ -1 +1 @@\n") == {}
    # "+++ " 로 시작하지 않는 줄은 파일 헤더가 아니다
    assert cf.parse_diff("+++b/x.py\n@@ -1 +1 @@\n") == {}
    # 앞/뒤가 붙은 hunk 헤더는 무시
    assert cf.parse_diff("+++ b/x.py\nx@@ -1 +5 @@\n@@ -1 +6\n") == {}
    # 추가 0줄뿐이면 키 자체가 생기지 않는다
    assert cf.parse_diff("+++ b/x.py\n@@ -3,2 +3,0 @@\n") == {}
    # 개수 1, 개수 2: 범위 끝은 start+count 미포함
    assert cf.parse_diff("+++ b/x.py\n@@ -1 +7 @@\n") == {"x.py": {7}}
    assert cf.parse_diff("+++ b/x.py\n@@ -1,4 +7,2 @@\n") == {"x.py": {7, 8}}
    # 비-py 파일 뒤 hunk 는 직전 py 파일에 합쳐지지 않는다
    assert cf.parse_diff("+++ b/x.py\n@@ -1 +1 @@\n+++ b/y.md\n@@ -1 +9 @@\n") == {"x.py": {1}}
    # 같은 파일의 여러 hunk 는 합집합
    assert cf.parse_diff("+++ b/x.py\n@@ -1 +1 @@\n@@ -5 +9,2 @@\n") == {"x.py": {1, 9, 10}}


def _raise_oserror(_p):
    raise OSError("nope")


def test_patterns_and_files_for_diff_order_skip_missing_and_read_default():
    def reader(p):
        if p == "missing.py":
            _raise_oserror(p)
        return SRC

    ranges = {"scripts/ops/z.py": {1}, "missing.py": {1}, "scripts/ops/a.py": {1}}
    assert cf.patterns_for_diff(ranges, read=reader) == ["scripts.ops.a.x_top__mutmut_*", "scripts.ops.z.x_top__mutmut_*"]
    assert cf.files_for_diff(ranges, read=reader) == ["scripts/ops/a.py", "scripts/ops/z.py"]
    # missing 이 정렬상 앞에 와도 나머지는 처리(continue)
    ranges2 = {"a_missing.py": {1}, "scripts/ops/b.py": {1}}

    def r2(p):
        if p == "a_missing.py":
            _raise_oserror(p)
        return SRC

    assert cf.files_for_diff(ranges2, read=r2) == ["scripts/ops/b.py"]
    assert cf.patterns_for_diff(ranges2, read=r2) == ["scripts.ops.b.x_top__mutmut_*"]


def test_patterns_and_files_default_reader_uses_utf8(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "scripts" / "ops").mkdir(parents=True)
    (tmp_path / "scripts" / "ops" / "a.py").write_text("def f():\n    return '한글'\n", encoding="utf-8")
    calls = _spy(monkeypatch, "read_text")
    assert cf.patterns_for_diff({"scripts/ops/a.py": {1}}) == ["scripts.ops.a.x_f__mutmut_*"]
    assert cf.files_for_diff({"scripts/ops/a.py": {1}}) == ["scripts/ops/a.py"]
    assert cf.files_for_diff({"scripts/ops/nofile.py": {1}}) == []
    assert cf.patterns_for_diff({"scripts/ops/nofile.py": {1}}) == []
    mine = [k for name, _a, k in calls if name == "a.py"]
    assert mine == [{"encoding": "utf-8"}, {"encoding": "utf-8"}]


def test_tests_for_files_selection_rules():
    texts = {
        "tests/test_b.py": "nothing",
        "tests/test_a_dotted.py": "x = 'scripts.ops.a_long'",  # 점 경로 부분 문자열만 일치
        "tests/test_c_stem.py": "import a",  # 파일명(stem)만 일치
        "tests/test_d_sub.py": "import abc",  # 단어 경계 불일치
        "tests/test_e_both.py": "import b",  # 두 번째 파일의 stem
        "tests/test_f_self.py": "zzz",  # 변경 파일 목록에 직접 포함
        "tests/test_zz.py": "scripts.ops.b",
    }
    files = ["scripts/ops/a.py", "scripts/ops/b.py", "tests/test_f_self.py"]

    def reader(p):
        if p == "tests/test_ioerr.py":
            _raise_oserror(p)
        return texts[p]

    tests = [*texts, "tests/test_ioerr.py"]
    got = cf.tests_for_files(files, tests, read=reader)
    assert got == ["tests/test_a_dotted.py", "tests/test_c_stem.py", "tests/test_e_both.py", "tests/test_f_self.py", "tests/test_zz.py"]


def test_tests_for_files_ioerror_does_not_stop_and_sorted():
    def reader(p):
        if p == "t1.py":
            _raise_oserror(p)
        return "import a"

    assert cf.tests_for_files(["x/a.py"], ["t3.py", "t1.py", "t2.py"], read=reader) == ["t2.py", "t3.py"]


def test_tests_for_files_stem_is_regex_escaped():
    files = ["scripts/a+b.py"]
    assert cf.tests_for_files(files, ["t.py"], read=lambda p: "aab") == []
    assert cf.tests_for_files(files, ["t.py"], read=lambda p: "use a+b here") == ["t.py"]


def test_tests_for_files_self_entry_is_not_read():
    def reader(p):
        raise AssertionError("변경된 시험 파일 자체는 읽지 않는다")

    assert cf.tests_for_files(["tests/test_q.py"], ["tests/test_q.py"], read=reader) == ["tests/test_q.py"]


def test_tests_for_files_default_reader_tolerates_bad_bytes(tmp_path):
    p = tmp_path / "test_bad.py"
    p.write_bytes(b"import a\n\xff\xfe\n")
    assert cf.tests_for_files(["x/a.py"], [str(p)]) == [str(p)]
    assert cf.tests_for_files(["x/a.py"], [str(tmp_path / "absent.py")]) == []


def test_rewrite_toml_list_exact_formatting():
    assert cf.rewrite_toml_list('k = ["a"]\n', "k", ["x", "y", "z"]) == 'k = ["x", "y", "z"]\n'
    assert cf.rewrite_toml_list('k = ["a"]\n', "k", []) == "k = []\n"
    # 여러 줄 목록
    assert cf.rewrite_toml_list('[t]\nk = [\n  "a",\n  "b",\n]\nz = 1\n', "k", ["q"]) == '[t]\nk = ["q"]\nz = 1\n'
    # 첫 번째 것만 교체(count=1)
    assert cf.rewrite_toml_list('k = ["a"]\n[o]\nk = ["b"]\n', "k", ["q"]) == 'k = ["q"]\n[o]\nk = ["b"]\n'
    # 줄 처음에서 시작할 때만(다른 키의 접미 / 주석 제외), 줄 중간 줄바꿈 뒤는 매치(re.M)
    assert cf.rewrite_toml_list('xk = ["a"]\n# k = ["a"]\n', "k", ["q"]) == 'xk = ["a"]\n# k = ["a"]\n'
    assert cf.rewrite_toml_list('a = 1\nk = ["a"]\n', "k", ["q"]) == 'a = 1\nk = ["q"]\n'
    # 키가 없으면 그대로
    assert cf.rewrite_toml_list("a = 1\n", "k", ["q"]) == "a = 1\n"
    # 값의 역슬래시는 정규식 치환 템플릿으로 해석되지 않는다
    assert cf.rewrite_toml_list('k = ["a"]\n', "k", ["q\\x\\1"]) == 'k = ["q\\x\\1"]\n'
    # 키의 특수문자는 이스케이프
    assert cf.rewrite_toml_list('a.b = ["1"]\naxb = ["2"]\n', "axb", ["q"]) == 'a.b = ["1"]\naxb = ["q"]\n'
    assert cf.rewrite_toml_list('axb = ["2"]\n', "a.b", ["q"]) == 'axb = ["2"]\n'


# ---- main ----
@pytest.fixture
def rec(monkeypatch):
    """main 이 쓰는 협력 함수를 기록기로 바꾼다."""
    r = {"cl": [], "files": [], "tests": [], "patterns": [], "ret": {"files": ["f1.py", "f2.py"], "tests": ["t1", "t2"], "patterns": ["p1", "p2", "p3"]}}
    ranges = {"scripts/a.py": {1}}

    def cl(*a, **k):
        r["cl"].append((a, k))
        return ranges

    def fd(rg, *a, **k):
        r["files"].append((rg, a, k))
        return r["ret"]["files"]

    def tf(files, tests, *a, **k):
        r["tests"].append((files, sorted(tests), a, k))
        return r["ret"]["tests"]

    def pd(rg, *a, **k):
        r["patterns"].append((rg, a, k))
        return r["ret"]["patterns"]

    monkeypatch.setattr(cf, "changed_line_ranges", cl)
    monkeypatch.setattr(cf, "files_for_diff", fd)
    monkeypatch.setattr(cf, "tests_for_files", tf)
    monkeypatch.setattr(cf, "patterns_for_diff", pd)
    r["ranges"] = ranges
    return r


def test_main_usage_errors(rec, capsys):
    assert cf.main([]) == 2
    out = capsys.readouterr()
    assert out.err == USAGE and out.out == ""
    for argv in (["--files"], ["--tests"], ["--limit", "3"], ["--write-source-paths", "x.toml"], ["--files", "--tests", "--limit", "1"]):
        assert cf.main(argv) == 2
        out = capsys.readouterr()
        assert out.err == USAGE and out.out == ""
    assert rec["cl"] == []


def test_main_base_head_defaults(rec, capsys):
    assert cf.main(["B"]) == 0
    assert rec["cl"][-1] == (("B", "HEAD"), {})
    assert cf.main(["B", "H"]) == 0
    assert rec["cl"][-1] == (("B", "H"), {})
    assert cf.main(["B", "H", "extra"]) == 0
    assert rec["cl"][-1] == (("B", "H"), {})
    assert rec["patterns"][-1] == (rec["ranges"], (), {})
    capsys.readouterr()


def test_main_default_prints_all_patterns(rec, capsys):
    assert cf.main(["B"]) == 0
    out = capsys.readouterr()
    assert out.out == "p1\np2\np3\n" and out.err == ""
    rec["ret"]["patterns"] = []
    assert cf.main(["B"]) == 0
    out = capsys.readouterr()
    assert out.out == "\n" and out.err == ""


def test_main_limit_boundaries(rec, capsys):
    assert cf.main(["B", "--limit", "2"]) == 0
    out = capsys.readouterr()
    assert out.out == "p1\np2\n"
    assert out.err == "[changed_functions] 3개 중 앞 2개만 출력(상한)\n"
    # 상한 == 개수 -> 절삭 없음
    assert cf.main(["B", "--limit", "3"]) == 0
    out = capsys.readouterr()
    assert out.out == "p1\np2\np3\n" and out.err == ""
    assert cf.main(["B", "--limit", "99"]) == 0
    assert capsys.readouterr().out == "p1\np2\np3\n"
    assert cf.main(["B", "--limit", "1"]) == 0
    out = capsys.readouterr()
    assert out.out == "p1\n" and "3개 중 앞 1개" in out.err
    # 0 = 무제한, 값 없이 끝나도 오류 없음, 위치 무관
    assert cf.main(["B", "--limit", "0"]) == 0
    out = capsys.readouterr()
    assert out.out == "p1\np2\np3\n" and out.err == ""
    assert cf.main(["B", "--limit"]) == 0
    out = capsys.readouterr()
    assert out.out == "p1\np2\np3\n" and out.err == ""
    assert cf.main(["--limit", "2", "B", "H"]) == 0
    assert rec["cl"][-1] == (("B", "H"), {})
    assert capsys.readouterr().out == "p1\np2\n"


def test_main_files_flag(rec, capsys):
    assert cf.main(["--files", "B", "H"]) == 0
    out = capsys.readouterr()
    assert out.out == "f1.py\nf2.py\n" and out.err == ""
    assert rec["cl"][-1] == (("B", "H"), {})
    assert rec["files"][-1] == (rec["ranges"], (), {})
    assert rec["patterns"] == []
    rec["ret"]["files"] = []
    assert cf.main(["B", "--files"]) == 0
    assert capsys.readouterr().out == "\n"


def test_main_tests_flag_lists_test_files(rec, capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests" / "sub").mkdir(parents=True)
    for n in ("tests/test_x.py", "tests/sub/test_y.py", "tests/helper.py", "tests/sub/conftest.py", "tests/test_z.txt"):
        (tmp_path / n).write_text("", encoding="utf-8")
    assert cf.main(["B", "--tests"]) == 0
    out = capsys.readouterr()
    assert out.out == "t1\nt2\n" and out.err == ""
    assert rec["files"][-1] == (rec["ranges"], (), {})
    files, tests, a, k = rec["tests"][-1]
    assert files == ["f1.py", "f2.py"] and (a, k) == ((), {})
    assert tests == ["tests/sub/test_y.py", "tests/test_x.py"]  # 슬래시 정규화, test_*.py 만
    assert rec["patterns"] == []
    rec["ret"]["tests"] = []
    assert cf.main(["B", "--tests"]) == 0
    assert capsys.readouterr().out == "\n"


def test_main_tests_flag_beats_files_flag(rec, capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    assert cf.main(["--files", "--tests", "B"]) == 0
    assert capsys.readouterr().out == "t1\nt2\n"
    assert cf.main(["--tests", "--files", "B"]) == 0
    assert capsys.readouterr().out == "t1\nt2\n"


def test_main_write_source_paths(rec, capsys, tmp_path, monkeypatch):
    target = tmp_path / "pyproject.toml"
    original = '[tool.mutmut]\r\nsource_paths = ["x/", "y/"]\r\n# 한글\r\n'
    target.write_bytes(original.encode("utf-8"))
    reads = _spy(monkeypatch, "read_text")
    writes = _spy(monkeypatch, "write_text")
    replaces = _spy(monkeypatch, "replace")
    assert cf.main(["B", "H", "--write-source-paths", str(target)]) == 0
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
    assert rec["cl"][-1] == (("B", "H"), {})
    assert rec["files"][-1] == (rec["ranges"], (), {})
    assert target.read_bytes() == '[tool.mutmut]\nsource_paths = ["f1.py", "f2.py"]\n# 한글\n'.encode()
    assert not (tmp_path / "pyproject.toml.tmp").exists()
    assert reads == [("pyproject.toml", (), {"encoding": "utf-8"})]
    assert [w[0] for w in writes] == ["pyproject.toml.tmp"]
    assert writes[0][2] == {"encoding": "utf-8", "newline": "\n"}
    assert [r_[0] for r_ in replaces] == ["pyproject.toml.tmp"]
    assert replaces[0][1] == (target,)
    assert rec["patterns"] == [] and rec["tests"] == []


def test_main_write_source_paths_writes_lf_and_beats_other_flags(rec, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    target = tmp_path / "p.toml"
    target.write_text('source_paths = ["a"]\n', encoding="utf-8", newline="\n")
    assert cf.main(["--tests", "--files", "--write-source-paths", "p.toml", "B"]) == 0
    assert capsys.readouterr().out == ""
    assert target.read_bytes() == b'source_paths = ["f1.py", "f2.py"]\n'
    assert rec["tests"] == []


def test_main_write_source_paths_value_is_consumed(rec, tmp_path, monkeypatch, capsys):
    target = tmp_path / "p.toml"
    target.write_text('source_paths = ["a"]\n', encoding="utf-8")
    # 값이 위치 인자로 새어 나가면 BASE 가 바뀐다
    assert cf.main(["--write-source-paths", str(target), "B"]) == 0
    assert rec["cl"][-1] == (("B", "HEAD"), {})
    # 값이 없으면(빈 문자열) 쓰기 분기가 아니라 기본 출력
    assert cf.main(["B", "--write-source-paths"]) == 0
    assert capsys.readouterr().out == "p1\np2\np3\n"
