"""audit-kit 게이트(tools/hooks/audit_kit_gate.py) — 가짜 audit-kit 으로 막힘/통과/미설치/기존 항목/잡음을 확인한다.

진짜 audit-kit·git·네트워크를 쓰지 않는다. 가짜 audit-kit 은 `hook` 서브명령으로 불리면 미리 정한 stderr 를 내고 정해 둔 종료코드로 끝난다.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from tools.hooks import audit_kit_gate as gate


@pytest.fixture
def fake_kit(tmp_path, monkeypatch):
    """가짜 audit-kit: tmp_path/'plan.json' 의 {"rc":..., "stderr":...} 대로 동작. AUDIT_KIT_BIN 으로 연결."""
    script = tmp_path / "fake_audit_kit.py"
    script.write_text(
        textwrap.dedent(
            """
            import json, pathlib, sys
            plan = json.loads((pathlib.Path(__file__).parent / "plan.json").read_text(encoding="utf-8"))
            sys.stdin.read()
            sys.stderr.write(plan["stderr"])
            sys.exit(plan["rc"])
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AUDIT_KIT_BIN", str(script))

    def plan(rc: int, stderr: str = "") -> None:
        (tmp_path / "plan.json").write_text(json.dumps({"rc": rc, "stderr": stderr}), encoding="utf-8")

    plan(0)
    return plan


@pytest.fixture
def py_file(tmp_path, monkeypatch):
    """저장소 안에 있는 것으로 보이는 .py 파일(ROOT 를 tmp_path 로 바꾼다)."""
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n", encoding="utf-8")
    return f


class _Result:
    def __init__(self, returncode: int, stderr: str) -> None:
        self.returncode, self.stderr = returncode, stderr


@pytest.fixture
def _capture(capsys):
    return capsys


def _post_edit(path: Path, capsys=None) -> _Result:
    """게이트를 같은 프로세스에서 실행(ROOT monkeypatch 가 적용되게). stderr 는 capsys 로 읽는다."""
    payload = json.dumps({"tool_input": {"file_path": str(path)}, "cwd": str(path.parent)})
    rc = gate.run_post_edit(payload)
    return _Result(rc, capsys.readouterr().err if capsys is not None else "")


# ── 출력 해석 ─────────────────────────────────────────────────────────────


def test_new_findings_keeps_only_new_real_items():
    text = "\n".join(
        [
            "audit-kit: a.py 검사에서 4건 발견",
            "[표준 STD-02] a.py:5 절대경로 하드코딩",
            "[표준 EFF-03] a.py:9 반복문 안에서 open() 호출 (기존)",
            "[mypy import-not-found] a.py:1 Cannot find implementation or library stub for module named \"fastapi\"",
            "[cycle] 순환 임포트: a -> b -> a",
            "수정 후 다시 저장하세요.",
        ]
    )
    assert gate.new_findings(text) == ["[표준 STD-02] a.py:5 절대경로 하드코딩", "[cycle] 순환 임포트: a -> b -> a"]


def test_new_findings_empty_for_blank_or_noise_only():
    assert gate.new_findings("") == []
    assert gate.new_findings("[mypy import-untyped] a.py:1 Library stubs not installed") == []


# ── audit-kit 찾기 ────────────────────────────────────────────────────────


def test_find_audit_kit_uses_env_for_py_and_exe(tmp_path):
    py = tmp_path / "k.py"
    py.write_text("", encoding="utf-8")
    assert gate.find_audit_kit(tmp_path, {"AUDIT_KIT_BIN": str(py)}) == [sys.executable, str(py)]
    exe = tmp_path / "kit.exe"
    exe.write_text("", encoding="utf-8")
    assert gate.find_audit_kit(tmp_path, {"AUDIT_KIT_BIN": str(exe)}) == [str(exe)]
    assert gate.find_audit_kit(tmp_path, {"AUDIT_KIT_BIN": str(tmp_path / "nope")}) is None  # 지정했는데 없으면 다른 곳을 뒤지지 않는다


