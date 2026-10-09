"""merge_stage.py(③ 병합 게이트) — verify_change/subprocess 를 모두 모킹해 실제 병합 없이 검증.

실제 verify_change.py 는 ~15분 걸리므로 여기서는 절대 호출하지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import merge_stage  # noqa: E402


def test_tag_name_strips_stage_prefix():
    assert merge_stage.tag_name_for("stage/skeleton-gate") == "verified/skeleton-gate"
    assert merge_stage.tag_name_for("feature-x") == "verified/feature-x"


def _stub_branch_and_tag(monkeypatch, *, branch: str = "master", tag_exists: bool = False):
    """대부분의 테스트는 '현재 master 위에 있고 태그가 아직 없다'는 정상 전제를 쓴다."""
    monkeypatch.setattr(merge_stage, "current_branch", lambda root=None: branch)
    monkeypatch.setattr(merge_stage, "tag_exists", lambda tag, root=None: tag_exists)


def test_dry_run_does_not_merge_or_tag(monkeypatch):
    calls = {"merge": 0, "tag": 0}
    _stub_branch_and_tag(monkeypatch)

    monkeypatch.setattr(
        merge_stage,
        "run_verify_change",
        lambda base, branch, path: {"ok": True, "report": "PASS table", "changed": ["a.py"]},
    )
    monkeypatch.setattr(merge_stage, "dirty_paths", lambda: set())
    monkeypatch.setattr(merge_stage, "do_merge", lambda b: calls.__setitem__("merge", calls["merge"] + 1))
    monkeypatch.setattr(merge_stage, "do_tag", lambda t, m: calls.__setitem__("tag", calls["tag"] + 1))

    rc = merge_stage.main(["stage/skeleton-gate", "--dry-run"])
    assert rc == 0
    assert calls == {"merge": 0, "tag": 0}


def test_fail_refuses_merge(monkeypatch):
    calls = {"merge": 0, "tag": 0}
    _stub_branch_and_tag(monkeypatch)
    monkeypatch.setattr(
        merge_stage,
        "run_verify_change",
        lambda base, branch, path: {"ok": False, "report": "FAIL table", "changed": ["a.py"]},
    )
    monkeypatch.setattr(merge_stage, "dirty_paths", lambda: set())
    monkeypatch.setattr(merge_stage, "do_merge", lambda b: calls.__setitem__("merge", calls["merge"] + 1))
    monkeypatch.setattr(merge_stage, "do_tag", lambda t, m: calls.__setitem__("tag", calls["tag"] + 1))

    rc = merge_stage.main(["stage/skeleton-gate"])
    assert rc == 1
    assert calls == {"merge": 0, "tag": 0}


def test_overlap_with_dirty_worktree_refuses(monkeypatch):
    calls = {"merge": 0, "tag": 0}
    _stub_branch_and_tag(monkeypatch)
    monkeypatch.setattr(
        merge_stage,
        "run_verify_change",
        lambda base, branch, path: {"ok": True, "report": "PASS table", "changed": ["a.py", "b.py"]},
    )
    monkeypatch.setattr(merge_stage, "dirty_paths", lambda: {"b.py"})
    monkeypatch.setattr(merge_stage, "do_merge", lambda b: calls.__setitem__("merge", calls["merge"] + 1))
    monkeypatch.setattr(merge_stage, "do_tag", lambda t, m: calls.__setitem__("tag", calls["tag"] + 1))

    rc = merge_stage.main(["stage/skeleton-gate"])
    assert rc == 1
    assert calls == {"merge": 0, "tag": 0}


def test_pass_calls_merge_and_tag(monkeypatch):
    calls = {}
    _stub_branch_and_tag(monkeypatch)

    class FakeCP:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(
        merge_stage,
        "run_verify_change",
        lambda base, branch, path: {"ok": True, "report": "PASS table", "changed": ["a.py"]},
    )
    monkeypatch.setattr(merge_stage, "dirty_paths", lambda: set())

    def fake_merge(b):
        calls["merge"] = b
        return FakeCP()

    def fake_tag(t, m):
        calls["tag"] = (t, m)
        return FakeCP()

    monkeypatch.setattr(merge_stage, "do_merge", fake_merge)
    monkeypatch.setattr(merge_stage, "do_tag", fake_tag)

    rc = merge_stage.main(["stage/skeleton-gate"])
    assert rc == 0
    assert calls["merge"] == "stage/skeleton-gate"
    assert calls["tag"][0] == "verified/skeleton-gate"


# ── 리뷰 반영 신규 테스트 ────────────────────────────────────────────────


def test_wrong_branch_refuses_normal_run(monkeypatch):
    """현재 브랜치가 --base 와 다르면 거부(정상 실행)."""
    calls = {"merge": 0, "tag": 0, "verify": 0}
    _stub_branch_and_tag(monkeypatch, branch="stage/some-other-work")
    monkeypatch.setattr(
        merge_stage,
        "run_verify_change",
        lambda base, branch, path: (
            calls.__setitem__("verify", calls["verify"] + 1) or {"ok": True, "report": "PASS", "changed": []}
        ),
    )
    monkeypatch.setattr(merge_stage, "do_merge", lambda b: calls.__setitem__("merge", calls["merge"] + 1))
    monkeypatch.setattr(merge_stage, "do_tag", lambda t, m: calls.__setitem__("tag", calls["tag"] + 1))

    rc = merge_stage.main(["stage/skeleton-gate", "--base", "master"])
    assert rc == 1
    assert calls == {"merge": 0, "tag": 0, "verify": 0}  # verify_change 조차 실행되지 않음


def test_wrong_branch_refuses_dry_run(monkeypatch):
    """--dry-run 이어도 브랜치가 다르면 거부한다(틀린 전제로 계획을 세우지 않음)."""
    calls = {"verify": 0}
    _stub_branch_and_tag(monkeypatch, branch="stage/some-other-work")
    monkeypatch.setattr(
        merge_stage,
        "run_verify_change",
        lambda base, branch, path: (
            calls.__setitem__("verify", calls["verify"] + 1) or {"ok": True, "report": "PASS", "changed": []}
        ),
    )

    rc = merge_stage.main(["stage/skeleton-gate", "--base", "master", "--dry-run"])
    assert rc == 1
    assert calls["verify"] == 0


def test_existing_tag_refuses_before_merge(monkeypatch):
    """verified/<name> 태그가 이미 있으면 verify_change 조차 실행하지 않고 거부한다."""
    calls = {"merge": 0, "tag": 0, "verify": 0}
    _stub_branch_and_tag(monkeypatch, branch="master", tag_exists=True)
    monkeypatch.setattr(
        merge_stage,
        "run_verify_change",
        lambda base, branch, path: (
            calls.__setitem__("verify", calls["verify"] + 1) or {"ok": True, "report": "PASS", "changed": []}
        ),
    )
    monkeypatch.setattr(merge_stage, "do_merge", lambda b: calls.__setitem__("merge", calls["merge"] + 1))
    monkeypatch.setattr(merge_stage, "do_tag", lambda t, m: calls.__setitem__("tag", calls["tag"] + 1))

    rc = merge_stage.main(["stage/skeleton-gate"])
    assert rc == 1
    assert calls == {"merge": 0, "tag": 0, "verify": 0}


def test_verify_change_crash_is_clean_refusal(monkeypatch):
    """verify_change.py 프로세스 자체가 예외를 던져도(크래시) traceback 없이 깔끔히 거부한다."""
    _stub_branch_and_tag(monkeypatch)

    def boom(*args, **kwargs):
        raise OSError("verify_change crashed")

    monkeypatch.setattr(merge_stage.subprocess, "run", boom)

    rc = merge_stage.main(["stage/skeleton-gate"])
    assert rc == 1  # 절대 예외로 죽지 않고 정상적으로 거부 코드 반환


def test_run_verify_change_empty_json_path_is_clean_refusal(monkeypatch):
    """subprocess 는 정상 종료했지만(returncode 0) json_path 가 비어있으면(mkstemp 빈 파일) 거부."""
    _stub_branch_and_tag(monkeypatch)

    class FakeCP:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(merge_stage.subprocess, "run", lambda *a, **kw: FakeCP())

    rc = merge_stage.main(["stage/skeleton-gate"])
    assert rc == 1


def test_garbage_json_result_is_clean_refusal(monkeypatch):
    """JSON 파일은 만들어졌지만(mkstemp 처럼) 파싱 불가한 내용이면 깔끔한 거부가 된다."""
    result = merge_stage._validate_verify_result("{not valid json", 0, "")
    assert result["ok"] is False
    assert "파싱" in result["report"]


def test_empty_json_file_is_clean_refusal():
    """mkstemp 가 만든 빈 파일 그대로(내용 없음)면 '파일 존재'만으로 신뢰하지 않는다."""
    result = merge_stage._validate_verify_result("", 1, "boom: crashed")
    assert result["ok"] is False
    assert "crashed" in result["report"] or "returncode" in result["report"]


def test_non_dict_json_is_clean_refusal():
    result = merge_stage._validate_verify_result("[1, 2, 3]", 0, "")
    assert result["ok"] is False


def test_missing_ok_key_is_clean_refusal():
    result = merge_stage._validate_verify_result('{"report": "no ok key"}', 0, "")
    assert result["ok"] is False


def test_dirty_paths_parses_nul_separated_status(monkeypatch):
    """dirty_paths 는 -z(NUL 구분) 출력을 파싱한다 — 공백 포함 경로도 안전."""
    fake_stdout = "\0".join([" M a b.py", "?? new dir/c.py", ""])

    class FakeCP:
        stdout = fake_stdout

    monkeypatch.setattr(merge_stage, "run", lambda args, cwd=None, **kw: FakeCP())
    paths = merge_stage.dirty_paths()
    assert "a b.py" in paths
    assert "new dir/c.py" in paths
