"""ORCHESTRATOR_BROWSER_ACTION_EXECUTION_PIPELINE_01 — 실행 회로 단위.

실제 Chrome / Playwright 미사용. runner / target_resolver 를 주입하여 시뮬레이션.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from local_agent import browser_action_executor as bx
from local_agent import login_state_detector as det
from local_agent.browser_session_store import default_store as _bs


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── 1. supported / unsupported ─────────────────────────────────────

def test_unsupported_action_returns_error():
    r = bx.execute(
        bx.ActionRequest(command_id="c1", action_type="moonwalk"),
        target_resolver=lambda tid: {"exists": True, "closed": False},
        runner=lambda a, p: {"ok": True},
    )
    assert r.ok is False
    assert r.error_code == bx.ERR_UNSUPPORTED_ACTION


def test_submit_action_returns_unsupported_action_from_default_runner():
    # default_runner 가 SUBMIT 에 대해 UNSUPPORTED_ACTION 을 반환 (Enter/click 대체 권장)
    out = bx.default_runner(bx.ACT_SUBMIT, {})
    assert out["ok"] is False
    assert out["error_code"] == bx.ERR_UNSUPPORTED_ACTION


# ── 2. target_not_found / target_closed ─────────────────────────────

def test_target_not_found_when_target_id_given_but_missing():
    r = bx.execute(
        bx.ActionRequest(command_id="c1", action_type="navigate", target_id="T-x",
                         params={"url": "https://example.com"}),
        target_resolver=lambda tid: {"exists": False, "closed": False},
        runner=lambda a, p: {"ok": True},
    )
    assert r.ok is False
    assert r.error_code == bx.ERR_TARGET_NOT_FOUND


def test_target_closed_blocks_execution():
    r = bx.execute(
        bx.ActionRequest(command_id="c1", action_type="navigate", target_id="T-1",
                         params={"url": "https://example.com"}),
        target_resolver=lambda tid: {"exists": True, "closed": True},
        runner=lambda a, p: {"ok": True},
    )
    assert r.ok is False
    assert r.error_code == bx.ERR_TARGET_CLOSED
    assert r.recoverable is False


# ── 3. navigate / click / type 성공 ──────────────────────────────────

def test_navigate_success():
    calls = []

    def runner(action_type, params):
        calls.append((action_type, dict(params)))
        return {"ok": True, "url": params["url"], "title": "Example"}

    r = bx.execute(
        bx.ActionRequest(
            command_id="c1", action_type=bx.ACT_NAVIGATE,
            params={"url": "https://example.com"},
        ),
        target_resolver=lambda tid: {"exists": True, "closed": False},
        runner=runner,
    )
    assert r.ok is True
    assert r.url == "https://example.com"
    assert r.title == "Example"
    assert calls and calls[0][0] == bx.ACT_NAVIGATE


def test_click_success():
    r = bx.execute(
        bx.ActionRequest(
            command_id="c1", action_type=bx.ACT_CLICK,
            params={"text": "Sign in"},
        ),
        target_resolver=lambda tid: {"exists": True, "closed": False},
        runner=lambda a, p: {"ok": True},
    )
    assert r.ok is True


def test_type_success():
    r = bx.execute(
        bx.ActionRequest(
            command_id="c1", action_type=bx.ACT_TYPE,
            params={"target": "#id_input", "text": "hello"},
        ),
        target_resolver=lambda tid: {"exists": True, "closed": False},
        runner=lambda a, p: {"ok": True},
    )
    assert r.ok is True


def test_runner_failure_marks_recoverable():
    r = bx.execute(
        bx.ActionRequest(
            command_id="c1", action_type=bx.ACT_NAVIGATE,
            params={"url": "https://x"},
        ),
        target_resolver=lambda tid: {"exists": True, "closed": False},
        runner=lambda a, p: {"ok": False, "error_code": bx.ERR_RUNNER_FAILED, "reason": "boom"},
    )
    assert r.ok is False
    assert r.error_code == bx.ERR_RUNNER_FAILED
    assert r.recoverable is True


def test_timeout_is_recoverable():
    r = bx.execute(
        bx.ActionRequest(
            command_id="c1", action_type=bx.ACT_WAIT_FOR_SELECTOR,
            params={"selector": ".x"},
        ),
        target_resolver=lambda tid: {"exists": True, "closed": False},
        runner=lambda a, p: {"ok": False, "error_code": bx.ERR_TIMEOUT, "reason": "30s"},
    )
    assert r.ok is False
    assert r.recoverable is True


# ── 4. session store 기반 default_target_resolver ───────────────────

def test_default_target_resolver_closed_tab():
    _bs.clear()
    _bs.start_session()
    _bs.upsert_tab("T-closed", url="https://example.com")
    _bs.mark_tab_closed("T-closed")
    info = bx.default_target_resolver("T-closed")
    assert info["exists"] is True
    assert info["closed"] is True


def test_default_target_resolver_missing_tab():
    _bs.clear()
    _bs.start_session()
    info = bx.default_target_resolver("T-never-existed")
    assert info["exists"] is False


def test_empty_target_id_passes_resolver():
    info = bx.default_target_resolver("")
    assert info["exists"] is True
    assert info["closed"] is False


# ── 5. ActionResult.to_dict 표준 필드 ────────────────────────────────

def test_action_result_to_dict_success():
    r = bx.ActionResult(
        ok=True, command_id="c1", action_type="navigate",
        target_id="T", url="https://x", title="X",
    )
    d = r.to_dict()
    for k in ("ok", "command_id", "action_type", "target_id", "url", "title"):
        assert k in d


def test_action_result_to_dict_failure_has_error_fields():
    r = bx.ActionResult(
        ok=False, command_id="c1", action_type="click",
        error_code="X", reason="why", recoverable=True,
    )
    d = r.to_dict()
    for k in ("error_code", "reason", "recoverable"):
        assert k in d


# ── 6. local_server.browser_action 액션 broadcast 회로 ──────────────

def test_local_server_browser_action_broadcasts(monkeypatch):
    from desktop import local_server as ls
    from local_agent.browser_realtime_watcher import TargetSnapshot

    # 로그인 차단 없음
    monkeypatch.setitem(ls._login_watcher_state, "prev_login_states", {})
    monkeypatch.setitem(ls._login_watcher_state, "prev_targets", [])

    broadcasts: list[dict] = []

    async def fake_broadcast(msg: dict) -> None:
        broadcasts.append(msg)

    monkeypatch.setattr(ls, "_broadcast", fake_broadcast)

    # executor 의 default_runner 호출되지 않도록, execute 자체를 fake 로 monkeypatch
    from local_agent import browser_action_executor as bx_mod

    def fake_execute(req, **_):
        return bx_mod.ActionResult(
            ok=True, command_id=req.command_id, action_type=req.action_type,
            target_id=req.target_id, url="https://example.com", title="ok",
        )

    monkeypatch.setattr(bx_mod, "execute", fake_execute)

    class _FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, m):
            self.sent.append(m)

    ws = _FakeWS()
    _run(ls._handle_browser_action(ws, {
        "command_id": "c-ok",
        "action_type": "navigate",
        "params": {"url": "https://example.com"},
    }))
    types = [b.get("type") for b in broadcasts]
    assert "browser_action_started" in types
    assert "browser_action_completed" in types
    # 직접 응답
    assert any(m.get("type") == "browser_action_result" and m.get("ok") for m in ws.sent)


def test_local_server_browser_action_target_not_found(monkeypatch):
    from desktop import local_server as ls
    from local_agent import browser_action_executor as bx_mod

    monkeypatch.setitem(ls._login_watcher_state, "prev_login_states", {})
    broadcasts: list[dict] = []

    async def fake_broadcast(msg: dict) -> None:
        broadcasts.append(msg)

    monkeypatch.setattr(ls, "_broadcast", fake_broadcast)

    def fake_execute(req, **_):
        return bx_mod.ActionResult(
            ok=False, command_id=req.command_id, action_type=req.action_type,
            target_id=req.target_id,
            error_code=bx_mod.ERR_TARGET_NOT_FOUND, reason="missing",
        )

    monkeypatch.setattr(bx_mod, "execute", fake_execute)

    class _FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, m):
            self.sent.append(m)

    ws = _FakeWS()
    _run(ls._handle_browser_action(ws, {
        "command_id": "c-missing",
        "action_type": "click",
        "target_id": "T-x",
        "params": {"text": "OK"},
    }))
    types = [b.get("type") for b in broadcasts]
    assert "target_not_found" in types


def test_local_server_browser_action_target_closed(monkeypatch):
    from desktop import local_server as ls
    from local_agent import browser_action_executor as bx_mod

    monkeypatch.setitem(ls._login_watcher_state, "prev_login_states", {})
    broadcasts: list[dict] = []

    async def fake_broadcast(msg: dict) -> None:
        broadcasts.append(msg)

    monkeypatch.setattr(ls, "_broadcast", fake_broadcast)

    def fake_execute(req, **_):
        return bx_mod.ActionResult(
            ok=False, command_id=req.command_id, action_type=req.action_type,
            target_id=req.target_id,
            error_code=bx_mod.ERR_TARGET_CLOSED, reason="closed",
        )

    monkeypatch.setattr(bx_mod, "execute", fake_execute)

    class _FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, m):
            self.sent.append(m)

    ws = _FakeWS()
    _run(ls._handle_browser_action(ws, {
        "command_id": "c-closed",
        "action_type": "click",
        "target_id": "T-c",
        "params": {"text": "OK"},
    }))
    types = [b.get("type") for b in broadcasts]
    assert "target_closed" in types


# ── 7. 자동 재개 → browser_action 실행 dispatch ──────────────────────

def test_resume_dispatches_browser_action():
    """LoginAutoFlowEngine 의 resume executor 가 browser_action 도 처리하는지
    desktop/local_server.py 의 dispatch_map 에 등록되어 있어야 한다."""
    import inspect

    from desktop import local_server as ls

    src = inspect.getsource(ls._default_resume_executor)
    assert '"browser_action"' in src


# ── 8. 로그인 차단 상태에서 enqueue 로 보류 ──────────────────────────

# ── 9. dry-run 통합 시나리오 (1→9 전 회로) ───────────────────────────

def test_dry_run_browser_action_login_resume_pipeline(monkeypatch):
    """1) UI browser_action 수신
       2) mocked watcher = LOGIN_REQUIRED
       3) precheck → enqueue_work_command
       4) waiting_login broadcast
       5) mocked LOGGED_IN 감지
       6) engine._default_resume_executor 실행
       7) _from_resume=True 로 browser_action 재dispatch
       8) fake runner 실행
       9) browser_action_completed broadcast 도달

    실제 Chrome / CDP 호출 없음.
    """
    from desktop import local_server as ls
    from local_agent import browser_action_executor as bx_mod
    from local_agent.browser_realtime_watcher import TargetSnapshot

    # broadcast 캡처
    broadcasts: list[dict] = []

    async def fake_broadcast(msg: dict) -> None:
        broadcasts.append(msg)

    monkeypatch.setattr(ls, "_broadcast", fake_broadcast)

    # fake runner — Playwright/CDP 호출 회피.
    # navigate 호출이면 ok=True 와 함께 url/title 반환.
    runner_calls: list[tuple[str, dict]] = []

    def fake_execute(req, **_):
        runner_calls.append((req.action_type, dict(req.params or {})))
        return bx_mod.ActionResult(
            ok=True, command_id=req.command_id, action_type=req.action_type,
            target_id=req.target_id, url="https://mail.google.com/mail/u/0/",
            title="Inbox",
        )

    monkeypatch.setattr(bx_mod, "execute", fake_execute)

    # mocked watcher 상태: LOGIN_REQUIRED 인 auth target 1개
    monkeypatch.setitem(
        ls._login_watcher_state, "prev_login_states",
        {"T-auth": det.LOGIN_REQUIRED},
    )
    monkeypatch.setitem(
        ls._login_watcher_state, "prev_targets",
        [TargetSnapshot(
            target_id="T-auth",
            url="https://accounts.google.com/signin",
            title="Sign in", seen_at=1.0,
        )],
    )

    # engine 신선 상태로 시작 (이전 테스트 잔존 차단)
    eng = ls._ensure_engine()
    eng._pending = None
    eng._login_flow_active = False
    eng._states = {}

    class _FakeWS:
        def __init__(self):
            self.sent: list[dict] = []

        async def send_json(self, m):
            self.sent.append(m)

    ws = _FakeWS()

    async def scenario():
        # Step 1~4: UI browser_action 수신 → precheck → enqueue → waiting_login
        await ls._handle_browser_action(ws, {
            "command_id": "dry-1",
            "action_type": "navigate",
            "params": {"url": "https://mail.google.com/mail/u/0/"},
        })

        # 검증 4: waiting_login 응답
        assert any(
            m.get("type") == "browser_action_status"
            and m.get("status") == "waiting_login"
            for m in ws.sent
        ), "waiting_login 응답 누락"

        # 검증 3: engine 에 pending command 등록됨 + browser_action 으로
        assert eng.pending_command is not None
        assert eng.pending_command.action == "browser_action"
        assert eng.pending_command.original_payload["action_type"] == "navigate"

        # Step 5~6: LOGGED_IN 감지 시뮬레이션
        # engine.on_target_state 동기 호출 → 내부에서 _default_resume_executor 가
        # call_soon_threadsafe 로 _run_browser_action_from_payload 스케줄.
        events = eng.on_target_state(
            "T-auth",
            det.classify(
                "https://mail.google.com/mail/u/0/",
                title="Inbox",
                body_sample="Sign out",
            ),
        )
        types = [e.type for e in events]
        assert "logged_in_detected" in types
        assert "command_auto_resumed" in types

        # Step 7~8: 스케줄된 _run_browser_action_from_payload 가 실행되도록 yield
        for _ in range(5):
            await asyncio.sleep(0)

        # 검증 8: fake runner 가 호출됨 — navigate 액션 1회
        assert runner_calls, "fake runner 미호출 — resume dispatch 가 executor 까지 도달 안 함"
        assert runner_calls[0][0] == "navigate"
        assert runner_calls[0][1].get("url") == "https://mail.google.com/mail/u/0/"

        # 검증 9: browser_action_completed broadcast 도달
        types_all = [m.get("type") for m in broadcasts]
        assert "browser_action_started" in types_all
        assert "browser_action_completed" in types_all

        # 검증 (보너스): 무한 재진입 차단 — 재dispatch payload 에 _from_resume=True
        # → 두 번째 precheck 가 enqueue 하지 않으므로 두 번째 waiting_login 없음
        waiting_count = sum(
            1 for m in broadcasts
            if m.get("type") == "browser_action_status"
            and m.get("status") == "waiting_login"
        )
        # 첫 호출 시 broadcast 1회만 발생 (_broadcast 경로) — 직접 응답은 ws.sent
        # broadcast 측 waiting_login 은 _handle_browser_action 의 _broadcast(msg)
        assert waiting_count <= 1, "재진입 발생 (precheck 가 두 번 enqueue)"

    asyncio.new_event_loop().run_until_complete(scenario())


def test_browser_action_with_login_required_is_enqueued(monkeypatch):
    from desktop import local_server as ls
    from local_agent.browser_realtime_watcher import TargetSnapshot

    monkeypatch.setitem(
        ls._login_watcher_state, "prev_login_states",
        {"T-login": det.LOGIN_REQUIRED},
    )
    monkeypatch.setitem(
        ls._login_watcher_state, "prev_targets",
        [TargetSnapshot(
            target_id="T-login",
            url="https://accounts.google.com/signin",
            title="Sign in", seen_at=1.0,
        )],
    )

    eng = ls._ensure_engine()
    eng._pending = None

    broadcasts: list[dict] = []

    async def fake_broadcast(msg: dict) -> None:
        broadcasts.append(msg)

    monkeypatch.setattr(ls, "_broadcast", fake_broadcast)

    class _FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, m):
            self.sent.append(m)

    ws = _FakeWS()
    _run(ls._handle_browser_action(ws, {
        "command_id": "c-await",
        "action_type": "click",
        "params": {"text": "Hello"},
    }))
    assert eng.pending_command is not None
    assert eng.pending_command.action == "browser_action"
    statuses = [m for m in ws.sent if m.get("type") == "browser_action_status"]
    assert any(s.get("status") == "waiting_login" for s in statuses)
