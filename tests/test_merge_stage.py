"""merge_stage.py(③ 병합 게이트) — verify_change/subprocess 를 모두 모킹해 실제 병합 없이 검증.

실제 verify_change.py 는 ~15분 걸리므로 여기서는 절대 호출하지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ops import merge_stage  # noqa: E402


def test_tag_name_strips_stage_prefix():
    assert merge_stage.tag_name_for("stage/skeleton-gate") == "verified/skeleton-gate"
    assert merge_stage.tag_name_for("feature-x") == "verified/feature-x"


def test_dry_run_does_not_merge_or_tag(monkeypatch):
    calls = {"merge": 0, "tag": 0}

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
