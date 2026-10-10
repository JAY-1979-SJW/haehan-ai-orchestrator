"""local_agent._tool_edit_product — product_id 누락 시 ProductFormRunner 호출 없이 ok=False.

ai_orchestrator/server/mcp_server.py 의 자매 구현 _edit_product() 는 product_id 누락을
미리 막는데, core/agent_runtime/runtime/local_agent.py 의 ws tool_call 경로엔 그 가드가
없어 None 이 ProductFormRunner.edit() 까지 흘러가던 결함(mypy 신규발견으로 드러남,
run38009465088) — 같은 가드를 추가했고, 이 시험은 그 가드가 실제로 외부(CDP 브라우저·
ProductFormRunner) 호출 전에 멈추는지 고정한다.
"""

from __future__ import annotations

import sys

from core.agent_runtime.runtime import local_agent


def test_missing_product_id_returns_ok_false_without_calling_form_runner(monkeypatch):
    called = []

    class _BoomFormRunner:
        def __init__(self, *a, **k):
            called.append("constructed")

    monkeypatch.setitem(
        sys.modules,
        "scripts.naver.smartstore.product.form_runner",
        type(sys)("scripts.naver.smartstore.product.form_runner"),
    )
    sys.modules["scripts.naver.smartstore.product.form_runner"].ProductFormRunner = _BoomFormRunner

    class _BoomCtx:
        @property
        def pages(self):
            called.append("ctx.pages accessed")
            return []

        def new_page(self):
            called.append("ctx.new_page")
            raise AssertionError("product_id 없이 새 페이지를 열면 안 된다")

    result = local_agent._tool_edit_product(None, _BoomCtx(), {})

    assert result == {"ok": False, "error": "product_id 필수"}
    assert called == [], f"product_id 없이 외부/브라우저 호출이 발생함: {called}"


def test_blank_product_id_also_blocked(monkeypatch):
    result = local_agent._tool_edit_product(None, object(), {"product_id": ""})
    assert result == {"ok": False, "error": "product_id 필수"}
