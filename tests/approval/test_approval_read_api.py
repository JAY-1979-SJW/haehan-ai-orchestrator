"""승인 게이트 3단계: pending/history/detail 조회 API 검증.

검증 항목:
  1. pending 목록만 조회
  2. history 전체 조회
  3. history status 필터
  4. history provider 필터
  5. history 페이지네이션
  6. task 상세 조회
  7. 없는 task_id → 404
  8. admin 허용
  9. owner 허용
  10. viewer 차단 (403)
  11. 민감정보(approval_token_hash, screenshot 절대경로) 미노출
  12. 기존 승인 게이트 회귀 없음 (write API 동작 미변경 확인)
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ── 테스트 데이터 상수 ────────────────────────────────────────────────
_TASK_PENDING_1 = "DR-READ-PENDING-1"
_TASK_PENDING_2 = "DR-READ-PENDING-2"
_TASK_APPROVED_1 = "DR-READ-APPROVED-1"
_TASK_REJECTED_1 = "DR-READ-REJECTED-1"

_SCREENSHOT_ABS = "/srv/data/screenshots/hiworks_2026.png"

OWNER_AUTH = ("owner_u", "pw-owner")
ADMIN_AUTH = ("admin_u", "pw-admin")
VIEWER_AUTH = ("viewer_u", "pw-viewer")


# ── module-scope 픽스처 ───────────────────────────────────────────────


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    storage_dir = tmp_path_factory.mktemp("dr_read_storage")
    users_path = tmp_path_factory.mktemp("dr_read_policies") / "http_users.json"

    users_path.write_text(
        json.dumps(
            [
                {"username": "owner_u", "password_hash": "pw-owner", "role": "owner", "enabled": True},
                {"username": "admin_u", "password_hash": "pw-admin", "role": "admin", "enabled": True},
                {"username": "viewer_u", "password_hash": "pw-viewer", "role": "viewer", "enabled": True},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    os.environ["LOG_DIR"] = str(storage_dir)

    from tests.conftest import apply_basic_auth_users

    mp = pytest.MonkeyPatch()
    apply_basic_auth_users(mp, users_path)
    import ai_orchestrator.core.config as _config

    importlib.reload(_config)
    import tools.gates.approval as _ap

    importlib.reload(_ap)
    _ap.clear_rate_store()
    import ai_orchestrator.audit.audit_logger as _al

    importlib.reload(_al)
    import ai_orchestrator.dev_reg.dev_reg_approval as _dra

    importlib.reload(_dra)
    _dra.clear()
    import ai_orchestrator.routers.registry as _router

    importlib.reload(_router)
    import ai_orchestrator.asgi as _srv

    importlib.reload(_srv)

    exp = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()

    _dra.create_pending(
        task_id=_TASK_PENDING_1,
        token_id=str(uuid.uuid4()),
        provider="hiworks",
        action_type="developer_apply",
        risk_level="high",
        summary="[하이웍스] app_name: TestApp1",
        target_url="https://developers.hiworks.com/apply",
        screenshot_path=_SCREENSHOT_ABS,
        requested_by="tester1",
        expires_at=exp,
    )
    _dra.create_pending(
        task_id=_TASK_PENDING_2,
        token_id=str(uuid.uuid4()),
        provider="naver",
        action_type="app_register",
        risk_level="medium",
        summary="[네이버] client_name: TestApp2",
        target_url="https://developers.naver.com/register",
        screenshot_path="/srv/data/screenshots/naver_2026.png",
        requested_by="tester2",
        expires_at=exp,
    )
    _dra.create_pending(
        task_id=_TASK_APPROVED_1,
        token_id=str(uuid.uuid4()),
        provider="hiworks",
        action_type="app_register",
        risk_level="high",
        summary="[하이웍스] app_name: TestApp3",
        target_url="https://developers.hiworks.com/app",
        screenshot_path="/srv/data/screenshots/hiworks_app.png",
        requested_by="tester1",
        expires_at=exp,
    )
    _dra._update(
        _TASK_APPROVED_1,
        "DEV_REG_APPROVED",
        status="approved",
        approved_by="admin_u",
        decided_at=datetime.now(UTC).isoformat(),
    )

    _dra.create_pending(
        task_id=_TASK_REJECTED_1,
        token_id=str(uuid.uuid4()),
        provider="naver",
        action_type="oauth_submit",
        risk_level="medium",
        summary="[네이버] client_name: BadApp",
        target_url="https://developers.naver.com/oauth",
        screenshot_path="/srv/data/screenshots/naver_oauth.png",
        requested_by="tester2",
        expires_at=exp,
    )
    _dra._update(
        _TASK_REJECTED_1,
        "DEV_REG_REJECTED",
        status="rejected",
        approved_by="owner_u",
        decided_at=datetime.now(UTC).isoformat(),
        reject_reason="정책 위반",
    )

    from fastapi.testclient import TestClient

    client = TestClient(_srv.app, raise_server_exceptions=True)

    yield client

    mp.undo()
    os.environ.pop("LOG_DIR", None)
    importlib.reload(_config)
    _dra.clear()


# ── 1. pending 목록 조회 ──────────────────────────────────────────────


def test_pending_only(setup):
    r = setup.get("/api/v1/dev-reg/approvals/pending", auth=ADMIN_AUTH)
    assert r.status_code == 200
    ids = {d["task_id"] for d in r.json()}
    assert _TASK_PENDING_1 in ids
    assert _TASK_PENDING_2 in ids
    assert _TASK_APPROVED_1 not in ids
    assert _TASK_REJECTED_1 not in ids


# ── 2. history 전체 조회 ──────────────────────────────────────────────


def test_history_all(setup):
    r = setup.get("/api/v1/dev-reg/approvals/history", auth=ADMIN_AUTH)
    assert r.status_code == 200
    ids = {d["task_id"] for d in r.json()}
    assert {_TASK_PENDING_1, _TASK_PENDING_2, _TASK_APPROVED_1, _TASK_REJECTED_1}.issubset(ids)


# ── 3. history status 필터 ────────────────────────────────────────────


def test_history_filter_status_approved(setup):
    r = setup.get("/api/v1/dev-reg/approvals/history?status=approved", auth=ADMIN_AUTH)
    assert r.status_code == 200
    data = r.json()
    assert all(d["status"] == "approved" for d in data)
    assert any(d["task_id"] == _TASK_APPROVED_1 for d in data)
    assert all(d["task_id"] != _TASK_PENDING_1 for d in data)


def test_history_filter_status_rejected(setup):
    r = setup.get("/api/v1/dev-reg/approvals/history?status=rejected", auth=ADMIN_AUTH)
    assert r.status_code == 200
    data = r.json()
    assert all(d["status"] == "rejected" for d in data)
    assert any(d["task_id"] == _TASK_REJECTED_1 for d in data)


def test_history_filter_status_pending(setup):
    r = setup.get("/api/v1/dev-reg/approvals/history?status=pending", auth=ADMIN_AUTH)
    assert r.status_code == 200
    data = r.json()
    assert all(d["status"] == "pending" for d in data)
    ids = {d["task_id"] for d in data}
    assert _TASK_PENDING_1 in ids
    assert _TASK_PENDING_2 in ids
    assert _TASK_APPROVED_1 not in ids


# ── 4. history provider 필터 ──────────────────────────────────────────


def test_history_filter_provider_hiworks(setup):
    r = setup.get("/api/v1/dev-reg/approvals/history?provider=hiworks", auth=ADMIN_AUTH)
    assert r.status_code == 200
    data = r.json()
    assert all(d["provider"] == "hiworks" for d in data)
    ids = {d["task_id"] for d in data}
    assert _TASK_PENDING_1 in ids
    assert _TASK_APPROVED_1 in ids
    assert _TASK_PENDING_2 not in ids
    assert _TASK_REJECTED_1 not in ids


def test_history_filter_provider_naver(setup):
    r = setup.get("/api/v1/dev-reg/approvals/history?provider=naver", auth=ADMIN_AUTH)
    assert r.status_code == 200
    data = r.json()
    assert all(d["provider"] == "naver" for d in data)
    ids = {d["task_id"] for d in data}
    assert _TASK_PENDING_2 in ids
    assert _TASK_REJECTED_1 in ids
    assert _TASK_PENDING_1 not in ids


# ── 5. history 페이지네이션 ───────────────────────────────────────────


def test_history_pagination_limit(setup):
    r = setup.get("/api/v1/dev-reg/approvals/history?limit=2&offset=0", auth=ADMIN_AUTH)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_history_pagination_offset(setup):
    r_all = setup.get("/api/v1/dev-reg/approvals/history?limit=500", auth=ADMIN_AUTH)
    total = len(r_all.json())

    r_offset = setup.get("/api/v1/dev-reg/approvals/history?limit=500&offset=1", auth=ADMIN_AUTH)
    assert r_offset.status_code == 200
    assert len(r_offset.json()) == total - 1


def test_history_limit_capped_at_500(setup):
    r = setup.get("/api/v1/dev-reg/approvals/history?limit=9999", auth=ADMIN_AUTH)
    assert r.status_code == 200  # 서버가 500 으로 cap — 에러 없이 응답


# ── 6. task 상세 조회 ─────────────────────────────────────────────────


def test_detail_pending(setup):
    r = setup.get(f"/api/v1/dev-reg/approvals/{_TASK_PENDING_1}", auth=ADMIN_AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["task_id"] == _TASK_PENDING_1
    assert d["provider"] == "hiworks"
    assert d["status"] == "pending"


def test_detail_approved(setup):
    r = setup.get(f"/api/v1/dev-reg/approvals/{_TASK_APPROVED_1}", auth=OWNER_AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["task_id"] == _TASK_APPROVED_1
    assert d["status"] == "approved"
    assert d["approved_by"] == "admin_u"


# ── 7. 없는 task_id → 404 ────────────────────────────────────────────


def test_detail_not_found(setup):
    r = setup.get("/api/v1/dev-reg/approvals/NONEXISTENT-TASK-XYZ", auth=ADMIN_AUTH)
    assert r.status_code == 404


# ── 8. admin 허용 ─────────────────────────────────────────────────────


def test_admin_allowed_all_endpoints(setup):
    assert setup.get("/api/v1/dev-reg/approvals/pending", auth=ADMIN_AUTH).status_code == 200
    assert setup.get("/api/v1/dev-reg/approvals/history", auth=ADMIN_AUTH).status_code == 200
    assert setup.get(f"/api/v1/dev-reg/approvals/{_TASK_PENDING_1}", auth=ADMIN_AUTH).status_code == 200


# ── 9. owner 허용 ─────────────────────────────────────────────────────


def test_owner_allowed_all_endpoints(setup):
    assert setup.get("/api/v1/dev-reg/approvals/pending", auth=OWNER_AUTH).status_code == 200
    assert setup.get("/api/v1/dev-reg/approvals/history", auth=OWNER_AUTH).status_code == 200
    assert setup.get(f"/api/v1/dev-reg/approvals/{_TASK_PENDING_1}", auth=OWNER_AUTH).status_code == 200


# ── 10. viewer 차단 (403) ────────────────────────────────────────────


def test_viewer_blocked_pending(setup):
    assert setup.get("/api/v1/dev-reg/approvals/pending", auth=VIEWER_AUTH).status_code == 403


def test_viewer_blocked_history(setup):
    assert setup.get("/api/v1/dev-reg/approvals/history", auth=VIEWER_AUTH).status_code == 403


def test_viewer_blocked_detail(setup):
    assert setup.get(f"/api/v1/dev-reg/approvals/{_TASK_PENDING_1}", auth=VIEWER_AUTH).status_code == 403


# ── 11. 민감정보 미노출 ───────────────────────────────────────────────

_SENSITIVE_PATTERNS = [
    "approval_token_hash",
    _SCREENSHOT_ABS,  # 절대경로 미노출
    "screenshot_path",  # 필드 자체 미노출
]

_READ_ENDPOINTS = [
    "/api/v1/dev-reg/approvals/pending",
    "/api/v1/dev-reg/approvals/history",
    f"/api/v1/dev-reg/approvals/{_TASK_PENDING_1}",
]


def test_sensitive_not_exposed_in_pending(setup):
    raw = setup.get("/api/v1/dev-reg/approvals/pending", auth=ADMIN_AUTH).text
    for pattern in _SENSITIVE_PATTERNS:
        assert pattern not in raw, f"민감정보 노출: {pattern!r}"


def test_sensitive_not_exposed_in_history(setup):
    raw = setup.get("/api/v1/dev-reg/approvals/history", auth=ADMIN_AUTH).text
    for pattern in _SENSITIVE_PATTERNS:
        assert pattern not in raw, f"민감정보 노출: {pattern!r}"


def test_sensitive_not_exposed_in_detail(setup):
    raw = setup.get(f"/api/v1/dev-reg/approvals/{_TASK_PENDING_1}", auth=ADMIN_AUTH).text
    for pattern in _SENSITIVE_PATTERNS:
        assert pattern not in raw, f"민감정보 노출: {pattern!r}"


# ── 12. 기존 write API 회귀 — 엔드포인트 존재·형식 확인 ────────────────


def test_existing_tasks_endpoint_unaffected(setup):
    """POST /tasks 가 여전히 응답하는지 확인 (write 동작 미변경)."""
    r = setup.post(
        "/api/v1/tasks",
        json={
            "task_id": f"REGRESS-{uuid.uuid4().hex[:8]}",
            "source": "manual",
            "action_type": "read_file",
            "target": "/tmp/regression_check",  # noqa: S108 — 테스트 픽스처 경로, 실제 파일 생성 없음
            "description": "regression check",
        },
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 200
    data = r.json()
    assert "task_id" in data
    assert "risk_level" in data
