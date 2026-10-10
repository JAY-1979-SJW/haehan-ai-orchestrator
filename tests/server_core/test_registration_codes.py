"""REGCODE-1 registration-code endpoint 검증.

검증 항목:
  - admin/owner 만 발급 가능, viewer 403
  - 1회용 — 두 번째 교환은 generic 400
  - 만료/폐기/오타 모두 generic 400 (응답 분간 불가)
  - list 응답에 registration_code/code_hash/code_salt 미포함
  - audit jsonl 에 registration_code 원문 / device_token 원문 미기록
  - register-with-code 가 agent_id + device_token 을 1회만 반환
  - allowed_actions 검증 — 미등록 액션은 400
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    # auth/local_agent_router 를 reload 하지 않는다: reload 하면 get_current_user 가 시험마다 새 객체가 되는데
    # 하위 라우터는 처음 import 된 옛 객체에 묶여 있어 dependency_overrides 가 두 번째 시험부터 안 먹혀
    # 파일 전체 실행 시 등록이 401 이 되고 KeyError: 'agent_id' 가 난다(단독 실행만 통과, 2026-10-04 확인).

    import ai_orchestrator.agent_hub.registry.common as _reg_common
    import ai_orchestrator.agent_hub.registry.facade as _reg
    import ai_orchestrator.audit.audit_logger as _al
    import ai_orchestrator.auth.registration_codes as _rc
    import tools.gates.approval as _ap

    monkeypatch.setattr(_al, "_LOG_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(_ap, "_STORE_PATH", tmp_path / "approval_tokens.jsonl")
    # 2026-09-29 영속화 추가 후 필수: 안 하면 _reg.clear()가 실제 개발 세션의
    # data/local_agent_registry_state.json(실제 등록된 로컬 에이전트 상태)을 테스트마다 지운다.
    monkeypatch.setattr(_reg_common, "_REGISTRY_STATE_PATH", tmp_path / "local_agent_registry_state.json")

    _reg.clear()
    _rc.clear()
    _ap._store.clear()
    _ap.clear_rate_store()
    yield
    _reg.clear()
    _rc.clear()
    _ap._store.clear()
    _ap.clear_rate_store()


@pytest.fixture
def admin_user():
    return {"actor": "admin_test", "role": "admin"}


@pytest.fixture
def viewer_user():
    return {"actor": "viewer_test", "role": "viewer"}


class _AnyCurrentUserOverrides(dict):
    """이름이 get_current_user 인 의존성은 어느 객체든 같은 사용자로 대체하는 dependency_overrides."""

    def __init__(self, user: dict):
        super().__init__()
        self._user = user

    def __bool__(self) -> bool:  # FastAPI 는 빈 dict 면 override 조회 자체를 건너뛴다
        return True

    def get(self, key, default=None):
        if getattr(key, "__name__", "") == "get_current_user":
            return lambda: self._user
        return super().get(key, default)


def _override_current_user(app, current_get_current_user, user: dict) -> None:
    """앱 라우트가 실제로 묶고 있는 get_current_user 를 객체 동일성과 무관하게 override 한다.

    다른 시험 파일의 fixture 가 importlib.reload(gates.auth) 를 하면 gates.auth.get_current_user 는 새 객체가
    되지만 이미 import 된 라우터는 옛 객체에 묶여 남는다. 그 상태에서 새 객체만 override 하면 라우터는 실제
    의존성(AUTH_ENABLED=False → 고정 owner)을 쓰게 되어 시험 실행 순서에 따라 결과가 달라진다.
    """
    app.dependency_overrides = _AnyCurrentUserOverrides(user)


def _make_client(user_override: dict):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_orchestrator.agent_hub.router.root import local_agent_router
    from tools.gates.auth import get_current_user

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")
    _override_current_user(app, get_current_user, user_override)
    return TestClient(app, raise_server_exceptions=True)


def _audit_lines(tmp_path):
    p = tmp_path / "audit.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


# ── 1. 발급 권한 ─────────────────────────────────────────────────────────


def test_admin_can_issue_code(admin_user):
    client = _make_client(admin_user)
    resp = client.post(
        "/api/v1/local-agents/registration-codes",
        json={
            "label": "대표님 PC",
            "expires_in_minutes": 30,
            "allowed_actions": ["open_url", "capture_screenshot"],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code_id"].startswith("rc-")
    assert body["registration_code"]
    assert "-" in body["registration_code"]  # 4-4-4 형식
    assert body["label"] == "대표님 PC"
    assert "expires_at" in body


def test_viewer_cannot_issue_code(viewer_user):
    client = _make_client(viewer_user)
    resp = client.post(
        "/api/v1/local-agents/registration-codes",
        json={
            "label": "X",
            "expires_in_minutes": 30,
        },
    )
    assert resp.status_code == 403


def test_viewer_cannot_list_codes(viewer_user):
    client = _make_client(viewer_user)
    resp = client.get("/api/v1/local-agents/registration-codes")
    assert resp.status_code == 403


def test_viewer_cannot_revoke(viewer_user, admin_user):
    a_client = _make_client(admin_user)
    issued = a_client.post("/api/v1/local-agents/registration-codes", json={"label": "X"}).json()
    v_client = _make_client(viewer_user)
    resp = v_client.post(f"/api/v1/local-agents/registration-codes/{issued['code_id']}/revoke")
    assert resp.status_code == 403


def test_server_mode_real_auth_enforces_roles_without_override(monkeypatch):
    """dependency_overrides 없이 실제 Basic 인증(AUTH_ENABLED=True)으로 role 검사가 동작하는지 확인한다.

    gates.auth 모듈 전역(config·_load_users)만 바꾸므로 다른 시험의 importlib.reload 로 라우터가 옛 함수에 묶여
    있어도 같은 모듈 전역을 읽어 순서와 무관하다.
    """
    import base64

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import tools.gates.auth as _auth
    from ai_orchestrator.agent_hub.router.root import local_agent_router

    monkeypatch.setattr(_auth.config, "AUTH_ENABLED", True)
    monkeypatch.setattr(
        _auth,
        "_load_users",
        lambda: {
            "v_user": {"password_hash": "pw-v", "role": "viewer", "enabled": True},
            "a_user": {"password_hash": "pw-a", "role": "admin", "enabled": True},
        },
    )

    def _hdr(u, p):
        return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=True)
    url = "/api/v1/local-agents/registration-codes"

    assert client.get(url).status_code == 401
    assert client.get(url, headers=_hdr("v_user", "pw-v")).status_code == 403
    assert client.post(url, json={"label": "X"}, headers=_hdr("v_user", "pw-v")).status_code == 403
    assert client.post(url, json={"label": "X"}, headers=_hdr("a_user", "pw-a")).status_code == 200


# ── 2. 발급 입력 검증 ───────────────────────────────────────────────────


def test_issue_rejects_invalid_ttl(admin_user):
    client = _make_client(admin_user)
    for bad in (0, -1, 60 * 24 + 1):
        resp = client.post("/api/v1/local-agents/registration-codes", json={"label": "X", "expires_in_minutes": bad})
        assert resp.status_code == 400, f"ttl={bad} → {resp.status_code}"


def test_issue_rejects_unknown_action(admin_user):
    client = _make_client(admin_user)
    resp = client.post(
        "/api/v1/local-agents/registration-codes",
        json={
            "label": "X",
            "allowed_actions": ["delete_file"],
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["code"] == "INVALID_ALLOWED_ACTIONS"


def test_issue_rejects_open_url_execute_in_scope(admin_user):
    """high-risk 직접 실행 액션은 등록코드 scope 에 직접 부여 금지."""
    client = _make_client(admin_user)
    resp = client.post(
        "/api/v1/local-agents/registration-codes",
        json={
            "label": "X",
            "allowed_actions": ["open_url_execute"],
        },
    )
    assert resp.status_code == 400


def test_issue_requires_label(admin_user):
    client = _make_client(admin_user)
    resp = client.post("/api/v1/local-agents/registration-codes", json={"label": "   "})
    assert resp.status_code == 400


# ── 3. 교환 흐름 ─────────────────────────────────────────────────────────


def test_exchange_returns_agent_and_token(admin_user):
    a_client = _make_client(admin_user)
    issued = a_client.post("/api/v1/local-agents/registration-codes", json={"label": "PC1"}).json()
    code = issued["registration_code"]

    # register-with-code 는 별도 클라이언트(미인증)로도 동작해야 한다.
    # 현재 라우터는 Depends 없음 — admin_user override 가 있어도 미사용.
    resp = a_client.post(
        "/api/v1/local-agents/register-with-code",
        json={
            "registration_code": code,
            "host": "pc1",
            "os_name": "Windows 11",
            "version": "0.1.0",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent_id"].startswith("la-")
    assert body["device_token"]
    assert body["code_id"] == issued["code_id"]


def test_exchange_one_time_only(admin_user):
    a_client = _make_client(admin_user)
    issued = a_client.post("/api/v1/local-agents/registration-codes", json={"label": "PC1"}).json()
    code = issued["registration_code"]

    r1 = a_client.post("/api/v1/local-agents/register-with-code", json={"registration_code": code, "host": "pc1"})
    assert r1.status_code == 200
    r2 = a_client.post("/api/v1/local-agents/register-with-code", json={"registration_code": code, "host": "pc1"})
    assert r2.status_code == 400
    assert r2.json()["detail"]["message"] == "invalid_registration_code"


def test_exchange_wrong_code_generic(admin_user):
    client = _make_client(admin_user)
    for bad in ("XXXX-XXXX-XXXX", "AAAA-BBBB-CCCC", "not-a-code", "", "ZZZZ"):
        r = client.post("/api/v1/local-agents/register-with-code", json={"registration_code": bad, "host": "pc"})
        assert r.status_code == 400
        assert r.json()["detail"]["message"] == "invalid_registration_code"


def test_exchange_revoked_generic(admin_user):
    a_client = _make_client(admin_user)
    issued = a_client.post("/api/v1/local-agents/registration-codes", json={"label": "X"}).json()
    rv = a_client.post(f"/api/v1/local-agents/registration-codes/{issued['code_id']}/revoke")
    assert rv.status_code == 200
    r = a_client.post(
        "/api/v1/local-agents/register-with-code", json={"registration_code": issued["registration_code"]}
    )
    assert r.status_code == 400
    assert r.json()["detail"]["message"] == "invalid_registration_code"


def test_exchange_expired_generic(admin_user):
    """만료 처리: 발급 직후 expires_at 을 과거로 강제 후 교환 시도."""
    import ai_orchestrator.auth.registration_codes as _rc

    a_client = _make_client(admin_user)
    issued = a_client.post("/api/v1/local-agents/registration-codes", json={"label": "X"}).json()
    rec = _rc.get_code(issued["code_id"])
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    rec.expires_at = past

    r = a_client.post(
        "/api/v1/local-agents/register-with-code", json={"registration_code": issued["registration_code"]}
    )
    assert r.status_code == 400
    assert r.json()["detail"]["message"] == "invalid_registration_code"


def test_exchange_normalizes_input(admin_user):
    """소문자/공백/하이픈 누락 입력도 정규화 후 매칭되어야 한다."""
    a_client = _make_client(admin_user)
    issued = a_client.post("/api/v1/local-agents/registration-codes", json={"label": "X"}).json()
    raw = issued["registration_code"]
    munged = raw.lower().replace("-", " ")
    r = a_client.post("/api/v1/local-agents/register-with-code", json={"registration_code": munged})
    assert r.status_code == 200


# ── 4. list 응답 비밀 노출 차단 ─────────────────────────────────────────


def test_list_does_not_expose_secret(admin_user):
    a_client = _make_client(admin_user)
    a_client.post("/api/v1/local-agents/registration-codes", json={"label": "PC1"}).json()
    a_client.post("/api/v1/local-agents/registration-codes", json={"label": "PC2"}).json()

    resp = a_client.get("/api/v1/local-agents/registration-codes")
    assert resp.status_code == 200
    body = resp.json()
    assert "codes" in body
    assert len(body["codes"]) == 2
    raw = json.dumps(body)
    for forbidden in ("registration_code", "code_hash", "code_salt", "device_token"):
        assert forbidden not in raw, f"{forbidden} leaked in list response"


def test_list_status_transitions(admin_user):
    a_client = _make_client(admin_user)
    issued = a_client.post("/api/v1/local-agents/registration-codes", json={"label": "PC1"}).json()
    # active
    items = a_client.get("/api/v1/local-agents/registration-codes").json()["codes"]
    assert items[0]["status"] == "active"
    # used
    a_client.post("/api/v1/local-agents/register-with-code", json={"registration_code": issued["registration_code"]})
    items = a_client.get("/api/v1/local-agents/registration-codes").json()["codes"]
    assert items[0]["status"] == "used"
    assert items[0]["used_by_agent_id"].startswith("la-")
    # revoke (used → revoked overrides)
    a_client.post(f"/api/v1/local-agents/registration-codes/{issued['code_id']}/revoke")
    items = a_client.get("/api/v1/local-agents/registration-codes").json()["codes"]
    assert items[0]["status"] == "revoked"


# ── 5. audit 비밀 미기록 ────────────────────────────────────────────────


def test_audit_does_not_log_raw_code_or_device_token(admin_user, tmp_path):
    a_client = _make_client(admin_user)
    issued = a_client.post("/api/v1/local-agents/registration-codes", json={"label": "PC1"}).json()
    code_plain = issued["registration_code"]
    used = a_client.post("/api/v1/local-agents/register-with-code", json={"registration_code": code_plain}).json()
    # 폐기 audit 도 기록 시도
    a_client.post(f"/api/v1/local-agents/registration-codes/{issued['code_id']}/revoke")

    lines = _audit_lines(tmp_path)
    assert lines, "audit log empty"
    raw = json.dumps(lines, ensure_ascii=False)
    assert code_plain not in raw, "registration_code raw leaked in audit"
    assert used["device_token"] not in raw, "device_token raw leaked in audit"

    # 이벤트 종류 확인
    types = {e["event_type"] for e in lines}
    assert "REGISTRATION_CODE_ISSUED" in types
    assert "REGISTRATION_CODE_USED" in types
    assert "LOCAL_AGENT_REGISTERED" in types
    assert "REGISTRATION_CODE_REVOKED" in types


def test_failed_exchange_audit_reason(admin_user, tmp_path):
    client = _make_client(admin_user)
    client.post("/api/v1/local-agents/register-with-code", json={"registration_code": "XXXX-XXXX-XXXX"})
    lines = _audit_lines(tmp_path)
    failed = [e for e in lines if e["event_type"] == "REGISTRATION_CODE_EXCHANGE_FAILED"]
    assert failed, "exchange failure not audited"
    assert failed[-1]["decision"] in {"malformed", "not_found"}
