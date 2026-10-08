"""
dashboard 라우트 테스트 (5단계)
- /dashboard 200 응답
- /dashboard/tasks/<task_id> 200 응답
- approve/reject 권한 검사
- viewer 승인 거절
- operator medium 승인 가능
- admin high 승인 가능 but execution still blocked
"""

import base64
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".."))

import orchestrator_v1.monitoring.dashboard as dash_mod
import orchestrator_v1.tasks.approval_manager as approval_manager
from orchestrator_v1.monitoring.dashboard import create_app

# ── 테스트용 Basic Auth 래퍼 ─────────────────────────────────────────────────
_TEST_USER = "test"
_TEST_PASS = "test"
_AUTH_HDR = {"Authorization": "Basic " + base64.b64encode(f"{_TEST_USER}:{_TEST_PASS}".encode()).decode()}


class _AuthClient:
    """모든 요청에 Basic Auth 헤더를 자동으로 추가하는 테스트 클라이언트 래퍼."""

    def __init__(self, client):
        self._c = client

    def get(self, url, **kw):
        kw["headers"] = {**_AUTH_HDR, **kw.get("headers", {})}
        return self._c.get(url, **kw)

    def post(self, url, **kw):
        kw["headers"] = {**_AUTH_HDR, **kw.get("headers", {})}
        return self._c.post(url, **kw)

    # 인증 없이 직접 요청이 필요한 테스트에서 사용
    def get_no_auth(self, url, **kw):
        return self._c.get(url, **kw)

    def post_no_auth(self, url, **kw):
        return self._c.post(url, **kw)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import orchestrator_v1.monitoring.log_analyzer as log_analyzer

    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", str(tmp_path / "history.jsonl"))
    monkeypatch.setattr(log_analyzer, "_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setattr(dash_mod, "_DECISIONS_PATH", str(tmp_path / "decisions.jsonl"))

    # Redirect audit_logger writes to tmp dir
    import orchestrator_v1.core.audit_logger as al

    tmp_logs = str(tmp_path / "logs")
    Path(tmp_logs).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(al, "_LOGS_DIR", tmp_logs)
    monkeypatch.setattr(al, "_AUDIT_PATH", str(Path(tmp_logs) / "audit.jsonl"))
    # Reset audit logger so it picks up the new path
    al._logger = None

    # Basic Auth 환경변수 설정
    monkeypatch.setenv("ORCH_DASHBOARD_USER", _TEST_USER)
    monkeypatch.setenv("ORCH_DASHBOARD_PASSWORD", _TEST_PASS)

    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as c:
        yield _AuthClient(c)

    approval_manager._store.clear()
    al._logger = None


def _add_token(task_id: str, risk_level: str, approved: bool = False, rejected: bool = False, age: float = 0.0) -> str:
    token_id = f"test-token-{task_id}"
    approval_manager._store[token_id] = {
        "task_id": task_id,
        "risk_level": risk_level,
        "issued_at": time.time() - age,
        "approved": approved,
        "rejected": rejected,
    }
    return token_id


# ── Route: GET /dashboard ─────────────────────────────────────────────────────


def test_dashboard_200(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"dashboard" in resp.data.lower() or b"orchestrator" in resp.data.lower()


def test_dashboard_shows_summary_cards(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"\xec\xa0\x84\xec\xb2\xb4 \xec\x9e\x91\xec\x97\x85" in resp.data or b"total" in resp.data.lower()


def test_dashboard_with_pending_token(client):
    _add_token("task-pend-001", "medium")
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"task-pend-001" in resp.data


# ── Route: GET /dashboard/tasks/<task_id> ────────────────────────────────────


def test_task_detail_200_not_found(client):
    resp = client.get("/dashboard/tasks/nonexistent-task-xyz")
    assert resp.status_code == 200


def test_task_detail_200_with_token(client):
    _add_token("task-detail-001", "medium")
    resp = client.get("/dashboard/tasks/task-detail-001")
    assert resp.status_code == 200
    assert b"task-detail-001" in resp.data


# ── Route: POST /dashboard/approve ───────────────────────────────────────────


def test_approve_missing_fields(client):
    resp = client.post("/dashboard/approve", json={})
    assert resp.status_code == 400
    assert "required" in resp.get_json()["error"]


def test_approve_unknown_user(client):
    token_id = _add_token("task-u001", "low")
    resp = client.post("/dashboard/approve", json={"token_id": token_id, "task_id": "task-u001", "user_id": "nobody"})
    assert resp.status_code == 403
    assert "unknown user_id" in resp.get_json()["error"]


def test_approve_viewer_rejected(client):
    token_id = _add_token("task-v001", "low")
    resp = client.post("/dashboard/approve", json={"token_id": token_id, "task_id": "task-v001", "user_id": "viewer-1"})
    assert resp.status_code == 403
    assert "viewer" in resp.get_json()["error"]


def test_approve_operator_low_success(client):
    token_id = _add_token("task-op-low", "low")
    resp = client.post(
        "/dashboard/approve", json={"token_id": token_id, "task_id": "task-op-low", "user_id": "operator-1"}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["decision"] == "APPROVED"


def test_approve_operator_medium_success(client):
    token_id = _add_token("task-op-med", "medium")
    resp = client.post(
        "/dashboard/approve", json={"token_id": token_id, "task_id": "task-op-med", "user_id": "operator-1"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["decision"] == "APPROVED"


def test_approve_operator_high_rejected(client):
    token_id = _add_token("task-op-high", "high")
    resp = client.post(
        "/dashboard/approve", json={"token_id": token_id, "task_id": "task-op-high", "user_id": "operator-1"}
    )
    assert resp.status_code == 403
    assert "operator" in resp.get_json()["error"] or "high" in resp.get_json()["error"]


def test_approve_admin_high_success(client):
    token_id = _add_token("task-admin-high", "high")
    resp = client.post(
        "/dashboard/approve", json={"token_id": token_id, "task_id": "task-admin-high", "user_id": "admin-1"}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["decision"] == "APPROVED"
    assert "execution remains blocked" in data["note"]  # high 승인해도 실행 차단 유지


def test_approve_critical_always_blocked(client):
    token_id = _add_token("task-crit", "critical")
    resp = client.post("/dashboard/approve", json={"token_id": token_id, "task_id": "task-crit", "user_id": "admin-1"})
    assert resp.status_code == 403
    assert "critical" in resp.get_json()["error"]


def test_approve_expired_token(client):
    token_id = _add_token("task-exp", "low", age=700.0)  # > 600s TTL
    resp = client.post("/dashboard/approve", json={"token_id": token_id, "task_id": "task-exp", "user_id": "admin-1"})
    assert resp.status_code == 410
    assert "expired" in resp.get_json()["error"]


def test_approve_already_approved(client):
    token_id = _add_token("task-dup", "low", approved=True)
    resp = client.post("/dashboard/approve", json={"token_id": token_id, "task_id": "task-dup", "user_id": "admin-1"})
    assert resp.status_code == 409


def test_approve_token_not_found(client):
    resp = client.post(
        "/dashboard/approve", json={"token_id": "no-such-token", "task_id": "task-x", "user_id": "admin-1"}
    )
    assert resp.status_code == 404


# ── Route: POST /dashboard/reject ────────────────────────────────────────────


def test_reject_normal(client):
    token_id = _add_token("task-rej-001", "medium")
    resp = client.post(
        "/dashboard/reject",
        json={"token_id": token_id, "task_id": "task-rej-001", "user_id": "operator-1", "reason": "테스트 거절"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["decision"] == "REJECTED"


def test_reject_viewer_blocked(client):
    token_id = _add_token("task-rej-v", "low")
    resp = client.post("/dashboard/reject", json={"token_id": token_id, "task_id": "task-rej-v", "user_id": "viewer-1"})
    assert resp.status_code == 403


def test_reject_records_decision(client, tmp_path):
    import json as _json

    decisions_path = str(tmp_path / "decisions.jsonl")
    token_id = _add_token("task-rec-001", "low")
    client.post(
        "/dashboard/reject",
        json={"token_id": token_id, "task_id": "task-rec-001", "user_id": "operator-1", "reason": "테스트"},
    )
    assert Path(decisions_path).exists()
    with Path(decisions_path).open(encoding="utf-8") as f:
        lines = [_json.loads(l) for l in f if l.strip()]  # noqa: E741
    assert any(l.get("decision") == "REJECTED" for l in lines)  # noqa: E741


# ── Execution still blocked after high approval ───────────────────────────────


def test_high_approval_does_not_enable_execution(client):
    """admin이 high를 승인해도 whitelist_executor는 여전히 BLOCKED 반환."""
    from orchestrator_v1.core.models import ExecutionPlan, RiskAssessment, TaskRequest
    from orchestrator_v1.tasks.policy_engine import load_policy
    from orchestrator_v1.tasks.whitelist_executor import can_execute

    token_id = _add_token("task-high-exec", "high")
    client.post("/dashboard/approve", json={"token_id": token_id, "task_id": "task-high-exec", "user_id": "admin-1"})

    # approval_manager.is_token_valid will return True for high
    # but whitelist_executor checks risk level directly → still blocked
    task = TaskRequest(
        task_id="task-high-exec",
        source="server",
        action_type="restart_service",
        target="nginx",
        description="test",
    )
    risk = RiskAssessment(risk_level="high", requires_approval=True)
    plan = ExecutionPlan(
        task_id="task-high-exec",
        allowed=False,
        requires_approval=True,
        blocked_reasons=["high actions cannot be auto-executed"],
    )
    policy = load_policy()
    ok, _reasons = can_execute(task, risk, plan, policy, approval_valid=True)
    assert not ok, "high risk must remain blocked regardless of approval"


# ── Basic Auth 인증 테스트 ────────────────────────────────────────────────────


def test_dashboard_no_auth_returns_401(tmp_path, monkeypatch):
    """인증 없이 접근하면 401 반환."""
    import orchestrator_v1.core.audit_logger as al
    import orchestrator_v1.monitoring.log_analyzer as log_analyzer

    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", str(tmp_path / "history.jsonl"))
    monkeypatch.setattr(log_analyzer, "_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("ORCH_DASHBOARD_USER", "admin")
    monkeypatch.setenv("ORCH_DASHBOARD_PASSWORD", "secret")

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        resp = c.get("/dashboard")
    assert resp.status_code == 401
    assert b"WWW-Authenticate" in resp.headers.get("WWW-Authenticate", "").encode() or resp.status_code == 401

    al._logger = None


def test_dashboard_wrong_password_returns_401(tmp_path, monkeypatch):
    """잘못된 비밀번호로 접근하면 401 반환."""
    import orchestrator_v1.core.audit_logger as al
    import orchestrator_v1.monitoring.log_analyzer as log_analyzer

    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", str(tmp_path / "history.jsonl"))
    monkeypatch.setattr(log_analyzer, "_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("ORCH_DASHBOARD_USER", "admin")
    monkeypatch.setenv("ORCH_DASHBOARD_PASSWORD", "correct")

    wrong_hdr = {"Authorization": "Basic " + base64.b64encode(b"admin:wrong").decode()}
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        resp = c.get("/dashboard", headers=wrong_hdr)
    assert resp.status_code == 401

    al._logger = None
