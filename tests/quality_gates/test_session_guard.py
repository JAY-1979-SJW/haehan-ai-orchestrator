"""session_guard.py / session_handoff.py 테스트. docs/specs/2026-09-24_session_handoff_guard.md"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hooks"))

import session_guard as sg  # noqa: E402
import session_handoff as sh  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """ROOT 를 tmp_path 로 치환해 실제 저장소를 건드리지 않는다."""
    monkeypatch.setattr(sh, "ROOT", tmp_path)
    monkeypatch.setattr(sg.sh, "ROOT", tmp_path)
    cfg = {
        "warn_mb": 0.001,
        "block_mb": 0.002,
        "bypass_prefix": "!계속",
        "handoff_path": "data/impact/HANDOFF.md",
        "worklog_path": "data/ops/worklog.jsonl",
        "phase_done_flag": "data/impact/PHASE_DONE",
        "cleanup": {},
    }
    (tmp_path / "configs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "configs" / "session_guard.json").write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(sh, "load_config", lambda: cfg)
    monkeypatch.setattr(sg.sh, "load_config", lambda: cfg)
    yield tmp_path


def _make_transcript(tmp_path: Path, size_bytes: int) -> str:
    p = tmp_path / "transcript.jsonl"
    p.write_bytes(b"x" * size_bytes)
    return str(p)


def test_below_warn_silent(tmp_path, monkeypatch, capsys):
    transcript = _make_transcript(tmp_path, 100)  # well below warn threshold in bytes
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": "hello", "transcript_path": transcript}
    rc = sg._handle_user_prompt_submit(payload)
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == ""


def test_warn_prints_note(tmp_path, monkeypatch, capsys):
    # warn_mb=0.001 -> ~1KB triggers warn but block_mb=0.002 (~2KB) not yet
    transcript = _make_transcript(tmp_path, 1500)
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": "hello", "transcript_path": transcript}
    rc = sg._handle_user_prompt_submit(payload)
    assert rc == 0
    out = capsys.readouterr().out
    assert "세션 경고" in out


def test_block_writes_handoff_and_exits_2(tmp_path, monkeypatch, capsys):
    transcript = _make_transcript(tmp_path, 3000)  # exceeds block_mb
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": "hello", "transcript_path": transcript}
    rc = sg._handle_user_prompt_submit(payload)
    assert rc == 2
    err = capsys.readouterr().err
    assert "세션 한도" in err
    assert "인계 이어서" in err
    handoff = tmp_path / "data" / "impact" / "HANDOFF.md"
    assert handoff.exists()
    text = handoff.read_text(encoding="utf-8")
    for sec in sh.REQUIRED_SECTIONS:
        assert sec in text


def test_block_when_verify_fails_does_not_block(tmp_path, monkeypatch, capsys):
    transcript = _make_transcript(tmp_path, 3000)
    monkeypatch.setattr(sh, "write", lambda: False)
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": "hello", "transcript_path": transcript}
    rc = sg._handle_user_prompt_submit(payload)
    assert rc == 0
    out = capsys.readouterr().out
    assert "저장 실패" in out


def test_bypass_prefix_passes_and_logs(tmp_path, monkeypatch, capsys):
    transcript = _make_transcript(tmp_path, 3000)
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": "!계속 진행해줘", "transcript_path": transcript}
    rc = sg._handle_user_prompt_submit(payload)
    assert rc == 0
    worklog = tmp_path / "data" / "ops" / "worklog.jsonl"
    assert worklog.exists()
    rows = [json.loads(x) for x in worklog.read_text(encoding="utf-8").splitlines()]
    assert any(r["kind"] == "bypass" for r in rows)


def test_phase_done_flag_blocks_even_when_small(tmp_path, monkeypatch, capsys):
    transcript = _make_transcript(tmp_path, 10)
    flag = tmp_path / "data" / "impact" / "PHASE_DONE"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("done", encoding="utf-8")
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": "hello", "transcript_path": transcript}
    rc = sg._handle_user_prompt_submit(payload)
    assert rc == 2


def test_session_start_prints_summary_and_removes_flag(tmp_path, monkeypatch, capsys):
    handoff = tmp_path / "data" / "impact" / "HANDOFF.md"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text("# 인계\n\n## 다음 할 일\n- 테스트", encoding="utf-8")
    flag = tmp_path / "data" / "impact" / "PHASE_DONE"
    flag.write_text("done", encoding="utf-8")
    monkeypatch.setattr(sh, "cleanup", lambda apply=False: {"deleted": [], "reported": [], "errors": []})
    rc = sg._handle_session_start({"hook_event_name": "SessionStart", "source": "startup"})
    assert rc == 0
    out = capsys.readouterr().out
    assert "다음 할 일" in out
    assert not flag.exists()


def test_session_start_handles_clear_source(tmp_path, monkeypatch, capsys):
    handoff = tmp_path / "data" / "impact" / "HANDOFF.md"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text("# 인계\n\n## 다음 할 일\n- 테스트", encoding="utf-8")
    monkeypatch.setattr(sh, "cleanup", lambda apply=False: {"deleted": [], "reported": [], "errors": []})
    rc = sg._handle_session_start({"hook_event_name": "SessionStart", "source": "clear"})
    assert rc == 0
    out = capsys.readouterr().out
    assert "다음 할 일" in out


def test_session_start_unknown_source_noop(tmp_path, monkeypatch, capsys):
    handoff = tmp_path / "data" / "impact" / "HANDOFF.md"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text("# 인계\n\n## 다음 할 일\n- 테스트", encoding="utf-8")
    rc = sg._handle_session_start({"hook_event_name": "SessionStart", "source": "compact"})
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == ""


def test_stop_and_precompact_never_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "write", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert sg._handle_quiet_write() == 0


def test_main_fail_open_on_bad_stdin(monkeypatch, capsys):
    class FakeStdin:
        def read(self):
            return "not json{{"

    monkeypatch.setattr(sg.sys, "stdin", FakeStdin())
    rc = sg.main()
    assert rc == 0


def test_post_commit_logging_appends_line(tmp_path, monkeypatch):
    sh.log_event("commit", hash="abc123", subject="test commit", branch="master", files_changed=3)
    worklog = tmp_path / "data" / "ops" / "worklog.jsonl"
    assert worklog.exists()
    rows = [json.loads(x) for x in worklog.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["kind"] == "commit"
    assert rows[-1]["hash"] == "abc123"


def test_cleanup_report_mode_deletes_nothing(tmp_path, monkeypatch):
    scratch_root = tmp_path / "scratch_base"
    old_dir = scratch_root / "old-session"
    old_dir.mkdir(parents=True)
    (old_dir / "f.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(sh, "_scratchpad_root", lambda: scratch_root)
    monkeypatch.setattr(sh, "_current_session_id", lambda: "current-session")
    report = sh.cleanup(apply=False)
    assert old_dir.exists()
    assert any(e["path"] == str(old_dir) for e in report["reported"])
    assert report["deleted"] == []


def test_cleanup_never_touches_protected_paths(tmp_path, monkeypatch):
    cfg = sh.load_config()
    cfg = dict(cfg)
    cfg["cleanup"] = {
        "scratchpad_report_only_days": 0,
        "protected_paths": ["scratch_base/old-session"],
    }
    monkeypatch.setattr(sh, "load_config", lambda: cfg)
    scratch_root = tmp_path / "scratch_base"
    old_dir = scratch_root / "old-session"
    old_dir.mkdir(parents=True)
    monkeypatch.setattr(sh, "_scratchpad_root", lambda: scratch_root)
    monkeypatch.setattr(sh, "_current_session_id", lambda: "current-session")
    import os

    old_time = __import__("time").time() - 999999
    os.utime(old_dir, (old_time, old_time))
    sh.cleanup(apply=True)
    assert old_dir.exists()


def test_is_protected_matches_glob_db_file(tmp_path, monkeypatch):
    protected = ["data/*.db", "data/cdp_profile*", ".env*"]
    p = tmp_path / "data" / "app.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    assert sh._is_protected(p, protected) is True


def test_is_protected_matches_cdp_profile_subpath(tmp_path):
    protected = ["data/*.db", "data/cdp_profile*", ".env*"]
    p = tmp_path / "data" / "cdp_profile" / "ai_chrome" / "Cookies"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    assert sh._is_protected(p, protected) is True


def test_is_protected_matches_env_variant(tmp_path):
    protected = ["data/*.db", "data/cdp_profile*", ".env*"]
    p = tmp_path / ".env.local"
    p.write_text("x", encoding="utf-8")
    assert sh._is_protected(p, protected) is True


def test_is_protected_rejects_unrelated_path(tmp_path):
    protected = ["data/*.db", "data/cdp_profile*", ".env*"]
    p = tmp_path / "data" / "reports" / "summary.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    assert sh._is_protected(p, protected) is False


def test_verify_fails_without_handoff(tmp_path):
    assert sh.verify() is False


def test_write_then_verify_ok(tmp_path):
    ok = sh.write()
    assert ok is True
    assert sh.verify() is True
