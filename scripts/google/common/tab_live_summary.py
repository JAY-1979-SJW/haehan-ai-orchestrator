"""Google 탭 요약 + 실입력(live-fill) 지원 액션 표시 공용 함수.

cloud/registry.cloud_summary·workspace/registry.workspace_summary 가 탭 키만 바꿔 똑같이 쓰던 본문을
한 곳으로 모았다(잠긴 탭 레지스트리 요약에서 탭 하나를 고르고, 승인 액션을 실입력 지원/준비·열기 전용으로 나눔).
"""

from __future__ import annotations

from scripts.google.common.live_inputs import build_live_input_coverage
from scripts.google.common.tab_registry import build_google_tab_summary


def tab_summary_with_live_inputs(tab_key: str) -> dict:
    """tab_key 탭 요약에 live_input_supported_actions·prepare_or_open_only_approval_actions 를 붙여 돌려준다."""
    summary = build_google_tab_summary()
    tab = next(tab for tab in summary["tabs"] if tab["key"] == tab_key)
    live_supported = {item["action_key"] for item in build_live_input_coverage()["supported"]}
    tab["live_input_supported_actions"] = [
        action["key"] for action in tab["actions"] if action["key"] in live_supported
    ]
    tab["prepare_or_open_only_approval_actions"] = [
        action["key"]
        for action in tab["actions"]
        if action["requires_approval"] and action["key"] not in live_supported
    ]
    return tab
