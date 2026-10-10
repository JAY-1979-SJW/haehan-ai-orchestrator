"""ai_orchestrator.site_work.work_record (L1) — 순수 규칙 시험. DB·환경변수·네트워크 접촉 없음."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ai_orchestrator.site_work import work_record as wr
from ai_orchestrator.site_work.work_record import JobStatus as J
from ai_orchestrator.site_work.work_record import ValidationError

_SRC = Path(wr.__file__)


def test_transition_table_exhaustive():
    allowed = {
        (J.DRAFT, J.PENDING_APPROVAL), (J.DRAFT, J.CANCELLED),
        (J.PENDING_APPROVAL, J.RUNNING), (J.PENDING_APPROVAL, J.CANCELLED), (J.PENDING_APPROVAL, J.EXPIRED),
        (J.RUNNING, J.SUCCEEDED), (J.RUNNING, J.FAILED), (J.RUNNING, J.PAUSED), (J.RUNNING, J.CANCELLED),
        (J.PAUSED, J.RESUMABLE), (J.PAUSED, J.CANCELLED),
        (J.RESUMABLE, J.RUNNING), (J.RESUMABLE, J.CANCELLED),
    }  # fmt: skip
    for a in J:
        for b in J:
            assert wr.can_transition_job(a, b) == ((a, b) in allowed), (a, b)


def test_terminal_states_and_sources():
    assert {J.SUCCEEDED, J.FAILED, J.CANCELLED, J.EXPIRED} == set(wr.JOB_TERMINAL)
    assert set(wr.job_sources_for(J.RUNNING)) == {J.PENDING_APPROVAL, J.RESUMABLE}
    assert wr.job_sources_for(J.DRAFT) == ()


def test_step_transitions():
    S = wr.StepStatus
    assert wr.can_transition_step(S.PENDING, S.RUNNING)
    assert wr.can_transition_step(S.FAILED, S.RUNNING)
    assert not wr.can_transition_step(S.SUCCEEDED, S.RUNNING)
    assert not wr.can_transition_step(S.SKIPPED, S.RUNNING)


def test_job_kinds():
    for k in ("site_map_explore", "task_run", "dev_task", "ops_check", "manual", "site.onboard:eum.cw.or.kr"):
        assert wr.validate_job_kind(k) == k
    for bad in ("nope", "site.onboard:", "site.onboard:Bad Host", "site.onboard:a/b", "site.onboard:http://x", ""):
        with pytest.raises(ValidationError):
            wr.validate_job_kind(bad)
    assert wr.onboard_host("site.onboard:a.com") == "a.com"
    assert wr.onboard_host("manual") is None


def test_step_kinds_include_dry_run():
    assert wr.validate_step_kind("dry_run") == "dry_run"
    with pytest.raises(ValidationError):
        wr.validate_step_kind("hack")


def test_params_whitelist():
    ok = wr.validate_params({"host": "a.com", "task_key": "t1", "columns": ["a", "b"], "row_count": 3})
    assert ok["row_count"] == 3
    for bad in (
        {"unknown": 1},
        {"password": "x"},
        {"my_token": "x"},
        {"note": "x" * 501},
        {"url": "https://a.com/p?id=1"},
        {"url": "https://u:p@a.com/p"},
        {"note": "see https://a.com/p?x=1"},
        {"note": "password=abc"},
        {"columns": [{"a": 1}]},
        {"note": {"nested": 1}},
        {"columns": ["x"] * 51},
    ):
        with pytest.raises(ValidationError):
            wr.validate_params(bad)
    assert wr.validate_params({"url": "https://a.com/path"}) == {"url": "https://a.com/path"}


def test_input_hash_stable():
    a = wr.compute_input_hash("manual", "a.com", {"b": 1, "a": 2})
    b = wr.compute_input_hash("manual", "a.com", {"a": 2, "b": 1})
    assert a == b and len(a) == 64
    assert a != wr.compute_input_hash("manual", "b.com", {"a": 2, "b": 1})


def test_artifact_rel_path():
    assert wr.validate_artifact_rel_path("data/work_records/a/b.png")
    drive_path = chr(67) + ":/x"  # 드라이브 문자 절대경로(리터럴 하드코딩 회피)
    for bad in ("", "/etc/x", drive_path, "a/../b", "a//b", "a" + chr(92) + "b", "./a", "a/."):
        with pytest.raises(ValidationError):
            wr.validate_artifact_rel_path(bad)


def test_misc_validators():
    assert wr.validate_sha256("a" * 64)
    for bad in ("A" * 64, "a" * 63, "g" * 64):
        with pytest.raises(ValidationError):
            wr.validate_sha256(bad)
    assert wr.validate_host("a.b-c.com") == "a.b-c.com"
    with pytest.raises(ValidationError):
        wr.validate_host("A.com")
    with pytest.raises(ValidationError):
        wr.validate_host("a.com:80")
    with pytest.raises(ValidationError):
        wr.validate_tags(["ok", "bad tag"])
    with pytest.raises(ValidationError):
        wr.validate_tags([str(i) for i in range(21)])


def test_scope_has_no_implicit_wide_access():
    s = wr.Scope.owner_only("alice")
    assert s.created_by == "alice" and s.tenant_id == "default"
    assert wr.Scope.tenant_wide().created_by is None


def test_protocols_present():
    for name in ("RecordJobStart", "RecordStep", "AttachArtifact", "FinishJob"):
        assert hasattr(wr, name)


def test_l1_is_pure_by_ast():
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.level * "." + (node.module or ""))
    forbidden = {"os", "sqlite3", "socket", "requests", "httpx", "subprocess", "pathlib", "shutil", "datetime", "time"}
    assert not (mods & forbidden), mods & forbidden
    assert not any(m.startswith(".") for m in mods)  # 다른 레이어 상대 import 없음
    assert not any(m.startswith("ai_orchestrator") for m in mods)
    text = _SRC.read_text(encoding="utf-8")
    assert "environ" not in text and "getenv" not in text and "sqlite" not in text.replace("sqlite 금지", "")


def test_params_verdict_robots_enum_ok():
    for v in ("proceed", "use_api", "blocked"):
        for r in ("ok", "missing", "unavailable"):
            assert wr.validate_params({"verdict": v, "robots_status": r}) == {"verdict": v, "robots_status": r}


def test_params_verdict_robots_enum_rejected():
    for bad in (
        {"verdict": "maybe"},
        {"verdict": ""},
        {"verdict": 1},
        {"verdict": None},
        {"verdict": ["proceed"]},
        {"verdict": "PROCEED"},
        {"robots_status": 1},
        {"robots_status": ""},
        {"robots_status": "maybe"},
        {"robots_status": True},
    ):
        with pytest.raises(ValidationError):
            wr.validate_params(bad)


def test_params_existing_keys_unchanged_after_enum_keys():
    assert len(wr.PARAM_ALLOWED_KEYS) == 21
    assert {"host", "url", "note", "max_pages", "reason"} <= wr.PARAM_ALLOWED_KEYS
    assert wr.validate_params({"note": "free text", "mode": "anything"}) == {"note": "free text", "mode": "anything"}
