"""F-4G-3Y-b — local_agent.actions.action_hometax_post_login_observe 검증.

- 등록 여부 확인 (_ACTIONS).
- observe_after_user_ready / build_hometax_controlled_action_plan 가
  monkeypatch 로 호출되는지 (실제 브라우저 미실행).
- 기본 인자 (url=hometax 메인 / wait_until=networkidle / user_ready_seconds=180
  / warmup_url=https://example.com/ / goto_retries=2) 가 전달되는지.
- 결과 dict 의 화이트리스트 키만 노출, cookies/storage_state/raw HTML 미포함.
- forbidden params 거절.
- observer 실패 시 success=False 안전 반환.
- AST scan: 핸들러 본문에 page.click / fill / type / press / keyboard /
  mouse / cookies / storage_state / localStorage 등 금지 키워드 미사용.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from local_agent import actions as _act  # noqa: E402


# ─── helpers ────────────────────────────────────────────────────────────

def _success_observer_result() -> dict:
    return {
        "success": True,
        "error_code": "",
        "warnings": [],
        "target_url": "https://www.hometax.go.kr/",
        "final_url_host_path": "www.hometax.go.kr/",
        "title": "홈택스 - 메인",
        "status_code": 200,
        "page_state": "authenticated",
        "text_excerpt": "마이홈택스 로그아웃",
        "text_length": 150,
        "links_count": 30,
        "buttons_count": 5,
        "forms_count": 1,
        "inputs_count": 2,
        "links": [
            {"text": "마이홈택스", "href": "/something", "risk_hint": ""},
        ],
        "buttons": [{"text": "로그아웃", "type": "button"}],
        "forms": [],
        "input_types": ["text"],
        "warmup_attempted": True,
        "warmup_success": True,
        "warmup_url": "https://example.com/",
        "goto_attempts_used": 1,
        "handoff": {
            "mode": "manual",
            "handoff_seconds": 180,
            "instruction": "user_completes_login_and_navigation_no_credentials",
            "captured_after_handoff": True,
        },
        "security_program_signals": None,
        "hometax_login_candidates": None,
    }


def _success_plan_result() -> dict:
    return {
        "site_key": "hometax",
        "page_state": "authenticated",
        "manual_action_required": False,
        "unrecoverable": False,
        "safe_read_candidates": [{"text": "마이홈택스"}],
        "download_candidates": [],
        "blocked_candidates": [],
        "dangerous_candidates": [],
        "security_program_signals": None,
        "login_candidates": None,
        "warnings": [],
    }


class _FakeCalls:
    def __init__(self) -> None:
        self.observe_kwargs: dict = {}
        self.plan_arg: Any = None


def _patch_observe_and_plan(
    monkeypatch: pytest.MonkeyPatch,
    *,
    observer_result: dict,
    plan_result: dict,
) -> _FakeCalls:
    calls = _FakeCalls()

    def fake_observe(**kwargs: Any) -> dict:
        calls.observe_kwargs = dict(kwargs)
        return observer_result

    def fake_plan(arg: Any) -> dict:
        calls.plan_arg = arg
        return plan_result

    import local_agent.browser_manual_handoff as _mh
    import local_agent.site_adapters.hometax as _hm
    monkeypatch.setattr(_mh, "observe_after_user_ready", fake_observe)
    monkeypatch.setattr(_hm, "build_hometax_controlled_action_plan", fake_plan)
    return calls


# ─── 1. 등록 여부 ────────────────────────────────────────────────────────

def test_handler_registered_in_actions_map():
    assert "hometax_post_login_observe" in _act._ACTIONS
    assert (
        _act._ACTIONS["hometax_post_login_observe"]
        is _act.action_hometax_post_login_observe
    )


def test_execute_action_dispatches_to_handler(monkeypatch):
    calls = _patch_observe_and_plan(
        monkeypatch,
        observer_result=_success_observer_result(),
        plan_result=_success_plan_result(),
    )
    r = _act.execute_action("hometax_post_login_observe", {})
    assert r.success is True
    assert r.error_code == ""
    assert calls.observe_kwargs  # 핸들러를 거쳐 fake_observe 가 호출됨


def test_unknown_action_still_returns_unknown_action():
    """F-4G-3Y-b 도 다른 unknown action 의 폴백 동작은 유지."""
    r = _act.execute_action("nope_such_thing_xyz", {})
    assert not r.success
    assert r.error_code == "UNKNOWN_ACTION"


# ─── 2. 기본 인자 ────────────────────────────────────────────────────────

def test_default_kwargs_passed_through(monkeypatch):
    calls = _patch_observe_and_plan(
        monkeypatch,
        observer_result=_success_observer_result(),
        plan_result=_success_plan_result(),
    )
    r = _act.action_hometax_post_login_observe({})
    assert r.success is True
    kw = calls.observe_kwargs
    assert kw["url"] == "https://www.hometax.go.kr/"
    assert kw["wait_until"] == "networkidle"
    assert kw["user_ready_seconds"] == 180
    assert kw["dwell_after_capture_seconds"] == 10
    assert kw["max_text_chars"] == 10000
    assert kw["warmup_url"] == "https://example.com/"
    assert kw["goto_retries"] == 2
    assert kw["goto_retry_delay_seconds"] == 1.5
    assert kw["goto_timeout_ms"] == 90000


def test_max_text_chars_capped_at_10000(monkeypatch):
    calls = _patch_observe_and_plan(
        monkeypatch,
        observer_result=_success_observer_result(),
        plan_result=_success_plan_result(),
    )
    _act.action_hometax_post_login_observe({"max_text_chars": 999_999})
    assert calls.observe_kwargs["max_text_chars"] == 10000


def test_warmup_url_explicit_none_disables_warmup(monkeypatch):
    calls = _patch_observe_and_plan(
        monkeypatch,
        observer_result=_success_observer_result(),
        plan_result=_success_plan_result(),
    )
    _act.action_hometax_post_login_observe({"warmup_url": None})
    assert calls.observe_kwargs["warmup_url"] is None


def test_warmup_url_empty_string_disables_warmup(monkeypatch):
    calls = _patch_observe_and_plan(
        monkeypatch,
        observer_result=_success_observer_result(),
        plan_result=_success_plan_result(),
    )
    _act.action_hometax_post_login_observe({"warmup_url": "   "})
    assert calls.observe_kwargs["warmup_url"] is None


def test_invalid_int_falls_back_to_default(monkeypatch):
    calls = _patch_observe_and_plan(
        monkeypatch,
        observer_result=_success_observer_result(),
        plan_result=_success_plan_result(),
    )
    _act.action_hometax_post_login_observe({
        "user_ready_seconds": "not-a-number",
        "goto_retries": True,  # bool 은 거절
    })
    assert calls.observe_kwargs["user_ready_seconds"] == 180
    assert calls.observe_kwargs["goto_retries"] == 2


# ─── 3. URL 스킴 가드 ────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "file:///C:/Windows/System32/cmd.exe",
    "javascript:alert(1)",
    "data:text/html,<x>",
    "ftp://example.com/",
])
def test_url_scheme_not_allowed(monkeypatch, url):
    _patch_observe_and_plan(
        monkeypatch,
        observer_result=_success_observer_result(),
        plan_result=_success_plan_result(),
    )
    r = _act.action_hometax_post_login_observe({"url": url})
    assert not r.success
    assert r.error_code == "URL_SCHEME_NOT_ALLOWED"


# ─── 4. forbidden params ────────────────────────────────────────────────

@pytest.mark.parametrize("forbidden_key", [
    "cookie", "cookies", "session", "session_token",
    "storage_state", "localstorage", "sessionstorage",
    "password", "token", "device_token", "secret",
    "api_key", "authorization",
])
def test_forbidden_params_are_rejected(monkeypatch, forbidden_key):
    _patch_observe_and_plan(
        monkeypatch,
        observer_result=_success_observer_result(),
        plan_result=_success_plan_result(),
    )
    r = _act.action_hometax_post_login_observe({forbidden_key: "anything"})
    assert not r.success
    assert r.error_code == "FORBIDDEN_PARAMS"


# ─── 5. observer 실패 / 비정상 응답 ─────────────────────────────────────

def test_observer_failure_returns_success_false(monkeypatch):
    bad = dict(_success_observer_result())
    bad["success"] = False
    bad["error_code"] = "GOTO_FAILED"
    bad["warnings"] = ["goto_attempt_failed:1:TimeoutError"]
    _patch_observe_and_plan(
        monkeypatch,
        observer_result=bad,
        plan_result=_success_plan_result(),
    )
    r = _act.action_hometax_post_login_observe({})
    assert not r.success
    assert r.error_code == "GOTO_FAILED"
    # 결과 페이로드는 화이트리스트로 정상 평탄화되어야 한다.
    assert r.data["action"] == "hometax_post_login_observe"
    assert r.data["success"] is False
    assert r.data["observer"]["error_code"] == "GOTO_FAILED"


def test_observe_raises_returns_observation_failed(monkeypatch):
    import local_agent.browser_manual_handoff as _mh
    import local_agent.site_adapters.hometax as _hm

    def boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(_mh, "observe_after_user_ready", boom)
    monkeypatch.setattr(
        _hm, "build_hometax_controlled_action_plan",
        lambda x: _success_plan_result(),
    )
    r = _act.action_hometax_post_login_observe({})
    assert not r.success
    assert r.error_code == "BROWSER_OBSERVATION_FAILED"
    assert any("observe_failed" in w for w in r.data["warnings"])


def test_observer_returns_non_dict(monkeypatch):
    import local_agent.browser_manual_handoff as _mh
    import local_agent.site_adapters.hometax as _hm

    monkeypatch.setattr(
        _mh, "observe_after_user_ready", lambda **k: "garbage",
    )
    monkeypatch.setattr(
        _hm, "build_hometax_controlled_action_plan",
        lambda x: _success_plan_result(),
    )
    r = _act.action_hometax_post_login_observe({})
    assert not r.success
    assert r.error_code == "BROWSER_OBSERVATION_FAILED"


# ─── 6. 결과 화이트리스트 / forbidden 키 미포함 ─────────────────────────

def test_payload_summary_shape(monkeypatch):
    _patch_observe_and_plan(
        monkeypatch,
        observer_result=_success_observer_result(),
        plan_result=_success_plan_result(),
    )
    r = _act.action_hometax_post_login_observe({})
    assert r.success is True
    s = r.data["summary"]
    for k in (
        "success", "title", "final_url_host_path", "page_state",
        "text_length", "links_count", "buttons_count", "forms_count",
        "inputs_count", "manual_action_required",
        "safe_read_candidates_count", "download_candidates_count",
        "blocked_candidates_count", "warmup_attempted", "warmup_success",
        "goto_attempts_used", "warnings_count",
    ):
        assert k in s, f"missing summary key: {k}"
    assert s["safe_read_candidates_count"] == 1
    assert s["download_candidates_count"] == 0
    assert s["blocked_candidates_count"] == 0


def test_payload_does_not_leak_forbidden_keys_even_if_observer_returned_them(
    monkeypatch,
):
    """방어적 회귀 테스트: 어떤 이유로든 observer 결과에 cookies/
    storage_state/raw HTML 같은 키가 포함되어도, 핸들러가 화이트리스트
    평탄화로 그 키들을 결과 페이로드에 포함시키지 않는다."""
    polluted = dict(_success_observer_result())
    polluted.update({
        "cookies": [{"name": "JSESSIONID", "value": "leaked"}],
        "storage_state": {"origins": []},
        "localStorage": {"k": "v"},
        "sessionStorage": {"k": "v"},
        "raw_html": "<html>...</html>",
        "page_html": "<html>...</html>",
    })
    polluted_plan = dict(_success_plan_result())
    polluted_plan.update({
        "cookies": [{"name": "x"}],
        "storage_state": {"x": 1},
        "raw_html": "<html>",
    })
    _patch_observe_and_plan(
        monkeypatch,
        observer_result=polluted,
        plan_result=polluted_plan,
    )
    r = _act.action_hometax_post_login_observe({})
    blob = json.dumps(r.data, ensure_ascii=False).lower()
    for forbidden in (
        "jsessionid", "leaked", "<html>",
    ):
        assert forbidden.lower() not in blob, (
            f"forbidden value leaked into payload: {forbidden!r}"
        )
    for forbidden_key in (
        "cookies", "cookie", "storage_state",
        "localstorage", "sessionstorage", "raw_html", "page_html",
    ):
        assert forbidden_key not in r.data
        assert forbidden_key not in r.data["observer"]
        assert forbidden_key not in r.data["plan"]


# ─── 7. AST 스캔 — 핸들러 본문에 금지 동작 미사용 ───────────────────────

_FORBIDDEN_ATTR_NAMES: frozenset[str] = frozenset({
    "click", "fill", "type", "press",
    "select_option", "set_input_files",
    "keyboard", "mouse",
    "expect_download",
    "save_as",
    "storage_state", "localStorage", "sessionStorage",
    "cookies",
    "input_value",
})


def _collect_handler_attr_names() -> set[str]:
    """action_hometax_post_login_observe 함수 본문에서 사용되는 모든 Attribute
    이름을 수집한다 (예: page.click → "click"). docstring/주석은 자연히 제외."""
    src_path = Path(_act.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and \
                node.name == "action_hometax_post_login_observe":
            attrs: set[str] = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Attribute):
                    attrs.add(sub.attr)
            return attrs
    raise AssertionError("action_hometax_post_login_observe not found in AST")


def test_handler_body_uses_no_forbidden_apis():
    attrs = _collect_handler_attr_names()
    overlap = _FORBIDDEN_ATTR_NAMES & attrs
    assert not overlap, (
        f"handler 본문에 금지 속성/메서드 사용 감지: {sorted(overlap)}"
    )


def test_handler_imports_only_allowed_modules():
    """핸들러는 browser_manual_handoff / site_adapters.hometax 만 import.
    다른 자동화 모듈은 import 하지 않는다.

    ``ast.ImportFrom.module`` 은 leading dot 없는 모듈 이름만 반환하고,
    relative import 여부는 ``level`` 로 알 수 있다 (level==1 → ``from .x``).
    """
    src = Path(_act.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and \
                node.name == "action_hometax_post_login_observe":
            from_imports: list[tuple[int, str]] = []  # (level, module)
            plain_imports: list[str] = []
            for sub in ast.walk(node):
                if isinstance(sub, ast.ImportFrom):
                    from_imports.append((int(sub.level or 0), sub.module or ""))
                elif isinstance(sub, ast.Import):
                    for n in sub.names:
                        plain_imports.append(n.name)
            # 두 relative import 가 모두 있어야 한다.
            assert (1, "browser_manual_handoff") in from_imports
            assert (1, "site_adapters.hometax") in from_imports
            all_modules = (
                [m for _, m in from_imports] + plain_imports
            )
            for imp in all_modules:
                # 금지 모듈을 임포트하지 않는지.
                assert "playwright" not in imp.lower()
                assert "browser_actions" not in imp.lower()
                assert "browser_login_probe" not in imp.lower()
            return
    raise AssertionError("handler not found")