def test_find_audit_kit_searches_parent_audit_tools(tmp_path):
    scripts = tmp_path / "audit-tools" / "audit-kit" / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "audit-kit.exe").write_text("", encoding="utf-8")
    nested = tmp_path / "work" / "repo" / "sub"
    nested.mkdir(parents=True)
    assert gate.find_audit_kit(nested, {}) == [str(scripts / "audit-kit.exe")]


# ── PostToolUse ───────────────────────────────────────────────────────────


def test_post_edit_blocks_new_findings(fake_kit, py_file, capsys):
    fake_kit(2, "audit-kit: mod.py 검사에서 1건 발견\n[표준 STD-02] mod.py:1 절대경로 하드코딩\n수정 후 다시 저장하세요.\n")
    proc = _post_edit(py_file, capsys)
    assert proc.returncode == 2
    assert "STD-02" in proc.stderr and "고친 뒤 다시 저장" in proc.stderr


def test_post_edit_passes_when_clean_or_only_existing(fake_kit, py_file, capsys):
    fake_kit(0)
    assert _post_edit(py_file, capsys).returncode == 0
    fake_kit(2, "audit-kit: mod.py 검사에서 1건 발견\n[표준 EFF-03] mod.py:3 반복문 안에서 open() 호출 (기존)\n")
    assert _post_edit(py_file, capsys).returncode == 0  # 이번 편집 이전부터 있던 문제는 막지 않는다


def test_post_edit_ignores_non_python_and_outside_repo(fake_kit, py_file, tmp_path, capsys):
    fake_kit(2, "[표준 STD-02] x\n")
    txt = tmp_path / "notes.txt"
    txt.write_text("x", encoding="utf-8")
    assert _post_edit(txt, capsys).returncode == 0
    outside = tmp_path.parent / "outside_scratch.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    try:
        assert _post_edit(outside, capsys).returncode == 0  # 저장소 밖 파일(임시 스크립트)은 대상이 아니다
    finally:
        outside.unlink(missing_ok=True)


def test_post_edit_is_fail_open_when_kit_missing_or_broken(py_file, monkeypatch, fake_kit, capsys):
    monkeypatch.delenv("AUDIT_KIT_REQUIRED", raising=False)  # 이 시험은 '필수 아님' 모드의 fail-open 을 본다 — 개발 PC·CI 환경에 켜져 있어도 격리한다
    monkeypatch.setenv("AUDIT_KIT_BIN", str(py_file.parent / "does_not_exist.py"))
    proc = _post_edit(py_file, capsys)
    assert proc.returncode == 0 and "찾지 못해" in proc.stderr  # 미설치 PC·CI 를 막지 않되 이유는 알린다
    monkeypatch.setenv("AUDIT_KIT_BIN", str(py_file.parent / "fake_audit_kit.py"))
    fake_kit(1, "Traceback: boom")
    proc = _post_edit(py_file, capsys)
    assert proc.returncode == 0 and "검사하지 못했습니다" in proc.stderr  # 도구 자체 오류도 작업을 막지 않는다


def test_post_edit_ignores_garbage_input():
    assert gate.run_post_edit("") == 0
    assert gate.run_post_edit("{깨진 json") == 0
    assert gate.run_post_edit(json.dumps({"tool_input": {}})) == 0


# ── Stop ──────────────────────────────────────────────────────────────────


def test_stop_blocks_with_decision_json(fake_kit, py_file, monkeypatch, capsys):
    fake_kit(2, "[표준 STD-02] mod.py:1 절대경로 하드코딩\n")
    from tools.hooks import post_edit_fast_gate as pef

    monkeypatch.setattr(pef, "load_session_edits", lambda _sid: [str(py_file)])
    monkeypatch.setattr(pef, "cleanup_old_session_edit_files", lambda: None)
    assert gate.run_stop(json.dumps({"session_id": "s1"})) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "block" and "신규 문제 1건" in out["reason"]


