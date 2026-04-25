"""F-3 — Google/YouTube open-only 정책 서버측 사전 차단 검증.

배경:
  F-2 에서 ``local_agent.browser_probe.probe_visible_browser`` 가
  Google 계열 URL 을 Playwright launch 전에 거절한다. F-3 은 같은
  정책을 서버 (요청 생성 단계, ``submit_local_agent_task``) 에도
  적용해, ``open_local_browser_probe`` 작업이 큐잉되기 전에 즉시
  ``GOOGLE_OPEN_ONLY`` 응답이 돌아가도록 한다.

검증 항목:
  1) probe + Google open-only URL 6 도메인 → 400 GOOGLE_OPEN_ONLY,
     warnings 에 ``google_open_only_use_open_local_browser`` 포함.
  2) probe + 일반 URL (example.com) → 정책 게이트 미적용. (현재 ACTION_RISK
     에 미등록이므로 UNKNOWN_ACTION 으로 폴백되지만, 정책 게이트가
     일반 URL 까지 잡지 않는다는 회귀 검증.)
  3) open_local_browser + Google URL → 정책 게이트 미적용 (probe 전용).
  4) raw URL query/fragment 가 응답/감사 로그에 노출되지 않는다.
  5) ``params.target_url`` 키도 ``params.url`` 과 동일하게 검사된다.
  6) 기존 ping / capture_screenshot 흐름 회귀 (gate 가 다른 액션을
     건드리지 않는다).
  7) `_is_google_open_only_probe_request` 단위 분류 검증.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ── 격리 fixture (test_local_agent.py 패턴 그대로) ──────────────────────

@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    import importlib
    import ai_orchestrator.auth as _auth; importlib.reload(_auth)
    import ai_orchestrator.local_agent_router as _lar; importlib.reload(_lar)

    import ai_orchestrator.audit_logger as _al
    import ai_orchestrator.approval as _ap
    import ai_orchestrator.local_agent_registry as _reg

    monkeypatch.setattr(_al, "_LOG_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(_ap, "_STORE_PATH", tmp_path / "approval_tokens.jsonl")

    _reg.clear()
    _ap._store.clear()
    _ap.clear_rate_store()

    yield

    _reg.clear()
    _ap._store.clear()
    _ap.clear_rate_store()


@pytest.fixture
def admin_user():
    return {"actor": "admin_test", "role": "admin"}


def _make_test_client(user_override: dict):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from ai_orchestrator.local_agent_router import local_agent_router
    from ai_orchestrator.auth import get_current_user

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user_override
    return TestClient(app, raise_server_exceptions=True)


def _register_agent(client) -> dict:
    resp = client.post("/api/v1/local-agents/register", json={
        "host": "test-pc", "os_name": "Windows 11", "version": "0.1.0",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── 1) probe + Google open-only 6 도메인 → 400 GOOGLE_OPEN_ONLY ────────

_GOOGLE_OPEN_ONLY_PROBE_CASES = [
    # (url, host_token_for_log_check)
    ("https://accounts.google.com/signin?continue=secret-state",
     "accounts.google.com"),
    ("https://google.com/", "google.com"),
    ("https://www.google.com/", "google.com"),
    ("https://studio.youtube.com/", "studio.youtube.com"),
    ("https://www.youtube.com/watch?v=SECRETID",
     "youtube.com"),
    ("https://gmail.com/?session=AAA", "gmail.com"),
    ("https://mail.google.com/mail/u/0/?token=AAA",
     "google.com"),
    ("https://drive.google.com/drive/folders/SECRET?usp=sharing",
     "google.com"),
]


@pytest.mark.parametrize("url,_host", _GOOGLE_OPEN_ONLY_PROBE_CASES)
def test_probe_request_with_google_url_blocked_with_google_open_only(
    admin_user, url: str, _host: str,
) -> None:
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]

    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "open_local_browser_probe",
        "params": {"url": url},
    })

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["error"] == "GOOGLE_OPEN_ONLY"
    assert detail["error_code"] == "GOOGLE_OPEN_ONLY"
    assert "google_open_only_use_open_local_browser" in detail["warnings"]
    # 사용자 안내 문구 (UI 가 그대로 표시) — substring 으로만 확인.
    assert "open_local_browser" in detail["message"]


@pytest.mark.parametrize("url,_host", _GOOGLE_OPEN_ONLY_PROBE_CASES)
def test_probe_block_does_not_leak_query_or_fragment(
    admin_user, url: str, _host: str,
) -> None:
    """차단 응답과 감사 로그 어디에도 raw URL / query / fragment 가
    들어가지 않는다. host 까지만 정책 표시 목적으로 노출 가능."""
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]

    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "open_local_browser_probe",
        "params": {"url": url},
    })
    assert resp.status_code == 400

    body = resp.text
    # raw URL 그대로 (query/fragment 포함) 응답에 들어가지 않아야 한다.
    if "?" in url:
        # 가장 첫 query 토큰 (ex. "secret-state", "SECRETID", "AAA") 이 응답에
        # 직접 노출되지 않아야 한다.
        forbidden_query_tokens = [
            "secret-state", "SECRETID", "session=AAA", "token=AAA",
            "?usp=sharing", "?continue=", "?session=", "?token=",
            "?v=SECRETID",
        ]
        for tok in forbidden_query_tokens:
            assert tok not in body, (tok, body)

    import ai_orchestrator.audit_logger as _al
    if _al._LOG_PATH.exists():
        raw_log = _al._LOG_PATH.read_text(encoding="utf-8")
        for tok in [
            "secret-state", "SECRETID", "session=AAA", "token=AAA",
            "?usp=sharing", "?continue=", "?session=", "?token=",
        ]:
            assert tok not in raw_log, (tok,)


def test_probe_block_emits_audit_event(admin_user) -> None:
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "open_local_browser_probe",
        "params": {"url": "https://studio.youtube.com/"},
    })

    import ai_orchestrator.audit_logger as _al
    events = list(_al.read_recent_logs(limit=50))
    rejected = [e for e in events
                if e["event_type"] == "LOCAL_AGENT_TASK_REJECTED"]
    assert rejected, "GOOGLE_OPEN_ONLY 거절은 감사 로그에 기록되어야 함"
    # note 는 reason=GOOGLE_OPEN_ONLY 만 포함, raw URL 미포함.
    note_blob = " ".join(e.get("note", "") for e in rejected)
    assert "GOOGLE_OPEN_ONLY" in note_blob
    assert "studio.youtube.com" not in note_blob  # host 도 note 에 안 박는다


# ── 2) probe + target_url 키도 동일하게 차단된다 ───────────────────────

def test_probe_block_recognizes_target_url_param_key(admin_user) -> None:
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "open_local_browser_probe",
        "params": {"target_url": "https://accounts.google.com/"},
    })
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "GOOGLE_OPEN_ONLY"


# ── 3) probe + 일반 URL → 정책 게이트 미적용 ──────────────────────────

def test_probe_with_non_google_url_does_not_trigger_google_open_only(
    admin_user,
) -> None:
    """example.com 은 GOOGLE_OPEN_ONLY 게이트에 걸리지 않는다.
    (현재 open_local_browser_probe 가 ACTION_RISK 에 미등록이므로 결국
    UNKNOWN_ACTION 으로 떨어지지만, 핵심은 GOOGLE_OPEN_ONLY 가 아니라는
    것이다.)"""
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "open_local_browser_probe",
        "params": {"url": "https://example.com/"},
    })
    assert resp.status_code == 400
    err = resp.json()["detail"]["error"]
    assert err != "GOOGLE_OPEN_ONLY", (
        "example.com 이 GOOGLE_OPEN_ONLY 로 잘못 분류됨"
    )


def test_probe_without_url_param_does_not_trigger_google_open_only(
    admin_user,
) -> None:
    """url/target_url 자체가 없으면 본 게이트는 건너뛴다."""
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "open_local_browser_probe",
        "params": {},
    })
    assert resp.status_code == 400
    err = resp.json()["detail"]["error"]
    assert err != "GOOGLE_OPEN_ONLY"


# ── 4) open_local_browser + Google URL → 정책 게이트 미적용 ────────────

# ── F-4B) observe_public_browser_page 도 동일 게이트로 차단된다 ────────

@pytest.mark.parametrize("url,_host", _GOOGLE_OPEN_ONLY_PROBE_CASES)
def test_observe_request_with_google_url_blocked_with_google_open_only(
    admin_user, url: str, _host: str,
) -> None:
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]

    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "observe_public_browser_page",
        "params": {"url": url},
    })
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["error"] == "GOOGLE_OPEN_ONLY"
    assert detail["error_code"] == "GOOGLE_OPEN_ONLY"
    assert "google_open_only_use_open_local_browser" in detail["warnings"]


def test_observe_with_non_google_url_does_not_trigger_google_open_only(
    admin_user,
) -> None:
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "observe_public_browser_page",
        "params": {"url": "https://example.com/"},
    })
    # 현재 ACTION_RISK 에 미등록이라 UNKNOWN_ACTION 으로 폴백되지만,
    # 핵심은 GOOGLE_OPEN_ONLY 가 아니라는 것.
    assert resp.status_code == 400
    err = resp.json()["detail"]["error"]
    assert err != "GOOGLE_OPEN_ONLY"


@pytest.mark.parametrize("url,_host", _GOOGLE_OPEN_ONLY_PROBE_CASES)
def test_open_local_browser_action_with_google_url_is_not_gated(
    admin_user, url: str, _host: str,
) -> None:
    """``open_local_browser`` (subprocess) 는 본 정책의 차단 대상이 아니다.

    오늘은 ``open_local_browser`` 도 ACTION_RISK 에 미등록 상태이므로 결국
    UNKNOWN_ACTION 으로 떨어진다. 본 테스트의 핵심은 GOOGLE_OPEN_ONLY
    응답이 절대 돌아가지 않는다는 것 — 즉 게이트가 probe 액션에만
    적용된다는 회귀 검증."""
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "open_local_browser",
        "params": {"url": url},
    })
    assert resp.status_code == 400
    err = resp.json()["detail"]["error"]
    assert err != "GOOGLE_OPEN_ONLY", (
        "open_local_browser 가 GOOGLE_OPEN_ONLY 로 잘못 차단됨"
    )


# ── 5) 기존 액션 회귀 — gate 가 ping/capture_screenshot 을 건드리지 않음 ──

def test_existing_ping_flow_unaffected(admin_user) -> None:
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "ping",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "low"
    assert data["status"] == "completed"


def test_existing_capture_screenshot_flow_unaffected(admin_user) -> None:
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "capture_screenshot",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "high"
    assert data["status"] == "waiting_approval"


# ── 6) _is_google_open_only_probe_request 단위 분류 ────────────────────

def test_unit_is_google_open_only_probe_request_classifier() -> None:
    from ai_orchestrator.local_agent_router import (
        _is_google_open_only_probe_request,
    )

    # 양성: probe + Google URL (다양한 키 / 다양한 도메인)
    pos = [
        ("open_local_browser_probe", {"url": "https://accounts.google.com/"}),
        ("open_local_browser_probe", {"url": "https://google.com/"}),
        ("open_local_browser_probe",
         {"target_url": "https://studio.youtube.com/"}),
        ("OPEN_LOCAL_BROWSER_PROBE",
         {"url": "https://www.youtube.com/"}),
        ("open_local_browser_probe",
         {"url": "https://drive.google.com/folder"}),
        ("open_local_browser_probe", {"url": "https://gmail.com/"}),
        # F-4B: observe action 도 동일 게이트 적용.
        ("observe_public_browser_page",
         {"url": "https://accounts.google.com/"}),
        ("observe_public_browser_page",
         {"url": "https://studio.youtube.com/"}),
        ("OBSERVE_PUBLIC_BROWSER_PAGE",
         {"target_url": "https://drive.google.com/"}),
    ]
    for action, params in pos:
        assert _is_google_open_only_probe_request(action, params) is True, (
            action, params,
        )

    # 음성: 액션 다름 / URL 다름 / params 형태 다름
    neg = [
        ("open_local_browser", {"url": "https://accounts.google.com/"}),
        ("ping", {"url": "https://google.com/"}),
        ("open_local_browser_probe", {"url": "https://example.com/"}),
        ("open_local_browser_probe", {"url": ""}),
        ("open_local_browser_probe", {}),
        ("open_local_browser_probe", None),
        ("open_local_browser_probe", "not-a-dict"),
        ("", {"url": "https://google.com/"}),
        # http/https 가 아니면 정책 대상 아님 (scheme 가 별도 정책에서 거절됨)
        ("open_local_browser_probe", {"url": "ftp://google.com/"}),
        # 비슷한 도메인은 차단되지 않음
        ("open_local_browser_probe", {"url": "https://googleblog.com/"}),
        ("open_local_browser_probe", {"url": "https://google.com.attacker.test/"}),
        # observe 도 일반 URL 은 차단 대상 아님
        ("observe_public_browser_page", {"url": "https://example.com/"}),
        ("observe_public_browser_page", {}),
    ]
    for action, params in neg:
        assert _is_google_open_only_probe_request(action, params) is False, (
            action, params,
        )


# ── 7) 정책 상수 / 메시지 상수 ─────────────────────────────────────────

def test_policy_domains_match_f2_helper() -> None:
    """F-3 서버 게이트의 mirror 가 F-2 단일 출처와 동일한 도메인 집합을
    가지는지 회귀 검증. 서버↔local_agent 직접 import 는 아키텍처 경계상
    금지이므로 양측 상수를 set 비교로 동치성만 확인한다."""
    from ai_orchestrator import local_agent_router as _lar
    from local_agent.browser_launcher import (
        is_google_open_only_url,
        GOOGLE_OPEN_ONLY_DOMAINS,
    )

    # 도메인 집합 동치 — 한쪽이 추가되면 다른 쪽도 같이 추가되어야 한다.
    assert set(_lar._GOOGLE_OPEN_ONLY_DOMAINS) == \
        set(GOOGLE_OPEN_ONLY_DOMAINS), (
            "F-3 server mirror domains diverged from F-2 source",
        )

    # 분류 함수도 동일하게 동작한다 (host 매칭 / scheme 필터).
    sample_urls = [
        "https://accounts.google.com/",
        "https://www.google.com/search",
        "https://studio.youtube.com/channel/abc",
        "https://m.youtube.com/",
        "https://gmail.com/",
        "https://drive.google.com/file",
        "https://example.com/",
        "https://googleblog.com/",
        "https://google.com.attacker.test/",
        "ftp://google.com/",
        "",
    ]
    for u in sample_urls:
        assert _lar._server_is_google_open_only_url(u) == \
            is_google_open_only_url(u), u

    # 메시지/에러 코드 상수도 라우터 모듈에 노출되어 있다.
    assert _lar._GOOGLE_OPEN_ONLY_ERROR == "GOOGLE_OPEN_ONLY"
    assert _lar._GOOGLE_OPEN_ONLY_WARNING == \
        "google_open_only_use_open_local_browser"
    assert "open_local_browser" in _lar._GOOGLE_OPEN_ONLY_MESSAGE


# ── 8) 관리자 UI 페이지 — 정책 안내 문구 노출 ─────────────────────────

def test_admin_ui_page_includes_google_open_only_notice(admin_user) -> None:
    """관리 UI HTML 에 Google/YouTube open-only 정책 안내 문구가 포함되어
    운영자가 별도 매뉴얼 없이도 정책을 인지할 수 있어야 한다 (단순 텍스트
    추가 — 기존 버튼/스크립트 로직에는 영향 없음)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from ai_orchestrator.admin_ui_router import admin_ui_router
    from ai_orchestrator.auth import get_current_user

    app = FastAPI()
    app.include_router(admin_ui_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: admin_user

    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/api/v1/admin/local-agents")
    assert resp.status_code == 200
    body = resp.text
    assert "Google/YouTube" in body
    assert "open_local_browser" in body
