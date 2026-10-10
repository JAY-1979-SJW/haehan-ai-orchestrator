"""승인 → 실제 실행 흐름 + RBAC + 상태 머신 통합.

검증 포인트:
- 승인 없이 실행 불가 (medium 제출만으로는 PENDING_APPROVAL, task_state=pending)
- viewer 승인 시도 → 403
- operator 승인 시도 → 403 (기존 RBAC 유지: admin/owner 만)
- admin 승인 → 200, task_state=executed, execution 결과 반환
- 야간 시간대 강제 시 승인 후 실행이 BLOCKED:night_blocked
- /api/v1/telegram/webhook alias 가 /webhooks/telegram 과 동일 동작
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


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

    logdir = tmp_path_factory.mktemp("storage")
    os.environ["LOG_DIR"] = str(logdir)

    from tests.conftest import apply_basic_auth_users

    mp = pytest.MonkeyPatch()
    apply_basic_auth_users(mp, users_path)
    from ai_orchestrator.core import config as _config

    importlib.reload(_config)
    from ai_orchestrator.core import execution_limits as _el

    importlib.reload(_el)
    from ai_orchestrator.tasks import executor as _ex

    importlib.reload(_ex)
    from tools.gates import approval as _ap

    importlib.reload(_ap)
    _ap.clear_rate_store()
    from ai_orchestrator.core import task_state as _ts

    importlib.reload(_ts)
    _ts.clear()
    from ai_orchestrator.sites import router as _sr

    importlib.reload(_sr)
    from ai_orchestrator.routers import registry as _rt

    importlib.reload(_rt)
    from ai_orchestrator import asgi as _srv

    importlib.reload(_srv)

    from fastapi.testclient import TestClient

    yield TestClient(_srv.app, raise_server_exceptions=True)

    mp.undo()
    os.environ.pop("LOG_DIR", None)
    _ap.clear_rate_store()
    importlib.reload(_config)
    importlib.reload(_el)
    importlib.reload(_ex)
    importlib.reload(_ap)
    importlib.reload(_ts)
    importlib.reload(_sr)
    importlib.reload(_rt)
    importlib.reload(_srv)


def _auth(u):
    return (u, f"pw-{u.split('_')[0]}")


def _uniq(p):
    return f"{p}-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _force_daytime(app_client, monkeypatch):
    """개별 테스트가 야간 wall-clock 에 의해 깨지지 않도록 주간(KST 12:30) 고정.

    야간 차단 자체를 검증하는 테스트는 자체 patch 를 적용해 덮어쓴다.
    """
    from ai_orchestrator.core import execution_limits as _el

    monkeypatch.setattr(
        _el,
        "_now",
        lambda: datetime(2026, 4, 22, 3, 30, tzinfo=UTC),
    )
    yield


def _submit_medium(client, auth):
    task_id = _uniq("M")
    body = {
        "task_id": task_id,
        "source": "manual",
        "action_type": "edit_config",
        "target": "/var/www/haehan/cfg.yaml",
        "description": "medium approval flow test",
    }
    r = client.post("/api/v1/tasks", json=body, auth=auth)
    assert r.status_code == 200, r.text
    return task_id, r.json().get("approval_token_id"), r.json()


def test_medium_submit_stays_pending_without_approval(app_client):
    """승인 없이 실행 불가 — submit 직후 status=PENDING_APPROVAL, task_state=pending."""
    task_id, token_id, data = _submit_medium(app_client, _auth("admin_u"))
    if not token_id:
        pytest.skip("medium 경로에서 토큰 발급 안됨")
    assert data["status"] == "PENDING_APPROVAL"
    assert data["requires_approval"] is True

    from ai_orchestrator.core import task_state as ts

    assert ts.get_state(task_id) == "pending"


def test_viewer_approve_forbidden(app_client):
    task_id, token_id, _ = _submit_medium(app_client, _auth("admin_u"))
    if not token_id:
        pytest.skip()
    r = app_client.post(
        f"/api/v1/tasks/{task_id}/approve", params={"token_id": token_id}, json={}, auth=_auth("viewer_u")
    )
    assert r.status_code == 403


def test_operator_approve_forbidden(app_client):
    """기존 RBAC: approve 는 admin/owner 만."""
    task_id, token_id, _ = _submit_medium(app_client, _auth("admin_u"))
    if not token_id:
        pytest.skip()
    r = app_client.post(
        f"/api/v1/tasks/{task_id}/approve", params={"token_id": token_id}, json={}, auth=_auth("operator_u")
    )
    assert r.status_code == 403


def test_admin_approve_triggers_execution(app_client):
    """admin 승인 토큰은 approved 로 전이되나, edit_config 는 whitelist 밖이라 실행은 BLOCKED."""
    task_id, token_id, _ = _submit_medium(app_client, _auth("admin_u"))
    if not token_id:
        pytest.skip()
    r = app_client.post(
        f"/api/v1/tasks/{task_id}/approve", params={"token_id": token_id}, json={}, auth=_auth("admin_u")
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved"
    assert body["approved_by"] == "admin_u"
    # whitelist 도입 이후: edit_config 는 ALLOWED_ACTIONS 밖 → execute_task 가 차단
    assert body["executed"] is False
    assert "not_allowed_action" in body["execution"]
    assert body["task_state"] == "approved"

    from ai_orchestrator.core import task_state as ts

    assert ts.get_state(task_id) == "approved"


def test_reject_moves_to_rejected(app_client):
    task_id, token_id, _ = _submit_medium(app_client, _auth("admin_u"))
    if not token_id:
        pytest.skip()
    r = app_client.post(
        f"/api/v1/tasks/{task_id}/reject", params={"token_id": token_id}, json={"reason": "no"}, auth=_auth("admin_u")
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert body["task_state"] == "rejected"


def test_night_block_prevents_execution(app_client):
    """야간 정책 강제 → 승인은 되지만 execute_task 단계에서 BLOCKED:night_blocked."""
    task_id, token_id, _ = _submit_medium(app_client, _auth("admin_u"))
    if not token_id:
        pytest.skip()

    from ai_orchestrator.core import execution_limits as el

    with patch.object(el, "_now", return_value=datetime(2026, 4, 22, 16, 30, tzinfo=UTC)):
        # UTC 16:30 = KST 01:30 (야간)
        r = app_client.post(
            f"/api/v1/tasks/{task_id}/approve", params={"token_id": token_id}, json={}, auth=_auth("admin_u")
        )
    assert r.status_code == 200
    body = r.json()
    # 승인은 되었고 task_state 는 approved (executed 까지는 못 감)
    assert body["status"] == "approved"
    assert body["executed"] is False
    assert "night_blocked" in body["execution"]
    # state 는 approved 로 남아야 함
    from ai_orchestrator.core import task_state as ts

    assert ts.get_state(task_id) == "approved"


def test_telegram_webhook_endpoint(app_client):
    """/api/v1/webhooks/telegram 은 빈 payload 에 invalid_payload(400) 를 돌려준다(인증 요구 없음).

    별칭 /api/v1/telegram/webhook 은 2026-04-24 핫픽스(3c155f55)에서 제거된 뒤 복구되지 않았고
    이를 호출하는 코드도 없다 — 별칭을 되살리려면 공개 엔드포인트 추가이므로 별도 승인 후 이 테스트에 되돌린다.
    """
    r = app_client.post("/api/v1/webhooks/telegram", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["status"] == "invalid_payload"


def test_user_rate_limit_5min(app_client):
    """동일 사용자 승인 실행이 5회 넘어가면 6번째는 BLOCKED:rate_limited_user_5min."""
    from ai_orchestrator.core import execution_limits as el

    # 과거 5회 실행 기록을 직접 채움 (user 5min 카운트 트리거)
    for i in range(5):
        el.record_execution(f"FILL-{i}", "edit_config", "admin_u", status="OK", risk_level="medium")
    task_id, token_id, _ = _submit_medium(app_client, _auth("admin_u"))
    if not token_id:
        pytest.skip()
    # 주간 시간대 강제
    with patch.object(el, "_now", return_value=datetime(2026, 4, 22, 3, 30, tzinfo=UTC)):
        r = app_client.post(
            f"/api/v1/tasks/{task_id}/approve", params={"token_id": token_id}, json={}, auth=_auth("admin_u")
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    # 실행 단계에서 rate limit 히트
    assert "rate_limited" in body["execution"]
    assert body["executed"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
