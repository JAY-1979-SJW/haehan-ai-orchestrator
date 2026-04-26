"""LOCAL-FS-3 테스트 — runs_summarizer.py 검증."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from ai_orchestrator.local_files.runs_summarizer import (
    GROUPS,
    classify_status,
    extract_next_actions,
    find_latest_files,
    load_run_json,
    summarize_all_groups,
    summarize_group,
    write_runs_summary,
)


# ── 헬퍼 ─────────────────────────────────────────────────────────────────

def _write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ── find_latest_files ─────────────────────────────────────────────────────

def test_find_latest_empty(tmp_path):
    result = find_latest_files(tmp_path, "developer_console")
    assert result == []


def test_find_latest_single_file(tmp_path):
    p = tmp_path / "runs" / "developer_console" / "session_health_001.json"
    _write_json(p, {"status": "READY_LOGGED_IN"})
    result = find_latest_files(tmp_path, "developer_console")
    assert len(result) == 1
    assert result[0].name == "session_health_001.json"


def test_find_latest_sorted_by_mtime(tmp_path):
    base = tmp_path / "runs" / "developer_console"
    p1 = _write_json(base / "a.json", {"status": "PASS"})
    time.sleep(0.02)
    p2 = _write_json(base / "b.json", {"status": "PASS"})
    result = find_latest_files(tmp_path, "developer_console", max_files=2)
    assert result[0].name == "b.json"
    assert result[1].name == "a.json"


def test_find_latest_max_files(tmp_path):
    base = tmp_path / "runs" / "developer_console"
    for i in range(5):
        _write_json(base / f"f{i}.json", {})
        time.sleep(0.01)
    result = find_latest_files(tmp_path, "developer_console", max_files=2)
    assert len(result) == 2


def test_find_latest_skips_secrets(tmp_path):
    safe = tmp_path / "runs" / "developer_console" / "safe.json"
    _write_json(safe, {})
    secret = tmp_path / "secrets" / "developer_console" / "token.json"
    _write_json(secret, {})
    result = find_latest_files(tmp_path, "developer_console")
    names = [r.name for r in result]
    assert "safe.json" in names
    assert "token.json" not in names


def test_find_latest_skips_summary_self(tmp_path):
    base = tmp_path / "runs" / "local_files"
    _write_json(base / "recent_runs_summary_20260426_120000.json", {})
    _write_json(base / "local_file_search_20260426_120000.json", {})
    result = find_latest_files(tmp_path, "local_files")
    names = [r.name for r in result]
    assert not any("recent_runs_summary" in n for n in names)


# ── classify_status ───────────────────────────────────────────────────────

def test_classify_ready_logged_in():
    status, signals = classify_status({"status": "READY_LOGGED_IN"})
    assert status == "PASS"


def test_classify_needs_reauth_is_warn():
    status, signals = classify_status({"status": "NEEDS_REAUTH"})
    assert status == "WARN"
    assert any("NEEDS_REAUTH" in s for s in signals)


def test_classify_blocked_is_fail():
    status, signals = classify_status({"status": "BLOCKED"})
    assert status == "FAIL"


def test_classify_failed_is_fail():
    status, signals = classify_status({"status": "failed"})
    assert status == "FAIL"


def test_classify_unknown_is_warn():
    status, signals = classify_status({"status": "UNKNOWN"})
    assert status == "WARN"


def test_classify_warnings_list_is_warn():
    status, signals = classify_status({"warnings": ["input_video_missing"]})
    assert status == "WARN"
    assert any("warnings" in s for s in signals)


def test_classify_ffmpeg_false_is_warn():
    status, signals = classify_status({"ffmpeg_available": False})
    assert status == "WARN"


def test_classify_dry_run_is_warn():
    status, signals = classify_status({"mode": "dry_run"})
    assert status == "WARN"


def test_classify_security_violation_is_fail():
    status, signals = classify_status({"security": {"password_stored": True}})
    assert status == "FAIL"
    assert any("security.password_stored=true" in s for s in signals)


def test_classify_empty_data_is_pass():
    status, signals = classify_status({})
    assert status == "PASS"
    assert signals == []


def test_classify_console_needs_reauth_is_warn():
    data = {
        "consoles": [
            {"console": "kakao", "display": "카카오", "status": "NEEDS_REAUTH"},
            {"console": "naver", "display": "네이버", "status": "READY_LOGGED_IN"},
        ],
        "summary": {"READY_LOGGED_IN": 1, "NEEDS_REAUTH": 1},
    }
    status, signals = classify_status(data)
    assert status == "WARN"


# ── extract_next_actions ──────────────────────────────────────────────────

def test_extract_next_actions_list():
    data = {"next_actions": ["작업A 진행", "작업B 확인"]}
    actions = extract_next_actions(data)
    assert "작업A 진행" in actions
    assert "작업B 확인" in actions


def test_extract_next_actions_empty():
    actions = extract_next_actions({})
    assert actions == []


def test_extract_next_actions_console_reauth():
    data = {
        "consoles": [
            {"console": "kakao", "display": "카카오 개발자", "status": "NEEDS_REAUTH"},
        ]
    }
    actions = extract_next_actions(data)
    assert any("카카오 개발자" in a for a in actions)


def test_extract_next_actions_redacted():
    secret = "x" * 40
    data = {"next_actions": [f"api_key={secret} 확인"]}
    actions = extract_next_actions(data)
    assert secret not in " ".join(actions)


# ── summarize_group ───────────────────────────────────────────────────────

def test_summarize_group_no_files(tmp_path):
    result = summarize_group(tmp_path, "developer_console")
    assert result["status"] == "PASS"
    assert result["file_count"] == 0
    assert result["latest_file"] is None


def test_summarize_group_with_file(tmp_path):
    p = tmp_path / "runs" / "developer_console" / "session_health.json"
    _write_json(p, {"status": "READY_LOGGED_IN", "consoles": []})
    result = summarize_group(tmp_path, "developer_console")
    assert result["status"] == "PASS"
    assert result["file_count"] == 1
    assert "developer_console" in result["latest_file"]


def test_summarize_group_warn_propagates(tmp_path):
    p = tmp_path / "runs" / "developer_console" / "session.json"
    _write_json(p, {"status": "NEEDS_REAUTH"})
    result = summarize_group(tmp_path, "developer_console")
    assert result["status"] == "WARN"
    assert result["action_required"] is True


# ── summarize_all_groups ──────────────────────────────────────────────────

def test_summarize_all_overall_fail_wins(tmp_path):
    _write_json(tmp_path / "runs" / "developer_console" / "s.json", {"status": "BLOCKED"})
    _write_json(tmp_path / "runs" / "naver" / "n.json", {"status": "READY_LOGGED_IN"})
    result = summarize_all_groups(tmp_path, groups=["developer_console", "naver"])
    assert result["overall_status"] == "FAIL"


def test_summarize_all_overall_warn(tmp_path):
    _write_json(tmp_path / "runs" / "developer_console" / "s.json", {"status": "NEEDS_REAUTH"})
    _write_json(tmp_path / "runs" / "naver" / "n.json", {"status": "READY_LOGGED_IN"})
    result = summarize_all_groups(tmp_path, groups=["developer_console", "naver"])
    assert result["overall_status"] == "WARN"


def test_summarize_all_next_actions_merged(tmp_path):
    _write_json(tmp_path / "runs" / "developer_console" / "s.json", {
        "status": "NEEDS_REAUTH",
        "next_actions": ["카카오 재인증"]
    })
    result = summarize_all_groups(tmp_path, groups=["developer_console"])
    assert any("카카오 재인증" in a for a in result["all_next_actions"])


def test_summarize_all_group_filter(tmp_path):
    _write_json(tmp_path / "runs" / "naver" / "n.json", {"status": "READY_LOGGED_IN"})
    result = summarize_all_groups(tmp_path, groups=["naver"])
    assert "naver" in result["groups"]
    assert "developer_console" not in result["groups"]


# ── write_runs_summary ────────────────────────────────────────────────────

def test_write_creates_json_and_md(tmp_path):
    summary = {
        "summarized_at": "20260426_120000",
        "root": str(tmp_path),
        "overall_status": "PASS",
        "groups": {
            "naver": {
                "status": "PASS",
                "latest_file": "runs/naver/n.json",
                "latest_ts": "20260426_120000",
                "signals": [],
                "next_actions": [],
                "action_required": False,
                "file_count": 1,
            }
        },
        "all_next_actions": [],
    }
    out = tmp_path / "out"
    paths = write_runs_summary(summary, out)
    assert Path(paths["json"]).exists()
    assert Path(paths["md"]).exists()
    data = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert data["overall_status"] == "PASS"


def test_write_no_secret_in_output(tmp_path):
    # s*40 은 40자 base64류 패턴 → write_runs_summary가 redact_sensitive_text 적용 후 저장
    secret = "s" * 40
    summary = {
        "summarized_at": "20260426_120000",
        "root": str(tmp_path),
        "overall_status": "PASS",
        "groups": {},
        "all_next_actions": [f"note={secret}"],
    }
    paths = write_runs_summary(summary, tmp_path / "out")
    content = Path(paths["json"]).read_text(encoding="utf-8")
    # write_runs_summary는 all_next_actions에 redact_sensitive_text를 적용한다
    assert secret not in content