def test_stop_passes_when_no_edits_or_loop_guard(fake_kit, py_file, monkeypatch, capsys):
    fake_kit(2, "[표준 STD-02] mod.py:1 x\n")
    from tools.hooks import post_edit_fast_gate as pef

    monkeypatch.setattr(pef, "cleanup_old_session_edit_files", lambda: None)
    monkeypatch.setattr(pef, "load_session_edits", lambda _sid: [])
    assert gate.run_stop(json.dumps({"session_id": "s1"})) == 0 and capsys.readouterr().out == ""
    monkeypatch.setattr(pef, "load_session_edits", lambda _sid: [str(py_file)])
    assert gate.run_stop(json.dumps({"session_id": "s1", "stop_hook_active": True})) == 0 and capsys.readouterr().out == ""  # 무한 루프 방지


def test_unknown_mode_does_not_block(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", type("S", (), {"isatty": lambda self: True, "read": lambda self: ""})())
    assert gate.main(["--nope"]) == 0
    assert "알 수 없는 모드" in capsys.readouterr().err


# ── verify_change 연동: 기준 트리와의 차이만 "이번 변경이 만든 문제" ──────────────────


def _two_trees(tmp_path):
    base, head = tmp_path / "base", tmp_path / "head"
    for tree in (base, head):
        (tree / "pkg").mkdir(parents=True)
    (base / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (head / "pkg" / "a.py").write_text("x = 2\n", encoding="utf-8")
    (head / "pkg" / "new.py").write_text("y = 1\n", encoding="utf-8")  # 기준에 없는 새 파일
    return base, head


@pytest.fixture
def tree_aware_kit(tmp_path, monkeypatch):
    """변경 트리(경로에 'head')에서는 두 건, 기준 트리에서는 그중 한 건만 보고하는 가짜 audit-kit. 줄 번호는 다르게."""
    script = tmp_path / "tree_kit.py"
    nl = chr(10)
    body = [
        "import json, sys",
        "data = json.loads(sys.stdin.read())",
        "path = data['tool_input']['file_path'].replace(chr(92), '/')",
        "name = path.rsplit('/', 1)[-1]",
        "nl = chr(10)",
        "if '/head/' in path:",
        "    sys.stderr.write('[표준 STD-02] pkg/' + name + ':30 절대경로 하드코딩 (기존)' + nl)",
        "    sys.stderr.write('[표준 EFF-03] pkg/' + name + ':8 반복문 안에서 open() 호출' + nl)",
        "    sys.exit(2)",
        "sys.stderr.write('[표준 STD-02] pkg/' + name + ':11 절대경로 하드코딩' + nl)",
        "sys.exit(2)",
    ]
    script.write_text(nl.join(body) + nl, encoding="utf-8")
    monkeypatch.setenv("AUDIT_KIT_BIN", str(script))


def test_verify_counts_only_findings_new_versus_base(tmp_path, tree_aware_kit):
    from tools import verify_change as vc

    base, head = _two_trees(tmp_path)
    found, note = vc._audit_kit_new_findings(["pkg/a.py", "pkg/new.py"], base, head)
    assert note == ""
    # a.py: STD-02 는 기준에도 있어(줄 번호만 다름) 제외, EFF-03 만 신규 / new.py: 기준에 없으므로 둘 다 신규
    assert sorted(x.split("] ", 1)[0].rsplit("[", 1)[-1] for x in found) == ["표준 EFF-03", "표준 EFF-03", "표준 STD-02"]
    assert not any(x.startswith("pkg/a.py") and "STD-02" in x for x in found)
    assert any(x.startswith("pkg/new.py") and "STD-02" in x for x in found)


def test_verify_skips_when_kit_missing(tmp_path, monkeypatch):
    from tools import verify_change as vc

    monkeypatch.setenv("AUDIT_KIT_BIN", str(tmp_path / "missing.py"))
    found, note = vc._audit_kit_new_findings(["pkg/a.py"], tmp_path, tmp_path)
    assert found == [] and "생략" in note


def test_verify_reports_unchecked_file_instead_of_passing_silently(tmp_path, monkeypatch):
    from tools import verify_change as vc

    script = tmp_path / "broken_kit.py"
    script.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
    monkeypatch.setenv("AUDIT_KIT_BIN", str(script))
    base, head = _two_trees(tmp_path)
    found, _ = vc._audit_kit_new_findings(["pkg/a.py"], base, head)
    assert found == ["pkg/a.py: audit-kit 검사를 하지 못했습니다"]  # 검사를 못 한 것을 '문제 없음'으로 처리하지 않는다


# ── mypy: 편집 전(HEAD)·기준 트리에 없던 신규 타입 오류만 ────────────────────────────


def test_mypy_python_only_for_real_audit_kit_executable(tmp_path):
    scripts_dir = tmp_path / "Scripts"
    scripts_dir.mkdir()
    (scripts_dir / "audit-kit.exe").write_text("", encoding="utf-8")
    (scripts_dir / "python.exe").write_text("", encoding="utf-8")
    assert gate.mypy_python([str(scripts_dir / "audit-kit.exe")]) == str(scripts_dir / "python.exe")
    assert gate.mypy_python([sys.executable, "fake_audit_kit.py"]) is None  # 가짜·직접 지정한 .py 는 mypy 를 돌리지 않는다
    (scripts_dir / "python.exe").unlink()
    assert gate.mypy_python([str(scripts_dir / "audit-kit.exe")]) is None


def test_mypy_new_reports_only_errors_absent_from_baseline(monkeypatch, tmp_path):
    outputs = {
        "cur.py": {"Incompatible return value type (got \"str\", expected \"int\")  [return-value]", "Missing return statement  [return]"},
        "base.py": {"Missing return statement  [return]"},
    }
    monkeypatch.setattr(gate, "mypy_keys", lambda _py, path, _root=None: outputs.get(path.name))
    new, why = gate.mypy_new("py", tmp_path / "cur.py", tmp_path / "base.py")
    assert why == "" and new == ["[mypy] cur.py: Incompatible return value type (got \"str\", expected \"int\")  [return-value]"]
    new, _ = gate.mypy_new("py", tmp_path / "cur.py", None)  # 기준이 없는 새 파일 = 전부 신규
    assert len(new) == 2


def test_mypy_new_reports_why_when_mypy_cannot_run(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "mypy_keys", lambda *_a, **_k: None)
    assert gate.mypy_new("py", tmp_path / "a.py", None) == ([], "mypy 를 실행하지 못했습니다")
    outputs = {"cur.py": set(), "base.py": None}
    monkeypatch.setattr(gate, "mypy_keys", lambda _py, path, _root=None: outputs[path.name])
    assert gate.mypy_new("py", tmp_path / "cur.py", tmp_path / "base.py")[1] == "기준 파일의 mypy 를 실행하지 못했습니다"


def test_mypy_keys_parses_error_lines_and_handles_failures(monkeypatch, tmp_path):
    class Proc:
        def __init__(self, rc, out):
            self.returncode, self.stdout = rc, out

    text = (
        b"pkg/a.py:3: error: Incompatible return value type (got \"str\", expected \"int\")  [return-value]\n"
        b"pkg/a.py:3: note: something helpful\n"
        b"pkg/b.py:9:5: error: Missing return statement  [return]\n"
    )
    monkeypatch.setattr(gate.subprocess, "run", lambda *_a, **_k: Proc(1, text))
    assert gate.mypy_keys("py", tmp_path / "a.py", tmp_path) == {
        "Incompatible return value type (got \"str\", expected \"int\")  [return-value]",
        "Missing return statement  [return]",
    }
    monkeypatch.setattr(gate.subprocess, "run", lambda *_a, **_k: Proc(0, b""))
    assert gate.mypy_keys("py", tmp_path / "a.py", tmp_path) == set()
    monkeypatch.setattr(gate.subprocess, "run", lambda *_a, **_k: Proc(2, b"fatal"))
    assert gate.mypy_keys("py", tmp_path / "a.py", tmp_path) is None  # mypy 자체 오류는 '오류 없음'으로 처리하지 않는다


def test_verify_includes_mypy_diff_against_base(tmp_path, tree_aware_kit, monkeypatch):
    import importlib

    from tools import verify_change as vc

    # verify_change 는 scripts/ops 를 경로에 넣고 `audit_kit_gate` 를 최상위 이름으로 가져온다 — 그 모듈 객체를 패치해야 한다
    akg = importlib.import_module("tools.hooks.audit_kit_gate")
    base, head = _two_trees(tmp_path)
    monkeypatch.setattr(akg, "mypy_python", lambda _kit: "py")
    calls = []

    def fake_batch(_py, paths, root=None):
        # head 트리: 옛 오류 'old' + 새 오류 'new', 기준 트리: 'old' 만 (일괄 1회씩 — 파일마다 따로 부르지 않는다)
        calls.append((root.name, sorted(p.name for p in paths)))
        keys = {"old", "new"} if root == head else {"old"}
        return {p: set(keys) for p in paths}

    monkeypatch.setattr(akg, "mypy_keys_batch", fake_batch)
    found, _ = vc._audit_kit_new_findings(["pkg/a.py", "pkg/new.py"], base, head)
    assert calls == [(head.name, ["a.py", "new.py"]), (base.name, ["a.py"])]  # head·base 각각 일괄 1회, 기준에는 기준 트리에 있는 파일만
    # 기준 트리에 있는 파일은 기준에도 있던 오류('old')를 빼고, 새 파일은 기준 없이 전부 신규로 본다
    assert "pkg/a.py: [mypy] a.py: new" in found and "pkg/a.py: [mypy] a.py: old" not in found
    assert "pkg/new.py: [mypy] new.py: new" in found and "pkg/new.py: [mypy] new.py: old" in found


def test_mypy_keys_retries_once_on_internal_error_and_serializes(monkeypatch, tmp_path):
    """병렬 검사에서 mypy 자체 오류(종료코드 2)가 한 번 나도 다시 시도해 결과를 얻는다 — verify_change 에서 실측된 일시 실패."""
    class Proc:
        def __init__(self, rc, out):
            self.returncode, self.stdout = rc, out

    answers = [Proc(2, b"cache error"), Proc(1, b"a.py:1: error: Missing return statement  [return]")]
    calls = []

    def fake_run(*_a, **_k):
        calls.append(1)
        return answers[len(calls) - 1]

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    assert gate.mypy_keys("py", tmp_path / "a.py", tmp_path) == {"Missing return statement  [return]"}
    assert len(calls) == 2
    calls.clear()
    answers[:] = [Proc(2, b"x"), Proc(2, b"x")]
    assert gate.mypy_keys("py", tmp_path / "a.py", tmp_path) is None  # 두 번 다 실패하면 '오류 없음'이 아니라 실행 못 함
    assert len(calls) == 2

def test_mypy_keys_treats_missing_mypy_module_as_not_run(monkeypatch, tmp_path):
    """`python -m mypy` 는 mypy 가 없으면 종료코드 1 + 빈 출력 — '오류 없음'(통과)으로 오인하면 타입 검사가 조용히 빠진다."""

    class Proc:
        returncode, stdout = 1, b""
        stderr = b"python.exe: No module named mypy"

    monkeypatch.setattr(gate.subprocess, "run", lambda *_a, **_k: Proc())
    assert gate.mypy_keys("py", tmp_path / "a.py", tmp_path) is None


def test_is_real_kit_only_for_audit_kit_executable():
    assert gate.is_real_kit(["x/.venv/Scripts/audit-kit.exe"]) and gate.is_real_kit(["audit-kit"])
    assert not gate.is_real_kit([sys.executable, "fake_audit_kit.py"])


def test_verify_fails_when_real_kit_has_no_python_for_mypy(tmp_path, tree_aware_kit, monkeypatch):
    """진짜 audit-kit 인데 mypy 를 돌릴 파이썬이 없으면 조용히 생략하지 않고 검사 결과(FAIL 사유)로 올린다."""
    import importlib

    from tools import verify_change as vc

    akg = importlib.import_module("tools.hooks.audit_kit_gate")
    base, head = _two_trees(tmp_path)
    monkeypatch.setattr(akg, "is_real_kit", lambda _kit: True)
    monkeypatch.setattr(akg, "mypy_python", lambda _kit: None)
    found, _ = vc._audit_kit_new_findings(["pkg/a.py"], base, head)
    assert any("mypy 실행 환경" in x for x in found)
    monkeypatch.setattr(akg, "is_real_kit", lambda _kit: False)  # 시험용 가짜 kit 는 기존처럼 mypy 없이 통과
    found, _ = vc._audit_kit_new_findings(["pkg/a.py"], base, head)
    assert not any("mypy 실행 환경" in x for x in found)


# ── 강제(AUDIT_KIT_REQUIRED)·커밋 단계(--staged) ─────────────────────────────


def _missing_kit(py_file, monkeypatch):
    monkeypatch.setenv("AUDIT_KIT_BIN", str(py_file.parent / "does_not_exist.py"))


def test_required_blocks_post_edit_when_kit_missing(py_file, monkeypatch, capsys):
    _missing_kit(py_file, monkeypatch)
    monkeypatch.setenv("AUDIT_KIT_REQUIRED", "1")
    proc = _post_edit(py_file, capsys)
    assert proc.returncode == 2 and "AUDIT_KIT_REQUIRED" in proc.stderr  # 필수 환경에선 미설치도 막는다


def test_required_blocks_stop_when_kit_missing(py_file, monkeypatch, capsys):
    from tools.hooks import post_edit_fast_gate as pef

    _missing_kit(py_file, monkeypatch)
    monkeypatch.setenv("AUDIT_KIT_REQUIRED", "1")
    monkeypatch.setattr(pef, "load_session_edits", lambda _sid: [str(py_file)])
    monkeypatch.setattr(pef, "cleanup_old_session_edit_files", lambda: None)
    assert gate.run_stop(json.dumps({"session_id": "s1"})) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "block" and "AUDIT_KIT_REQUIRED" in out["reason"]


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_not_required_values_stay_fail_open(py_file, monkeypatch, capsys, value):
    _missing_kit(py_file, monkeypatch)
    monkeypatch.setenv("AUDIT_KIT_REQUIRED", value)
    assert _post_edit(py_file, capsys).returncode == 0


def _staged(monkeypatch, files):
    monkeypatch.setattr(gate, "_staged_python_changes", lambda: [(f, None) for f in files])


def test_staged_blocks_commit_on_new_findings(fake_kit, py_file, monkeypatch, capsys):
    fake_kit(2, "audit-kit: mod.py 검사에서 1건 발견\n[표준 STD-02] mod.py:1 절대경로 하드코딩\n")
    _staged(monkeypatch, [py_file])
    assert gate.run_staged() == 1
    assert "STD-02" in capsys.readouterr().err


def test_staged_passes_when_clean_or_only_existing(fake_kit, py_file, monkeypatch):
    _staged(monkeypatch, [py_file])
    fake_kit(0)
    assert gate.run_staged() == 0
    fake_kit(2, "[표준 EFF-03] mod.py:3 반복문 안에서 open() 호출 (기존)\n")
    assert gate.run_staged() == 0  # 이번 변경 이전부터 있던 문제는 막지 않는다


def test_staged_with_nothing_staged_passes_without_kit(py_file, monkeypatch, capsys):
    _missing_kit(py_file, monkeypatch)
    monkeypatch.setenv("AUDIT_KIT_REQUIRED", "1")
    _staged(monkeypatch, [])
    assert gate.run_staged() == 0  # 검사할 .py 가 없으면 audit-kit 이 없어도 커밋을 막지 않는다


def test_staged_skips_when_kit_missing_unless_required(py_file, monkeypatch, capsys):
    _missing_kit(py_file, monkeypatch)
    _staged(monkeypatch, [py_file])
    monkeypatch.delenv("AUDIT_KIT_REQUIRED", raising=False)
    assert gate.run_staged() == 0
    assert "찾지 못해" in capsys.readouterr().err
    monkeypatch.setenv("AUDIT_KIT_REQUIRED", "1")
    assert gate.run_staged() == 1
    assert "AUDIT_KIT_REQUIRED" in capsys.readouterr().err


def test_main_dispatches_staged_mode(fake_kit, py_file, monkeypatch):
    fake_kit(2, "[표준 STD-02] mod.py:1 x\n")
    _staged(monkeypatch, [py_file])
    monkeypatch.setattr(sys, "stdin", type("S", (), {"isatty": lambda self: True, "read": lambda self: ""})())
    assert gate.main(["--staged"]) == 1

