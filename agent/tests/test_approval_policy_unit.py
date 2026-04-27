"""agent.approval_policy — 단위 테스트.

파일 I/O 는 tmp_path 에 fake xlsx 파일을 놓고, ``AGENT_WORK_DIR`` /
``AGENT_OUTPUT_DIR`` 을 monkeypatch 로 바꿔 격리한다.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    from agent import config as _cfg
    work = tmp_path / "work"
    out = tmp_path / "output"
    work.mkdir()
    out.mkdir()
    sample = work / "sample.xlsx"
    sample.write_bytes(b"dummy")  # 존재만 하면 된다 — approval_policy 는 파싱 안함
    monkeypatch.setattr(_cfg, "AGENT_WORK_DIR", work)
    monkeypatch.setattr(_cfg, "AGENT_OUTPUT_DIR", out)
    return {
        "work": work, "out": out, "sample": sample,
        "target": out / "target.xlsx",
    }


# ──────────────────────────────────────────────────────────────────
# action 허용 여부
# ──────────────────────────────────────────────────────────────────
def test_unknown_action_rejected(paths):
    from agent import approval_policy as ap
    d = ap.evaluate({"id": "x", "action": "cad.run_something",
                     "file_path": str(paths["sample"])})
    assert d.allowed is False
    assert d.error == "action_not_allowed"
    assert d.approved is False


def test_task_must_be_dict():
    from agent import approval_policy as ap
    d = ap.evaluate("not a dict")  # type: ignore[arg-type]
    assert d.allowed is False
    assert d.error == "action_not_allowed"


# ──────────────────────────────────────────────────────────────────
# low action (read_cell)
# ──────────────────────────────────────────────────────────────────
def test_low_read_action_allowed_without_approval(paths):
    from agent import approval_policy as ap
    d = ap.evaluate({
        "id": "t1", "action": "excel.read_cell",
        "file_path": str(paths["sample"]),
        "cell_ref": "A1",
    })
    assert d.allowed is True
    assert d.error is None
    assert d.approved is True
    assert d.risk_level == "low"
    assert d.category == "excel_com"
    assert d.approved_by is None


def test_low_run_poc_requires_save_as_even_though_low(paths):
    """run_poc 는 low 지만 B2 쓰기가 있으므로 save_as 없는 요청은 거부."""
    from agent import approval_policy as ap
    d = ap.evaluate({
        "id": "t1", "action": "excel.run_poc",
        "file_path": str(paths["sample"]),
    })
    assert d.allowed is False
    assert d.error == "save_as_required"


def test_low_run_poc_with_valid_save_as(paths):
    from agent import approval_policy as ap
    d = ap.evaluate({
        "id": "t1", "action": "excel.run_poc",
        "file_path": str(paths["sample"]),
        "save_as": str(paths["target"]),
    })
    assert d.allowed is True
    assert d.approved is True


# ──────────────────────────────────────────────────────────────────
# medium action — approval 게이트
# ──────────────────────────────────────────────────────────────────
def test_medium_write_cell_blocked_without_token(paths):
    from agent import approval_policy as ap
    d = ap.evaluate({
        "id": "t1", "action": "excel.write_cell",
        "file_path": str(paths["sample"]),
        "save_as": str(paths["target"]),
        "cell_ref": "B2", "value": "X",
    })
    assert d.allowed is False
    assert d.error == "approval_required"
    assert d.risk_level == "medium"
    assert d.approved is False


def test_medium_write_cell_allowed_with_token(paths):
    from agent import approval_policy as ap
    d = ap.evaluate({
        "id": "t1", "action": "excel.write_cell",
        "file_path": str(paths["sample"]),
        "save_as": str(paths["target"]),
        "cell_ref": "B2", "value": "X",
        "approval_token": "tok-xyz",
        "approved_by": "skyjw@example",
    })
    assert d.allowed is True
    assert d.approved is True
    assert d.approved_by == "skyjw@example"
    assert d.risk_level == "medium"


def test_medium_save_as_blocked_without_token(paths):
    from agent import approval_policy as ap
    d = ap.evaluate({
        "id": "t1", "action": "excel.save_as",
        "file_path": str(paths["sample"]),
        "save_as": str(paths["target"]),
    })
    assert d.allowed is False
    assert d.error == "approval_required"


def test_medium_save_as_requires_save_as_field(paths):
    from agent import approval_policy as ap
    d = ap.evaluate({
        "id": "t1", "action": "excel.save_as",
        "file_path": str(paths["sample"]),
        "approval_token": "tok",
    })
    assert d.allowed is False
    assert d.error == "save_as_required"


def test_empty_approval_token_treated_as_missing(paths):
    from agent import approval_policy as ap
    d = ap.evaluate({
        "id": "t1", "action": "excel.write_cell",
        "file_path": str(paths["sample"]),
        "save_as": str(paths["target"]),
        "cell_ref": "B2", "value": "X",
        "approval_token": "   ",  # 공백만
    })
    assert d.allowed is False
    assert d.error == "approval_required"


# ──────────────────────────────────────────────────────────────────
# 경로 정책
# ──────────────────────────────────────────────────────────────────
def test_file_path_outside_work_dir_blocked(paths, tmp_path):
    from agent import approval_policy as ap
    outside = tmp_path / "elsewhere.xlsx"
    outside.write_bytes(b"x")
    d = ap.evaluate({
        "id": "t1", "action": "excel.read_cell",
        "file_path": str(outside),
    })
    assert d.allowed is False
    assert d.error == "file_not_allowed"


def test_file_path_missing_file(paths):
    from agent import approval_policy as ap
    ghost = paths["work"] / "ghost.xlsx"
    d = ap.evaluate({
        "id": "t1", "action": "excel.read_cell",
        "file_path": str(ghost),
    })
    assert d.allowed is False
    assert d.error == "file_not_found"


def test_relative_file_path_blocked(paths):
    from agent import approval_policy as ap
    d = ap.evaluate({
        "id": "t1", "action": "excel.read_cell",
        "file_path": "sample.xlsx",
    })
    assert d.allowed is False
    assert d.error == "file_not_allowed"


def test_missing_file_path_blocked(paths):
    from agent import approval_policy as ap
    d = ap.evaluate({"id": "t1", "action": "excel.read_cell"})
    assert d.allowed is False
    assert d.error == "file_path_required"


def test_save_as_outside_output_dir_blocked(paths, tmp_path):
    from agent import approval_policy as ap
    # 출력을 AGENT_OUTPUT_DIR 밖으로
    elsewhere = tmp_path / "not_output.xlsx"
    d = ap.evaluate({
        "id": "t1", "action": "excel.run_poc",
        "file_path": str(paths["sample"]),
        "save_as": str(elsewhere),
    })
    assert d.allowed is False
    assert d.error == "output_path_not_allowed"


def test_save_as_equal_to_source_blocked(paths):
    """save_as 가 원본과 같으면 overwrite 이므로 거부."""
    from agent import approval_policy as ap
    d = ap.evaluate({
        "id": "t1", "action": "excel.run_poc",
        "file_path": str(paths["sample"]),
        "save_as": str(paths["sample"]),  # 동일 경로
    })
    assert d.allowed is False
    # file_policy 의 동일 경로 가드 → output_path_not_allowed
    assert d.error == "output_path_not_allowed"


def test_save_as_existing_file_blocked(paths):
    from agent import approval_policy as ap
    existing = paths["out"] / "already.xlsx"
    existing.write_bytes(b"old")
    d = ap.evaluate({
        "id": "t1", "action": "excel.run_poc",
        "file_path": str(paths["sample"]),
        "save_as": str(existing),
    })
    assert d.allowed is False
    assert d.error == "output_file_exists"


def test_read_action_with_save_as_still_validates(paths, tmp_path):
    """read 작업에 save_as 가 주어져도 허용 경로를 체크한다."""
    from agent import approval_policy as ap
    bad_save = tmp_path / "x.xlsx"
    d = ap.evaluate({
        "id": "t1", "action": "excel.read_cell",
        "file_path": str(paths["sample"]),
        "save_as": str(bad_save),
    })
    assert d.allowed is False
    assert d.error == "output_path_not_allowed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
