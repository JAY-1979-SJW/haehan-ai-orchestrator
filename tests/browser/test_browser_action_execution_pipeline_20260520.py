"""ORCHESTRATOR_BROWSER_ACTION_EXECUTION_PIPELINE_01 — 실행 회로 단위.

실제 Chrome / Playwright 미사용. runner / target_resolver 를 주입하여 시뮬레이션.
"""

from __future__ import annotations

import asyncio

from core.agent_runtime.browser import browser_action_executor as bx
from core.agent_runtime.browser.browser_session_store import default_store as _bs


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
        bx.ActionRequest(
            command_id="c1", action_type="navigate", target_id="T-x", params={"url": "https://example.com"}
        ),
        target_resolver=lambda tid: {"exists": False, "closed": False},
        runner=lambda a, p: {"ok": True},
    )
    assert r.ok is False
    assert r.error_code == bx.ERR_TARGET_NOT_FOUND


def test_target_closed_blocks_execution():
    r = bx.execute(
        bx.ActionRequest(
            command_id="c1", action_type="navigate", target_id="T-1", params={"url": "https://example.com"}
        ),
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
            command_id="c1",
            action_type=bx.ACT_NAVIGATE,
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
            command_id="c1",
            action_type=bx.ACT_CLICK,
            params={"text": "Sign in"},
        ),
        target_resolver=lambda tid: {"exists": True, "closed": False},
        runner=lambda a, p: {"ok": True},
    )
    assert r.ok is True


def test_type_success():
    r = bx.execute(
        bx.ActionRequest(
            command_id="c1",
            action_type=bx.ACT_TYPE,
            params={"target": "#id_input", "text": "hello"},
        ),
        target_resolver=lambda tid: {"exists": True, "closed": False},
        runner=lambda a, p: {"ok": True},
    )
    assert r.ok is True


def test_runner_failure_marks_recoverable():
    r = bx.execute(
        bx.ActionRequest(
            command_id="c1",
            action_type=bx.ACT_NAVIGATE,
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
            command_id="c1",
            action_type=bx.ACT_WAIT_FOR_SELECTOR,
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
        ok=True,
        command_id="c1",
        action_type="navigate",
        target_id="T",
        url="https://x",
        title="X",
    )
    d = r.to_dict()
    for k in ("ok", "command_id", "action_type", "target_id", "url", "title"):
        assert k in d


def test_action_result_to_dict_failure_has_error_fields():
    r = bx.ActionResult(
        ok=False,
        command_id="c1",
        action_type="click",
        error_code="X",
        reason="why",
        recoverable=True,
    )
    d = r.to_dict()
    for k in ("error_code", "reason", "recoverable"):
        assert k in d


# ── 6. local_server.browser_action 액션 broadcast 회로 ──────────────

# ── 7. 자동 재개 → browser_action 실행 dispatch ──────────────────────

# ── 8. 로그인 차단 상태에서 enqueue 로 보류 ──────────────────────────

# ── 9. dry-run 통합 시나리오 (1→9 전 회로) ───────────────────────────
