"""AUTH_ENABLED=true 상태에서 approve/reject/tasks 경로의 권한/신원 강제 검증.

이번 단계 목표:
- body.role / body.requested_by / body.approved_by 는 신뢰하지 않음
- 실제 권한과 actor 는 current_user 로 단일화
- 역할 매트릭스: owner/admin/operator/viewer 에 대해 approve/reject/tasks 동작 검증
- 스푸핑 차단: body.role=admin 을 보내도 current_user.role 이 낮으면 승인 불가
"""

import importlib
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ── 테스트 전역: AUTH_ENABLED=true 로 전환 후 모듈 리로드 ─────────────
@pytest.fixture(scope="module")
def app_client(tmp_path_factory):
    users_path = tmp_path_factory.mktemp("policies") / "http_users.json"
    users_path.write_text(
        json.dumps(
            [
                {"username": "owner_u", "password_hash": "pw-owner", "role": "owner", "enabled": True},
                {"username": "admin_u", "password_hash": "pw-admin", "role": "admin", "enabled": True},
                {"username": "operator_u", "password_hash": "pw-operator", "role": "operator", "enabled": True},
                {"username": "viewer_u", "password_hash": "pw-viewer", "role": "viewer", "enabled": True},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # 설정 캐시 무효화 → 관련 모듈 리로드
    from tests.conftest import apply_basic_auth_users

    mp = pytest.MonkeyPatch()
    apply_basic_auth_users(mp, users_path)
    from ai_orchestrator.core import config as _config

    importlib.reload(_config)
    from tools.gates import approval as _approval

    importlib.reload(_approval)
    _approval.clear_rate_store()  # module 간 rate counter 누적 차단
    from ai_orchestrator.routers import registry as _router

    importlib.reload(_router)
    from ai_orchestrator import asgi as _server

    importlib.reload(_server)

    from fastapi.testclient import TestClient

    client = TestClient(_server.app, raise_server_exceptions=True)
    yield client

    # 테스트 종료 후 원복
    mp.undo()
    importlib.reload(_config)
    importlib.reload(_router)
    importlib.reload(_server)


def _auth(username: str) -> tuple:
    return (username, f"pw-{username.split('_')[0]}")


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _submit_medium_task(client, auth):
    """medium 위험도 → 승인 토큰 발급되는 경로로 작업 제출.

    allowed_paths 내 쓰기(edit_config)여야 정책 게이트를 통과해 토큰이 발급된다.
    """
    task_id = _uniq("AUTH")
    body = {
        "task_id": task_id,
        "source": "manual",
        "action_type": "edit_config",
        "target": "/var/www/haehan/cfg.yaml",
        "description": "auth enforcement test",
        "requested_by": "CLAIMED-SPOOF",  # 스푸핑 시도 — 무시되어야 함
    }
    r = client.post("/api/v1/tasks", json=body, auth=auth)
    assert r.status_code == 200, r.text
    data = r.json()
    return task_id, data.get("approval_token_id")


# ── 1. POST /tasks — 역할 게이트 ─────────────────────────────────────
def test_tasks_owner_allowed(app_client):
    r = app_client.post(
        "/api/v1/tasks",
        json={
            "task_id": _uniq("OWN"),
            "source": "manual",
            "action_type": "read_file",
            "target": "/tmp/x",  # noqa: S108
            "description": "owner ok",
            "requested_by": "spoof",
        },
        auth=_auth("owner_u"),
    )
    assert r.status_code == 200


def test_tasks_admin_allowed(app_client):
    r = app_client.post(
        "/api/v1/tasks",
        json={
            "task_id": _uniq("ADM"),
            "source": "manual",
            "action_type": "read_file",
            "target": "/tmp/x",  # noqa: S108
            "description": "admin ok",
            "requested_by": "spoof",
        },
        auth=_auth("admin_u"),
    )
    assert r.status_code == 200


def test_tasks_operator_allowed(app_client):
    r = app_client.post(
        "/api/v1/tasks",
        json={
            "task_id": _uniq("OP"),
            "source": "manual",
            "action_type": "read_file",
            "target": "/tmp/x",  # noqa: S108
            "description": "operator ok",
            "requested_by": "spoof",
        },
        auth=_auth("operator_u"),
    )
    assert r.status_code == 200


def test_tasks_viewer_forbidden(app_client):
    r = app_client.post(
        "/api/v1/tasks",
        json={
            "task_id": _uniq("VW"),
            "source": "manual",
            "action_type": "read_file",
            "target": "/tmp/x",  # noqa: S108
            "description": "viewer denied",
            "requested_by": "spoof",
        },
        auth=_auth("viewer_u"),
    )
    assert r.status_code == 403


def test_tasks_unauthenticated_401(app_client):
    r = app_client.post(
        "/api/v1/tasks",
        json={
            "task_id": _uniq("NOA"),
            "source": "manual",
            "action_type": "read_file",
            "target": "/tmp/x",  # noqa: S108
            "description": "no auth",
        },
    )
    assert r.status_code == 401


# ── 2. POST /tasks — requested_by 스푸핑 무시 ────────────────────────
def test_tasks_requested_by_is_current_user(app_client):
    """body.requested_by 를 조작해도 저장/로그의 actor 는 current_user.actor."""
    from ai_orchestrator.audit.audit_logger import read_recent_logs

    task_id = _uniq("SPF")
    r = app_client.post(
        "/api/v1/tasks",
        json={
            "task_id": task_id,
            "source": "manual",
            "action_type": "read_file",
            "target": "/tmp/x",  # noqa: S108
            "description": "spoof test",
            "requested_by": "ATTACKER",
        },
        auth=_auth("operator_u"),
    )
    assert r.status_code == 200

    logs = read_recent_logs(limit=100)
    task_events = [e for e in logs if e["task_id"] == task_id and e["event_type"] == "TASK_RECEIVED"]
    assert task_events, "TASK_RECEIVED 이벤트가 기록되어야 함"
    assert task_events[-1]["actor"] == "operator_u", (
        f"actor 는 current_user.actor 이어야 함. got={task_events[-1]['actor']}"
    )
    assert task_events[-1]["actor"] != "ATTACKER"


# ── 3. approve/reject — 역할 게이트 (auth 계층) ──────────────────────
def test_approve_operator_forbidden(app_client):
    """operator 는 승인 권한 없음 → 403"""
    task_id, token_id = _submit_medium_task(app_client, _auth("admin_u"))
    if not token_id:
        pytest.skip("medium 경로에서 토큰 발급되지 않음(정책 구성 의존)")
    r = app_client.post(
        f"/api/v1/tasks/{task_id}/approve",
        params={"token_id": token_id},
        json={"approved_by": "operator_u", "role": "admin"},  # body.role 스푸핑 시도
        auth=_auth("operator_u"),
    )
    assert r.status_code == 403, f"operator 는 approve 403 이어야 함. got={r.status_code}"


def test_reject_operator_forbidden(app_client):
    task_id, token_id = _submit_medium_task(app_client, _auth("admin_u"))
    if not token_id:
        pytest.skip("medium 경로에서 토큰 발급되지 않음(정책 구성 의존)")
    r = app_client.post(
        f"/api/v1/tasks/{task_id}/reject",
        params={"token_id": token_id},
        json={"rejected_by": "operator_u", "role": "admin", "reason": "no"},
        auth=_auth("operator_u"),
    )
    assert r.status_code == 403


def test_approve_viewer_forbidden(app_client):
    task_id, token_id = _submit_medium_task(app_client, _auth("admin_u"))
    if not token_id:
        pytest.skip("medium 경로에서 토큰 발급되지 않음(정책 구성 의존)")
    r = app_client.post(
        f"/api/v1/tasks/{task_id}/approve",
        params={"token_id": token_id},
        json={"approved_by": "viewer_u", "role": "admin"},  # body.role 스푸핑
        auth=_auth("viewer_u"),
    )
    assert r.status_code == 403


# ── 4. approve/reject — 정상 경로 ────────────────────────────────────
def test_approve_owner_success(app_client):
    task_id, token_id = _submit_medium_task(app_client, _auth("admin_u"))
    if not token_id:
        pytest.skip("medium 경로에서 토큰 발급되지 않음(정책 구성 의존)")
    r = app_client.post(
        f"/api/v1/tasks/{task_id}/approve",
        params={"token_id": token_id},
        json={},  # 빈 바디도 허용되어야 함
        auth=_auth("owner_u"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved"
    # 응답 actor 는 current_user.actor
    assert body["approved_by"] == "owner_u"


def test_reject_admin_success(app_client):
    task_id, token_id = _submit_medium_task(app_client, _auth("admin_u"))
    if not token_id:
        pytest.skip("medium 경로에서 토큰 발급되지 않음(정책 구성 의존)")
    r = app_client.post(
        f"/api/v1/tasks/{task_id}/reject",
        params={"token_id": token_id},
        json={"reason": "부적절"},
        auth=_auth("admin_u"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "rejected"
    assert body["rejected_by"] == "admin_u"


# ── 5. 감사 로그 기준 — current_user 고정 ────────────────────────────
def test_approve_audit_actor_is_current_user(app_client):
    """body.approved_by/role 을 임의 값으로 보내도 audit actor/role 은 current_user 로 기록."""
    from ai_orchestrator.audit.audit_logger import read_recent_logs

    task_id, token_id = _submit_medium_task(app_client, _auth("admin_u"))
    if not token_id:
        pytest.skip("medium 경로에서 토큰 발급되지 않음")

    r = app_client.post(
        f"/api/v1/tasks/{task_id}/approve",
        params={"token_id": token_id},
        json={"approved_by": "ATTACKER", "role": "owner"},  # 스푸핑
        auth=_auth("admin_u"),
    )
    assert r.status_code == 200

    logs = read_recent_logs(limit=200)
    granted = [e for e in logs if e["task_id"] == task_id and e["event_type"] == "APPROVAL_GRANTED"]
    assert granted, "APPROVAL_GRANTED 이벤트가 기록되어야 함"
    assert granted[-1]["actor"] == "admin_u"
    assert granted[-1]["role"] == "admin"
    assert granted[-1]["actor"] != "ATTACKER"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
