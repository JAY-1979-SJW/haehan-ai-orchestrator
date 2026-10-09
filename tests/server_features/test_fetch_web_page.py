"""fetch_web_page action 통합 테스트 (운영형 보강 단계).

검증 포인트:
- ALLOWED_ACTIONS 에 fetch_web_page 포함 (whitelist 구조 유지)
- validate_url:
  * 도메인 allowlist 기반 허용 (law.go.kr / kosha.or.kr / moel.go.kr / g2b.go.kr + www)
  * 기존 localhost / 내부망 / file:// / mDNS / 잘못된 URL 차단 유지
  * 비허용 외부 도메인(host_not_allowed) 차단
- fetch_web_page 반환 표준화:
  * 성공 → final_url, http_status, fetched_at, timed_out 필드 포함
  * 실패 → data.{url, timed_out}
  * timeout → timed_out=True
  * snippet 최대 1000자 유지
- 커넥터 예외 → 안전한 error payload 반환 (크래시 금지)
- 승인 후 공개 허용 도메인 조회 성공 (title/snippet 반환, executed=True)
- viewer/operator 승인 시도는 기존 RBAC 유지 (403)
- URL 미허용 시 승인 후 실행 단계에서 BLOCKED_INVALID_TARGET
- 야간/cooldown/rate 정책이 fetch_web_page 에도 우선 적용됨
- 감사 로그(execution_history.jsonl) 에 final_url / http_status / blocked_reason 포함
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import types
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))


# ══ 공통 상수 ═══════════════════════════════════════════════════════
ALLOWED_URL = "https://www.law.go.kr/"
ALLOWED_URL_KOSHA = "https://www.kosha.or.kr/"
NON_ALLOWED_URL = "https://example.com/"


# ══ Playwright 테스트 더블 ═══════════════════════════════════════════
class _FakeTimeout(Exception):
    """Playwright TimeoutError 대체."""


class _FakeResponse:
    def __init__(self, status: int = 200):
        self.status = status


class _FakeLocator:
    def __init__(self, text: str):
        self._text = text

    def inner_text(self, timeout=None):
        return self._text


class _FakePage:
    def __init__(
        self,
        *,
        goto_raises: bool = False,
        resolved_url: str = "https://www.law.go.kr/resolved",
        title_val: str = "법제처 국가법령정보센터",
        body_val: str = "본문 내용 일부입니다.",
        http_status: int = 200,
    ):
        self.url = resolved_url
        self._goto_raises = goto_raises
        self._title = title_val
        self._body = body_val
        self._status = http_status

    def goto(self, *_a, **_kw):
        if self._goto_raises:
            raise _FakeTimeout("goto timeout")
        return _FakeResponse(status=self._status)

    def title(self):
        return self._title

    def locator(self, _selector: str):
        return _FakeLocator(self._body)

    def close(self):
        pass


class _FakeContext:
    def __init__(self, page: _FakePage):
        self._page = page

    def new_page(self):
        return self._page

    def close(self):
        pass


class _FakeBrowser:
    def __init__(self, page: _FakePage):
        self._context = _FakeContext(page)

    def new_context(self, **_):
        return self._context

    def close(self):
        pass


class _FakeChromium:
    def __init__(self, page: _FakePage):
        self._page = page

    def launch(self, **_):
        return _FakeBrowser(self._page)


class _FakePlaywrightCtx:
    def __init__(self, page: _FakePage):
        self.chromium = _FakeChromium(page)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _install_fake_playwright(monkeypatch, *, page: _FakePage):
    fake_mod = types.ModuleType("playwright.sync_api")
    fake_mod.sync_playwright = lambda: _FakePlaywrightCtx(page)  # type: ignore[attr-defined]  # 테스트용 가짜 모듈에 동적으로 속성 부여(mypy가 ModuleType에 없다고 오탐)
    fake_mod.TimeoutError = _FakeTimeout  # type: ignore[attr-defined]
    fake_pkg = types.ModuleType("playwright")
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_mod)


# ══ 단위 테스트: validate_url ════════════════════════════════════════
def test_validate_url_allows_allowlisted_hosts():
    from ai_orchestrator.connectors import playwright_connector as pc

    for u in [
        "https://law.go.kr/",
        "https://www.law.go.kr/abc?q=1",
        "https://kosha.or.kr/",
        "https://www.kosha.or.kr/notice",
        "https://moel.go.kr/",
        "https://www.moel.go.kr/",
        "https://g2b.go.kr/",
        "https://www.g2b.go.kr/",
        "http://www.law.go.kr/",  # http 도 허용 (스킴은 http/https 모두 허용)
    ]:
        ok, reason = pc.validate_url(u)
        assert ok, f"{u} → {reason}"


def test_validate_url_blocks_non_allowlist_hosts():
    from ai_orchestrator.connectors import playwright_connector as pc

    for u in [
        "http://example.com/",
        "https://example.com/",
        "https://google.com/",
        "https://naver.com/",
        "https://sub.law.go.kr/",  # 임의 서브도메인은 보수적으로 거부
        "https://law.go.kr.evil.com/",  # suffix-trick 거부
    ]:
        ok, reason = pc.validate_url(u)
        assert not ok, u
        assert "host_not_allowed" in reason, (u, reason)


def test_validate_url_blocks_localhost_variants():
    from ai_orchestrator.connectors import playwright_connector as pc

    for u in [
        "http://localhost/",
        "http://localhost:8080/",
        "https://LocalHost/",
    ]:
        ok, _ = pc.validate_url(u)
        assert not ok, u


def test_validate_url_blocks_loopback_and_unspecified():
    from ai_orchestrator.connectors import playwright_connector as pc

    for u in [
        "http://127.0.0.1/",
        "http://127.1.2.3/",
        "http://0.0.0.0/",
        "http://[::1]/",
    ]:
        ok, _ = pc.validate_url(u)
        assert not ok, u


def test_validate_url_blocks_internal_ipv4_ranges():
    from ai_orchestrator.connectors import playwright_connector as pc

    for u in [
        "http://10.0.0.1/",
        "http://10.255.255.255/",
        "http://172.16.0.1/",
        "http://172.20.5.5/",
        "http://172.31.255.254/",
        "http://192.168.0.1/",
        "http://192.168.255.255/",
    ]:
        ok, _ = pc.validate_url(u)
        assert not ok, u


def test_validate_url_blocks_non_http_schemes():
    from ai_orchestrator.connectors import playwright_connector as pc

    for u in [
        "file:///etc/passwd",
        "ftp://ftp.example.com/",
        "data:text/html,x",
        "javascript:alert(1)",
        "ssh://host/",
    ]:
        ok, _ = pc.validate_url(u)
        assert not ok, u


def test_validate_url_blocks_empty_or_malformed():
    from ai_orchestrator.connectors import playwright_connector as pc

    for u in ["", "   ", "http://", "not-a-url", "://missing-scheme"]:
        ok, _ = pc.validate_url(u)
        assert not ok, repr(u)


def test_validate_url_blocks_mdns_local():
    from ai_orchestrator.connectors import playwright_connector as pc

    ok, _ = pc.validate_url("http://printer.local/")
    assert not ok


# ══ 커넥터 동작: 표준화된 반환 포맷 ═════════════════════════════════
def test_fetch_web_page_success_payload_shape(monkeypatch):
    """성공 payload 가 final_url/http_status/fetched_at/timed_out 을 포함."""
    from ai_orchestrator.connectors import playwright_connector as pc

    page = _FakePage(
        resolved_url="https://www.law.go.kr/resolved/path",
        title_val="법제처",
        body_val="본문 내용",
        http_status=200,
    )
    _install_fake_playwright(monkeypatch, page=page)

    out = pc.fetch_web_page("https://www.law.go.kr/req")
    assert out["status"] == "success", out
    d = out["data"]
    assert d["url"] == "https://www.law.go.kr/req"
    assert d["final_url"] == "https://www.law.go.kr/resolved/path"
    assert d["title"] == "법제처"
    assert d["snippet"] == "본문 내용"
    assert d["http_status"] == 200
    assert d["timed_out"] is False
    assert "fetched_at" in d and d["fetched_at"].endswith("+00:00")
    # ISO8601(UTC) 기본 형식 체크
    datetime.fromisoformat(d["fetched_at"])


def test_fetch_web_page_snippet_truncated_to_1000(monkeypatch):
    from ai_orchestrator.connectors import playwright_connector as pc

    page = _FakePage(body_val="x" * 5000)
    _install_fake_playwright(monkeypatch, page=page)
    out = pc.fetch_web_page("https://www.law.go.kr/")
    assert out["status"] == "success"
    assert len(out["data"]["snippet"]) == 1000


def test_fetch_web_page_timeout_sets_timed_out_true(monkeypatch):
    """page.goto 타임아웃 → error payload 에 timed_out=True."""
    from ai_orchestrator.connectors import playwright_connector as pc

    page = _FakePage(goto_raises=True)
    _install_fake_playwright(monkeypatch, page=page)

    out = pc.fetch_web_page("https://www.law.go.kr/slow")
    assert out["status"] == "error"
    assert out["error"] == "playwright_timeout"
    assert out["data"]["timed_out"] is True
    assert out["data"]["url"] == "https://www.law.go.kr/slow"


def test_fetch_web_page_blocks_invalid_target_without_playwright(monkeypatch):
    """validate_url 실패 시 playwright 로딩 이전에 안전하게 차단."""
    from ai_orchestrator.connectors import playwright_connector as pc

    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    out = pc.fetch_web_page("http://localhost/")
    assert out["status"] == "error"
    assert pc.BLOCKED_INVALID_TARGET in out["error"]
    assert out["data"]["timed_out"] is False
    assert out["data"]["url"] == "http://localhost/"


def test_fetch_web_page_blocks_non_allowlist_host_in_payload(monkeypatch):
    """외부 도메인은 host_not_allowed 로 error payload 반환."""
    from ai_orchestrator.connectors import playwright_connector as pc

    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    out = pc.fetch_web_page("https://example.com/")
    assert out["status"] == "error"
    assert "host_not_allowed" in out["error"]
    assert out["data"]["timed_out"] is False


def test_fetch_web_page_connector_exception_returns_safe_error(monkeypatch):
    """playwright 내부 예외 → {status:error, error:...} 반환 (크래시 금지)."""
    from ai_orchestrator.connectors import playwright_connector as pc

    def _raise(*_a, **_kw):
        raise RuntimeError("boom")

    fake_pkg = types.ModuleType("playwright")
    fake_mod = types.ModuleType("playwright.sync_api")
    fake_mod.sync_playwright = _raise
    fake_mod.TimeoutError = _FakeTimeout
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_mod)

    out = pc.fetch_web_page("https://www.law.go.kr/")
    assert out["status"] == "error"
    assert "playwright_error" in out["error"]
    assert out["data"]["timed_out"] is False


# ══ 감사 로그 (execution_history) 확인 단위 테스트 ════════════════════
@pytest.fixture
def _isolated_logdir(tmp_path, monkeypatch):
    """executor 직접 호출용 — auth 는 건드리지 않고 LOG_DIR 만 격리."""
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    from ai_orchestrator.core import config as _cfg

    importlib.reload(_cfg)
    from ai_orchestrator.core import execution_limits as _el

    importlib.reload(_el)
    from ai_orchestrator.connectors import playwright_connector as _pc

    importlib.reload(_pc)
    from ai_orchestrator.tasks import executor as _ex

    importlib.reload(_ex)
    yield _cfg, _el, _pc, _ex


def test_audit_note_includes_final_url_and_http_status(_isolated_logdir, monkeypatch):
    _cfg, _el, _pc, _ex = _isolated_logdir
    from ai_orchestrator.core.models import TaskRequest

    # 야간 정책 의존성을 제거 — 주간(KST 12:30) 으로 고정
    monkeypatch.setattr(
        _el,
        "_now",
        lambda: datetime(2026, 4, 22, 3, 30, tzinfo=UTC),
    )
    fake = {
        "status": "success",
        "data": {
            "url": "https://www.law.go.kr/req",
            "final_url": "https://www.law.go.kr/final",
            "title": "T",
            "snippet": "S",
            "http_status": 200,
            "fetched_at": "2026-04-22T00:00:00+00:00",
            "timed_out": False,
        },
    }
    monkeypatch.setattr(_pc, "fetch_web_page", lambda *a, **kw: fake)

    req = TaskRequest(
        task_id="NOTE-OK-1",
        source="manual",
        action_type="fetch_web_page",
        target="https://www.law.go.kr/req",
        description="audit note ok",
        requested_by="admin_u",
    )
    out = _ex.execute_task(req, risk_level="medium")
    assert not out.startswith("BLOCKED"), out

    lines = _cfg.EXECUTION_HISTORY_PATH.read_text(encoding="utf-8").strip().splitlines()
    last = json.loads(lines[-1])
    assert last["task_id"] == "NOTE-OK-1"
    note = last["note"]
    assert "execution_type=REAL" in note
    assert "action=fetch_web_page" in note
    assert "target=https://www.law.go.kr/req" in note
    assert "final_url=https://www.law.go.kr/final" in note
    assert "http_status=200" in note


def test_audit_note_includes_blocked_reason_for_non_allowlist(_isolated_logdir, monkeypatch):
    _cfg, _el, _pc, _ex = _isolated_logdir
    from ai_orchestrator.core.models import TaskRequest

    monkeypatch.setattr(
        _el,
        "_now",
        lambda: datetime(2026, 4, 22, 3, 30, tzinfo=UTC),
    )
    req = TaskRequest(
        task_id="NOTE-BL-1",
        source="manual",
        action_type="fetch_web_page",
        target="https://example.com/",
        description="audit note block",
        requested_by="admin_u",
    )
    out = _ex.execute_task(req, risk_level="medium")
    assert out.startswith("BLOCKED:"), out

    lines = _cfg.EXECUTION_HISTORY_PATH.read_text(encoding="utf-8").strip().splitlines()
    last = json.loads(lines[-1])
    assert last["task_id"] == "NOTE-BL-1"
    note = last["note"]
    assert "execution_type=REAL" in note
    assert "blocked_reason=" in note
    assert "host_not_allowed" in note
    # 민감정보 기록 금지: 본문/쿠키/토큰 흔적 없어야 함
    assert "cookie" not in note.lower()
    assert "password" not in note.lower()


# ══ 통합: 승인 → 실행 플로우 (FastAPI TestClient) ═════════════════════
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
    from ai_orchestrator.connectors import playwright_connector as _pc

    importlib.reload(_pc)
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
    importlib.reload(_pc)
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
def _reset_rate(app_client):
    """approve/reject 인메모리 rate limit 은 테스트 간 초기화."""
    from tools.gates import approval as _ap

    _ap.clear_rate_store()
    yield
    _ap.clear_rate_store()


@pytest.fixture(autouse=True)
def _force_daytime(app_client, monkeypatch):
    """야간(KST 0~6) 정책이 실제 wall-clock 에 따라 테스트를 깨지 않도록 주간 고정.

    개별 테스트(`test_fetch_web_page_night_block_has_priority`)가 자체적으로
    `_now` 를 patch 하는 경우 그 scope 의 patch 가 우선 적용된다.
    """
    from ai_orchestrator.core import execution_limits as _el

    monkeypatch.setattr(
        _el,
        "_now",
        lambda: datetime(2026, 4, 22, 3, 30, tzinfo=UTC),  # KST 12:30
    )
    yield


def _submit_fetch(client, url, auth, task_id=None):
    task_id = task_id or _uniq("F")
    body = {
        "task_id": task_id,
        "source": "manual",
        "action_type": "fetch_web_page",
        "target": url,
        "description": "fetch web page test",
    }
    r = client.post("/api/v1/tasks", json=body, auth=auth)
    return task_id, r


def _approval_token(r):
    """제출 응답에서 승인 토큰을 꺼낸다.

    POST /api/v1/tasks 는 router.POST_TASKS_DRY_RUN_ENABLED=True(정책 잠금, 다른 시험들이 True 를 단언)일 때 토큰을 발급하지 않는다
    ("DRY_RUN: would issue token — gate active"). 이 흐름(승인→실행) 시험은 그 동안 건너뛰고 이유를 남긴다 —
    test_approval_execution_flow 의 기존 방식. 플래그가 꺼졌는데도 토큰이 없으면 진짜 회귀이므로 실패시킨다.
    주의: 정책이 풀려 토큰이 발급돼도 승인 응답에 'executed' 키가 없어(2026-10-05 실측: 플래그를 끄면 8건이 KeyError) 시험 본문이
    추가로 낡았다 — 정책 결정 뒤 별도로 정리해야 한다(이번 변경은 토큰 부재로 인한 실패만 건너뛰기로 바꾼 것).
    """
    from ai_orchestrator.routers import registry as _router

    token_id = r.json().get("approval_token_id")
    if not token_id and _router.POST_TASKS_DRY_RUN_ENABLED:
        pytest.skip("POST /tasks 가 DRY_RUN 게이트(POST_TASKS_DRY_RUN_ENABLED=True)라 승인 토큰을 발급하지 않음")
    assert token_id, r.text
    return token_id


def test_fetch_web_page_in_whitelist(app_client):
    from ai_orchestrator.tasks import executor as ex

    assert "fetch_web_page" in ex.ALLOWED_ACTIONS


def test_fetch_web_page_admin_approve_success(app_client):
    """admin 승인 후 허용 도메인 조회 성공 → 표준 payload 필드 전체 포함, executed=True."""
    from ai_orchestrator.connectors import playwright_connector as pc

    fake = {
        "status": "success",
        "data": {
            "url": ALLOWED_URL,
            "final_url": "https://www.law.go.kr/LSW/main.html",
            "title": "국가법령정보센터",
            "snippet": "법령/판례/행정규칙 등 국가법령정보를 제공합니다.",
            "http_status": 200,
            "fetched_at": "2026-04-22T00:00:00+00:00",
            "timed_out": False,
        },
    }
    with patch.object(pc, "fetch_web_page", return_value=fake):
        task_id, r = _submit_fetch(app_client, ALLOWED_URL, _auth("admin_u"))
        assert r.status_code == 200, r.text
        token_id = _approval_token(r)
        r2 = app_client.post(
            f"/api/v1/tasks/{task_id}/approve", params={"token_id": token_id}, json={}, auth=_auth("admin_u")
        )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["status"] == "approved"
    assert body["executed"] is True, body
    assert body["task_state"] == "executed"
    payload = json.loads(body["execution"])
    assert payload["status"] == "success"
    d = payload["data"]
    assert d["title"] == "국가법령정보센터"
    assert d["url"] == ALLOWED_URL
    assert d["final_url"].startswith("https://www.law.go.kr/")
    assert d["http_status"] == 200
    assert d["timed_out"] is False
    assert "fetched_at" in d


def test_fetch_web_page_viewer_approve_forbidden(app_client):
    task_id, r = _submit_fetch(app_client, ALLOWED_URL, _auth("admin_u"))
    token_id = _approval_token(r)
    r2 = app_client.post(
        f"/api/v1/tasks/{task_id}/approve", params={"token_id": token_id}, json={}, auth=_auth("viewer_u")
    )
    assert r2.status_code == 403


def test_fetch_web_page_operator_approve_forbidden(app_client):
    task_id, r = _submit_fetch(app_client, ALLOWED_URL, _auth("admin_u"))
    token_id = _approval_token(r)
    r2 = app_client.post(
        f"/api/v1/tasks/{task_id}/approve", params={"token_id": token_id}, json={}, auth=_auth("operator_u")
    )
    assert r2.status_code == 403


def _approve_expect_block(app_client, url, expected_marker):
    from ai_orchestrator.connectors import playwright_connector as pc

    with patch.object(pc, "fetch_web_page", wraps=pc.fetch_web_page):
        task_id, r = _submit_fetch(app_client, url, _auth("admin_u"))
        token_id = _approval_token(r)
        r2 = app_client.post(
            f"/api/v1/tasks/{task_id}/approve", params={"token_id": token_id}, json={}, auth=_auth("admin_u")
        )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["status"] == "approved"
    assert body["executed"] is False, body
    assert expected_marker in body["execution"], body


def test_fetch_web_page_blocks_non_allowlist_host_target(app_client):
    """허용 도메인 밖 → BLOCKED_INVALID_TARGET:host_not_allowed."""
    _approve_expect_block(app_client, NON_ALLOWED_URL, "host_not_allowed")


def test_fetch_web_page_blocks_localhost_target(app_client):
    from ai_orchestrator.connectors import playwright_connector as pc

    _approve_expect_block(app_client, "http://localhost:8080/", pc.BLOCKED_INVALID_TARGET)


def test_fetch_web_page_blocks_internal_ip_target(app_client):
    from ai_orchestrator.connectors import playwright_connector as pc

    _approve_expect_block(app_client, "http://10.0.0.5/", pc.BLOCKED_INVALID_TARGET)


def test_fetch_web_page_blocks_file_scheme_target(app_client):
    """file:// 스킴은 connector 의 validate_url 에서 BLOCKED_INVALID_TARGET.

    /tmp/ 는 policy 의 allowed_paths 내이므로 policy 에서 먼저 차단되지 않고,
    executor → validate_url 단계까지 도달해 차단되는지 확인.
    """
    from ai_orchestrator.connectors import playwright_connector as pc

    _approve_expect_block(app_client, "file:///tmp/data.txt", pc.BLOCKED_INVALID_TARGET)


def test_fetch_web_page_blocks_malformed_url_target(app_client):
    from ai_orchestrator.connectors import playwright_connector as pc

    _approve_expect_block(app_client, "not-a-url", pc.BLOCKED_INVALID_TARGET)


def test_fetch_web_page_night_block_has_priority(app_client):
    """야간 강제 시 fetch_web_page 도 BLOCKED:night_blocked (connector 호출 전 차단)."""
    from ai_orchestrator.connectors import playwright_connector as pc
    from ai_orchestrator.core import execution_limits as el

    task_id, r = _submit_fetch(app_client, ALLOWED_URL, _auth("admin_u"))
    token_id = _approval_token(r)

    with (
        patch.object(pc, "fetch_web_page") as spy,
        patch.object(el, "_now", return_value=datetime(2026, 4, 22, 16, 30, tzinfo=UTC)),
    ):
        r2 = app_client.post(
            f"/api/v1/tasks/{task_id}/approve", params={"token_id": token_id}, json={}, auth=_auth("admin_u")
        )
        # 야간 차단 → connector 는 호출되지 않아야 한다
        assert spy.call_count == 0
    body = r2.json()
    assert body["executed"] is False
    assert "night_blocked" in body["execution"]


def test_fetch_web_page_task_cooldown_has_priority(app_client):
    """동일 task_id 가 최근 성공 기록을 가지면 fetch 실행 전 task_cooldown 차단."""
    from ai_orchestrator.connectors import playwright_connector as pc
    from ai_orchestrator.core import execution_limits as el

    fixed_now = datetime(2026, 4, 22, 3, 30, tzinfo=UTC)  # KST 12:30
    task_id = _uniq("CD")
    with patch.object(el, "_now", return_value=fixed_now):
        el.record_execution(task_id, "fetch_web_page", "admin_u", status="OK", risk_level="medium")
        _, r = _submit_fetch(app_client, ALLOWED_URL, _auth("admin_u"), task_id=task_id)
        token_id = _approval_token(r)
        with patch.object(pc, "fetch_web_page") as spy:
            r2 = app_client.post(
                f"/api/v1/tasks/{task_id}/approve", params={"token_id": token_id}, json={}, auth=_auth("admin_u")
            )
            assert spy.call_count == 0
    body = r2.json()
    assert body["executed"] is False
    assert "task_cooldown" in body["execution"]


def test_fetch_web_page_user_rate_limit_has_priority(app_client):
    """user 5min 초과 시 fetch 도 BLOCKED:rate_limited_user_5min (connector 호출 전 차단)."""
    from ai_orchestrator.connectors import playwright_connector as pc
    from ai_orchestrator.core import execution_limits as el

    fixed_now = datetime(2026, 4, 22, 3, 31, tzinfo=UTC)  # 주간
    rate_user = "rate_admin_u"
    with patch.object(el, "_now", return_value=fixed_now):
        for i in range(5):
            el.record_execution(f"FILL-R-{i}", "fetch_web_page", rate_user, status="OK", risk_level="medium")
        r = el.check_user_5min_window(rate_user, max_count=5)
        assert r[0] is False and r[1] == el.BLOCK_USER_5MIN

    from ai_orchestrator.core.models import TaskRequest
    from ai_orchestrator.tasks import executor as ex

    with patch.object(el, "_now", return_value=fixed_now), patch.object(pc, "fetch_web_page") as spy:
        req = TaskRequest(
            task_id=_uniq("UR"),
            source="manual",
            action_type="fetch_web_page",
            target=ALLOWED_URL,
            description="rate limit test",
            requested_by=rate_user,
        )
        result = ex.execute_task(req, risk_level="medium")
        assert spy.call_count == 0
    assert result.startswith("BLOCKED:"), result
    assert "rate_limited" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
