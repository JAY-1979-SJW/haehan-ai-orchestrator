"""Local Agent On-Demand Controller 테스트.

실제 브라우저 실행, 외부 사이트 접속, 실제 process kill 없음.
파일/구조/정책/gate 검증 중심.
"""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime, timedelta

import pytest

# 온디맨드 컨트롤러 3개(T4 C11 에서 scripts/local_agent/ → local_agent/) — 금지 패턴 검사 대상은 그대로다
_CONTROLLER_FILES = [pathlib.Path("core/agent_runtime/connection") / name for name in ("controller.py", "process_guard.py", "status_store.py")]

# ── fixture: 임시 data/local_agent 디렉터리 ────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """각 테스트마다 독립적인 data/local_agent 디렉터리 사용."""
    agent_dir = tmp_path / "data" / "local_agent"
    agent_dir.mkdir(parents=True)
    import core.agent_runtime.connection.process_guard as pg
    import core.agent_runtime.connection.status_store as ss

    monkeypatch.setattr(ss, "_STATUS_DIR", agent_dir)
    monkeypatch.setattr(ss, "_STATUS_FILE", agent_dir / "status.json")
    monkeypatch.setattr(ss, "_LOCK_FILE", agent_dir / "agent.lock")
    monkeypatch.setattr(pg, "_LOCK_FILE", agent_dir / "agent.lock")
    monkeypatch.setattr(pg, "_STATUS_FILE", agent_dir / "status.json")
    yield agent_dir


# ── 1. start creates status/lock ────────────────────────────────────────


def test_start_creates_lock_and_status():
    from core.agent_runtime.connection.controller import get_local_agent_status, start_local_agent
    from core.agent_runtime.connection.status_store import lock_exists

    result = start_local_agent(
        task_id="t001",
        domain="gabia",
        approved_scope=["dns_read"],
        approval={"decision": "LOCAL_AGENT_REQUIRED", "blocked": False},
    )
    assert result["ok"], f"start 실패: {result}"
    assert lock_exists()
    status = get_local_agent_status()
    assert status["running"]
    assert status["task_id"] == "t001"


# ── 2. duplicate start blocked ──────────────────────────────────────────


def test_duplicate_start_blocked():
    from core.agent_runtime.connection.controller import start_local_agent

    r1 = start_local_agent(
        "t001", "gabia", ["dns_read"], approval={"decision": "LOCAL_AGENT_REQUIRED", "blocked": False}
    )
    assert r1["ok"]
    r2 = start_local_agent(
        "t002", "gabia", ["dns_read"], approval={"decision": "LOCAL_AGENT_REQUIRED", "blocked": False}
    )
    assert not r2["ok"]
    assert "이미 실행 중" in r2["error"]


# ── 3. status does not expose secret/session/cookie/token ──────────────


def test_status_no_secret():
    from core.agent_runtime.connection.controller import get_local_agent_status, start_local_agent

    start_local_agent("t001", "gabia", ["dns_read"], approval={"decision": "LOCAL_AGENT_REQUIRED", "blocked": False})
    status = get_local_agent_status()
    status_str = json.dumps(status).lower()
    for forbidden in ("password", "session", "cookie", "access_token", "refresh_token"):
        assert forbidden not in status_str, f"status에 '{forbidden}' 포함 금지"


# ── 4. stop releases lock ───────────────────────────────────────────────


def test_stop_releases_lock():
    from core.agent_runtime.connection.controller import start_local_agent, stop_local_agent
    from core.agent_runtime.connection.status_store import lock_exists

    start_local_agent("t001", "gabia", ["dns_read"], approval={"decision": "LOCAL_AGENT_REQUIRED", "blocked": False})
    assert lock_exists()
    result = stop_local_agent(reason="completed")
    assert result["ok"]
    assert not lock_exists()


# ── 5. cleanup default dry_run ──────────────────────────────────────────


def test_cleanup_default_dry_run():
    from core.agent_runtime.connection.controller import cleanup_stale

    result = cleanup_stale()
    assert result["dry_run"] is True
    assert result["cleaned"] == []


def test_cleanup_stale_detects_orphan_lock(_isolated_data_dir):
    from core.agent_runtime.connection.controller import cleanup_stale
    from core.agent_runtime.connection.status_store import _LOCK_FILE, write_status

    # lock 파일만 있고 running=False인 stale 상태
    _LOCK_FILE.write_text("orphan_task", encoding="utf-8")
    write_status(running=False)
    result = cleanup_stale(dry_run=True)
    assert result["dry_run"] is True
    assert len(result["candidates"]) > 0


# ── 6. blocked action cannot start ────────────────────────────────────


def test_blocked_action_cannot_start():
    from core.agent_runtime.connection.controller import start_local_agent

    result = start_local_agent(
        "t001",
        "g2b",
        ["submit_bid"],
        approval={"decision": "BLOCKED", "blocked": True, "reason": "투찰 자동화 금지"},
    )
    assert not result["ok"]
    assert "BLOCKED" in result["error"]


# ── 7. approved local-agent action can start ──────────────────────────


