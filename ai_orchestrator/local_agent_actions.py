"""로컬 에이전트 액션 정의 — server/client 공통 상수.

서버(ai_orchestrator.local_agent_registry)와 클라이언트(local_agent.websocket_client)가
동일한 AUTO_EXECUTE_VIA_AGENT 집합을 참조하기 위한 중앙 정의.

이 모듈은 순수 상수만 포함하며, 다른 의존성을 가지지 않는다.
"""
from __future__ import annotations


# PC 로컬 에이전트(client)에 위임되어 자동 실행 가능한 액션 목록.
# Stage 2: WebSocket 으로 PC 에이전트에 위임해 자동 실행 허용되는 액션.
# 이 집합에 포함된 액션만 queued → delivered → running → completed 흐름을 탄다.
#
# Stage 3: capture_screenshot 포함 — 단, high risk 이므로 반드시 승인 후(mark_approved)
# 에만 waiting_approval → queued 로 전환되어 이 경로로 전달된다. 미승인 상태는
# list_pending_for_agent() 에서 제외되어 WS 에 push 되지 않는다.
#
# BROWSER-4E: browser.* actions 추가 — 승인 후 배포됨.
# BROWSER-6D: server/client 정합성 맞춤.
AUTO_EXECUTE_VIA_AGENT: frozenset[str] = frozenset({
    "ping", "system_info", "list_allowed_apps",
    "open_url", "list_files_readonly",
    "capture_screenshot",
    "ws_noop",
    "open_url_execute",
    # browser automation actions (BROWSER-4E)
    "browser.inspect",
    "browser.plan_click",
    "browser.plan_type",
    "browser.plan_submit",
    "browser.execute_click",
    "browser.execute_type",
})