def test_approved_local_agent_action_can_start():
    from core.agent_runtime.connection.controller import start_local_agent

    result = start_local_agent(
        "t001",
        "gabia",
        ["dns_zone_read"],
        approval={"decision": "LOCAL_AGENT_REQUIRED", "blocked": False},
    )
    assert result["ok"]
    assert result["task_id"] == "t001"


# ── 8. expired approval causes denied ────────────────────────────────


def test_expired_approval_denied():
    from core.agent_runtime.connection.controller import start_local_agent

    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    result = start_local_agent(
        "t001",
        "gabia",
        ["dns_read"],
        approval={
            "decision": "LOCAL_AGENT_REQUIRED",
            "blocked": False,
            "expires_at": past,
        },
    )
    assert not result["ok"]
    assert "만료" in result["error"]


# ── 9. idle timeout policy exists ────────────────────────────────────


def test_idle_timeout_policy_in_status():
    from core.agent_runtime.connection.controller import get_local_agent_status, start_local_agent

    start_local_agent(
        "t001",
        "gabia",
        ["dns_read"],
        approval={"decision": "LOCAL_AGENT_REQUIRED", "blocked": False},
        idle_timeout_s=600,
    )
    status = get_local_agent_status()
    assert "idle_timeout_s" in status
    assert status["idle_timeout_s"] == 600


def test_idle_timeout_constant_exists():
    from core.agent_runtime.connection.process_guard import DEFAULT_IDLE_TIMEOUT_S

    assert DEFAULT_IDLE_TIMEOUT_S > 0


# ── 10. no Windows service/autostart code ────────────────────────────


def test_no_windows_service_code():
    forbidden = [
        "win32serviceutil",
        "servicemanager",
        "RegisterService",
        "CreateService",
        "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
    ]
    for py in _CONTROLLER_FILES:
        src = py.read_text(encoding="utf-8", errors="ignore")
        for pat in forbidden:
            assert pat not in src, f"{py.name}에 Windows service 코드 금지: '{pat}'"


# ── 11. no infinite daemon loop pattern ──────────────────────────────


def test_no_infinite_daemon_loop():
    controller_src = pathlib.Path("core/agent_runtime/connection/controller.py").read_text(encoding="utf-8")
    # while True 무한 루프가 없어야 함
    assert "while True:" not in controller_src
    assert "while True :" not in controller_src


# ── 12. data/sessions access absent ──────────────────────────────────


def test_no_sessions_access():
    """data/sessions 실제 접근 코드(open/pathlib/read/parse) 금지.
    주석/docstring 언급은 허용.
    """
    access_patterns = [
        "data/sessions",
    ]
    for py in _CONTROLLER_FILES:
        src = py.read_text(encoding="utf-8", errors="ignore")
        # docstring/주석이 아닌 실제 코드 줄에서만 검사
        code_lines = [
            ln
            for ln in src.splitlines()
            if not ln.strip().startswith("#")
            and not ln.strip().startswith('"""')
            and not ln.strip().startswith("'''")
            and not ln.strip().startswith("*")
        ]
        code_body = "\n".join(code_lines)  # noqa: F841
        for pat in access_patterns:
            # pathlib.Path("data/sessions") 또는 open("data/sessions") 형태만 차단
            code_hits = [ln for ln in code_lines if pat in ln and ("Path(" in ln or "open(" in ln or "read_text" in ln)]
            assert code_lines, "code_lines 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
            assert not code_hits, f"{py.name}에 data/sessions 실제 접근 코드 금지: {code_hits}"


# ── 13. server browser guard remains enforced ────────────────────────


def test_server_browser_guard_in_policy_doc():
    policy_path = pathlib.Path("docs/architecture/local_agent_on_demand_controller.md")
    assert policy_path.exists(), "정책 문서 없음"
    src = policy_path.read_text(encoding="utf-8")
    assert "서버" in src and "금지" in src, "서버 사이드 브라우저 금지 정책 명시 필요"


# ── 14. evidence/report policy referenced ────────────────────────────


def test_evidence_policy_in_policy_doc():
    policy_path = pathlib.Path("docs/architecture/local_agent_on_demand_controller.md")
    src = policy_path.read_text(encoding="utf-8")
    assert "evidence" in src.lower() or "data/local_agent" in src, "evidence 저장 정책 명시 필요"


# ── 추가: user_direct_required 차단 ──────────────────────────────────


def test_user_direct_required_blocked():
    from core.agent_runtime.connection.controller import start_local_agent

    result = start_local_agent(
        "t001",
        "g2b",
        ["certificate_auth"],
        approval={"decision": "USER_DIRECT_REQUIRED", "blocked": False},
    )
    assert not result["ok"]
    assert "USER_DIRECT_REQUIRED" in result["error"]


# ── 추가: stop reason 기록 ────────────────────────────────────────────


def test_stop_records_reason():
    from core.agent_runtime.connection.controller import start_local_agent, stop_local_agent

    start_local_agent("t001", "gabia", ["dns_read"], approval={"decision": "LOCAL_AGENT_REQUIRED", "blocked": False})
    result = stop_local_agent(reason="failed")
    assert result["reason"] == "failed"
    assert result["ok"]
