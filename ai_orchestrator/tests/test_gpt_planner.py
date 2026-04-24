"""ai_orchestrator.gpt_planner 검증 (Stage 1, plan_only).

본 테스트는 합성 site_map_payload / user_request 만 사용한다.
  - 실제 GPT / OpenAI API 호출 금지.
  - 실제 웹사이트 접속 금지.
  - 실제 브라우저 / 네트워크 호출 금지.
  - 실제 local_agent action 실행 금지.

모든 테스트는 ``build_planner_prompt_payload`` 와
``build_deterministic_fallback_plan`` 이 deterministic 하게 plan_only
payload 를 만드는지, 민감정보가 차단되는지, 특정 도메인 키워드가 엔진
본체에 하드코딩되어 있지 않은지 검증한다.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ai_orchestrator.gpt_planner import (  # noqa: E402
    DEFAULT_AVAILABLE_ACTIONS,
    DEFAULT_TENANT_POLICY,
    build_deterministic_fallback_plan,
    build_planner_prompt_payload,
    default_available_actions,
    default_tenant_policy,
    sanitize_planner_payload,
)


# ─── 샘플 fixture ─────────────────────────────────────────────────────────


def _site_map_payload_rich() -> dict:
    """일부 safe navigation 후보와 danger 요소가 섞인 합성 site map."""
    return {
        "ok": True,
        "purpose": "generic_site_map_analysis",
        "user_goal": "관찰 작업",
        "page_summary": {
            "title": "Sample List View",
            "current_url_host": "example.com",
            "login_required_hint": False,
            "has_modal_candidates": False,
            "counts": {
                "links": 3, "buttons": 3, "forms": 0,
                "tables": 1, "inputs": 0,
            },
        },
        "sanitized_observation": {
            "links": [
                {"text": "목록", "href": "/list", "risk_hint": "safe_read"},
                {"text": "상세", "href": "/detail/1", "risk_hint": "safe_read"},
                {"text": "삭제",
                 "href": "/admin/delete?id=1",
                 "risk_hint": "danger_write"},
            ],
            "buttons": [
                {"text": "검색", "type": "button",
                 "risk_level": "safe_read", "reason": "keyword:검색"},
                {"text": "저장", "type": "submit",
                 "risk_level": "danger_write", "reason": "keyword:저장"},
                {"text": "제출", "type": "submit",
                 "risk_level": "danger_write", "reason": "type:submit"},
            ],
            "forms": [],
            "tables": [{"headers": ["번호", "상태"], "row_count": 5,
                        "column_count": 2}],
            "inputs": [],
        },
        "heuristic_candidates": {
            "page_role_candidates": [
                {"role": "list_page", "score": 0.7,
                 "reasons": ["tables:1"]},
                {"role": "table_page", "score": 0.65,
                 "reasons": ["tables:1"]},
            ],
            "domain_profile_matches": [],
            "task_candidates": [],
            "danger_elements": [
                {"kind": "button", "text": "저장", "risk": "high",
                 "reason": "universal_danger_term"},
                {"kind": "button", "text": "제출", "risk": "high",
                 "reason": "universal_danger_term"},
                {"kind": "link", "text": "삭제", "risk": "high",
                 "reason": "classified_danger_write"},
            ],
            "safe_navigation_candidates": [
                {"kind": "link", "text": "목록", "risk": "low",
                 "score": 3,
                 "reasons": ["universal_safe_term", "safe_read_link"]},
                {"kind": "link", "text": "상세", "risk": "low",
                 "score": 3,
                 "reasons": ["universal_safe_term", "safe_read_link"]},
                {"kind": "button", "text": "검색", "risk": "low",
                 "score": 3,
                 "reasons": ["universal_safe_term", "safe_read_button"]},
            ],
        },
        "warnings": [],
    }


def _site_map_login_required() -> dict:
    payload = _site_map_payload_rich()
    payload["page_summary"]["login_required_hint"] = True
    return payload


def _site_map_with_modal() -> dict:
    payload = _site_map_payload_rich()
    payload["page_summary"]["has_modal_candidates"] = True
    return payload


# ─── 1. site_map 없는 경우 fallback ───────────────────────────────────────


def test_fallback_plan_without_site_map():
    payload = build_planner_prompt_payload(
        user_request="사이트 구조 파악",
        site_map_payload=None,
    )
    assert payload["ok"] is True
    assert payload["planning_mode"] == "plan_only"
    plan = payload["deterministic_fallback_plan"]
    assert plan["mode"] == "plan_only"
    # 사이트 정보가 없으므로 사용자 질문이 반드시 포함되어야 한다.
    assert any(
        "사이트" in q or "URL" in q or "관찰" in q
        for q in plan["questions_for_user"]
    )
    # 최소 하나의 step 또는 0 step 이어야 하며 모두 plan_only.
    for step in plan["steps"]:
        assert step["auto_execute"] is False
        assert step["requires_approval"] is True


# ─── 2. site_map 있는 경우 safe navigation 반영 ───────────────────────────


def test_safe_navigation_becomes_plan_only_steps():
    payload = build_planner_prompt_payload(
        user_request="목록을 살펴보고 싶다",
        site_map_payload=_site_map_payload_rich(),
    )
    plan = payload["deterministic_fallback_plan"]
    step_texts = {
        (step.get("target") or {}).get("text", "") for step in plan["steps"]
    }
    # "목록" / "상세" 같은 safe navigation 후보가 step 으로 들어가야 한다.
    assert "목록" in step_texts or "상세" in step_texts
    # 모든 step 은 plan_only.
    for step in plan["steps"]:
        assert step["auto_execute"] is False
        assert step["requires_approval"] is True
        assert step["action"] in {
            a["name"] for a in DEFAULT_AVAILABLE_ACTIONS
        }


# ─── 3. danger_elements 는 blocked_or_deferred 로 분리 ───────────────────


def test_danger_elements_are_isolated_in_blocked():
    plan = build_deterministic_fallback_plan(
        user_request="저장을 해봐",  # user 요청에 danger term 섞여 있어도 계획에 올리지 않음.
        site_map_payload=_site_map_payload_rich(),
        available_actions=list(DEFAULT_AVAILABLE_ACTIONS),
        tenant_policy=dict(DEFAULT_TENANT_POLICY),
    )
    step_targets = [
        (step.get("target") or {}).get("text", "") for step in plan["steps"]
    ]
    for danger in ("저장", "제출", "삭제"):
        assert danger not in step_targets, (
            f"danger text {danger} leaked into steps"
        )
    blocked_actions = " ".join(
        str(b.get("action", "") or "") + " " + str(b.get("reason", "") or "")
        for b in plan["blocked_or_deferred"]
    )
    for danger in ("저장", "제출", "삭제"):
        assert danger in blocked_actions, (
            f"danger term {danger} missing from blocked_or_deferred"
        )


# ─── 4. 모든 steps.auto_execute=false ────────────────────────────────────


def test_every_step_is_auto_execute_false():
    payload = build_planner_prompt_payload(
        user_request="검색해보고 싶다",
        site_map_payload=_site_map_payload_rich(),
    )
    for step in payload["deterministic_fallback_plan"]["steps"]:
        assert step["auto_execute"] is False


# ─── 5. high/critical 은 requires_approval=true ─────────────────────────


def test_blocked_entries_have_high_or_critical_risk():
    plan = build_deterministic_fallback_plan(
        user_request="목록 보기",
        site_map_payload=_site_map_payload_rich(),
        available_actions=list(DEFAULT_AVAILABLE_ACTIONS),
        tenant_policy=dict(DEFAULT_TENANT_POLICY),
    )
    for item in plan["blocked_or_deferred"]:
        assert item["risk"] in ("high", "critical")


# ─── 6. submit/delete/payment/password_fill 은 blocked_or_deferred ─────


def test_blocked_actions_always_reflected():
    plan = build_deterministic_fallback_plan(
        user_request="테스트",
        site_map_payload=_site_map_payload_rich(),
        available_actions=list(DEFAULT_AVAILABLE_ACTIONS),
        tenant_policy=dict(DEFAULT_TENANT_POLICY),
    )
    blocked_names = {b.get("action") for b in plan["blocked_or_deferred"]}
    for must in ("submit_form", "delete", "payment",
                 "credential_submit", "password_fill"):
        assert must in blocked_names, f"missing blocked action: {must}"


# ─── 7. login_required_hint 면 로그인 질문 생성 ──────────────────────────


def test_login_required_hint_triggers_user_question():
    plan = build_deterministic_fallback_plan(
        user_request="페이지 열어줘",
        site_map_payload=_site_map_login_required(),
        available_actions=list(DEFAULT_AVAILABLE_ACTIONS),
        tenant_policy=dict(DEFAULT_TENANT_POLICY),
    )
    assert any(
        ("로그인" in q or "login" in q.lower())
        for q in plan["questions_for_user"]
    )


# ─── 8. modal 후보 있으면 사용자 확인 질문 생성 ──────────────────────────


def test_modal_hint_triggers_user_question():
    plan = build_deterministic_fallback_plan(
        user_request="페이지 열어줘",
        site_map_payload=_site_map_with_modal(),
        available_actions=list(DEFAULT_AVAILABLE_ACTIONS),
        tenant_policy=dict(DEFAULT_TENANT_POLICY),
    )
    assert any(
        ("모달" in q or "modal" in q.lower() or "닫기" in q)
        for q in plan["questions_for_user"]
    )


# ─── 9. user_request 가 빈 문자열이면 안전 질문 생성 ─────────────────────


def test_empty_user_request_adds_clarifying_question():
    payload = build_planner_prompt_payload(
        user_request="",
        site_map_payload=_site_map_payload_rich(),
    )
    plan = payload["deterministic_fallback_plan"]
    assert "user_request_missing" in payload["warnings"]
    assert any(
        ("알려주세요" in q or "구체" in q)
        for q in plan["questions_for_user"]
    )


# ─── 10. available_actions 기본값 포함 ──────────────────────────────────


def test_default_available_actions_present_by_default():
    payload = build_planner_prompt_payload(
        user_request="검사",
        site_map_payload=_site_map_payload_rich(),
    )
    names = {a["name"] for a in payload["available_actions"]}
    for must in (
        "web_open_url_readonly",
        "web_analyze_html",
        "web_build_site_map_prompt",
        "web_click_guarded",
        "web_type_guarded",
        "web_select_guarded",
        "web_scroll_guarded",
        "scan_file_tree",
    ):
        assert must in names


# ─── 11. tenant_policy 기본값 auto_execute 금지 ─────────────────────────


def test_default_tenant_policy_forbids_auto_execute():
    payload = build_planner_prompt_payload(
        user_request="검사",
        site_map_payload=_site_map_payload_rich(),
    )
    policy = payload["tenant_policy"]
    assert policy["allow_auto_execute"] is False
    assert policy["allow_click"] is False
    assert policy["allow_type"] is False
    assert policy["allow_submit"] is False
    assert policy["allow_delete"] is False
    # 외부 입력이 auto_execute=true 를 주장하더라도 무시되어야 한다.
    overridden = build_planner_prompt_payload(
        user_request="검사",
        site_map_payload=_site_map_payload_rich(),
        tenant_policy={"allow_auto_execute": True},
    )
    assert overridden["tenant_policy"]["allow_auto_execute"] is False


# ─── 12. planner_instruction 필수 지침 포함 ─────────────────────────────


def test_planner_instruction_contains_plan_only_and_danger_guard():
    payload = build_planner_prompt_payload(
        user_request="검사",
        site_map_payload=_site_map_payload_rich(),
    )
    instruction = payload["planner_instruction"]
    assert "plan_only" in instruction
    assert "auto_execute=false" in instruction.lower()
    assert "requires_approval=true" in instruction.lower()
    # 위험 작업 자동 계획 금지 지침.
    for token in ("Save", "Delete", "Submit", "Payment"):
        assert token in instruction


# ─── 13. expected_json_schema 필수 필드 존재 ────────────────────────────


def test_expected_json_schema_fields_present():
    payload = build_planner_prompt_payload(
        user_request="검사",
        site_map_payload=_site_map_payload_rich(),
    )
    schema = payload["expected_json_schema"]
    for key in (
        "goal", "confidence", "mode", "needs_user_confirmation",
        "questions_for_user", "steps", "blocked_or_deferred",
        "safety_notes", "do_not_execute",
    ):
        assert key in schema
    assert schema["mode"] == "plan_only"
    # steps 내 필수 필드.
    sample_step = schema["steps"][0]
    for key in (
        "step_id", "action", "description", "target",
        "risk", "requires_approval", "auto_execute", "reason",
    ):
        assert key in sample_step
    assert sample_step["auto_execute"] is False


# ─── 14. 민감정보 redaction ───────────────────────────────────────────────


def test_sensitive_values_are_redacted():
    dirty = {
        "user_request": "ok",
        "password": "p@ssw0rd",
        "cookie": "session=xyz",
        "authorization": "Bearer abcdef1234567890",
        "api_key": "sk-verysecretvalue12345",
        "csrf_token": "tok123",
        "raw_html": "<html>...</html>",
        "screenshot_path": "/home/user/secret.png",
        "absolute_path": "/home/user/docs",
        "nested": {
            "cookie": "a=b",
            "has_password": True,
            "page_html": "<body>..",
        },
        "benign": "hello",
    }
    cleaned = sanitize_planner_payload(dirty)
    # drop 대상 키는 존재하지 않아야 한다.
    for dropped in (
        "raw_html", "screenshot_path", "absolute_path", "cookie",
        "authorization",
    ):
        assert dropped not in cleaned
    assert cleaned.get("password") == "<redacted>"
    assert cleaned.get("api_key") == "<redacted>"
    assert cleaned.get("csrf_token") == "<redacted>"
    assert cleaned.get("benign") == "hello"
    # 존재 플래그는 보존.
    assert cleaned["nested"]["has_password"] is True
    assert "cookie" not in cleaned["nested"]
    assert "page_html" not in cleaned["nested"]


def test_build_payload_drops_raw_html_and_cookies_from_site_map():
    site_map = _site_map_payload_rich()
    site_map["raw_html"] = "<html>sensitive</html>"
    site_map["cookies"] = {"sid": "abc"}
    site_map["api_key"] = "sk-reallysecret987654321"
    site_map["nested"] = {"bearer_token": "Bearer xyzxyzxyzxyz"}
    payload = build_planner_prompt_payload(
        user_request="검사",
        site_map_payload=site_map,
    )
    as_str = repr(payload)
    assert "<html>sensitive</html>" not in as_str
    assert "sk-reallysecret" not in as_str
    assert "Bearer xyzxyzxyz" not in as_str
    assert "raw_html" not in payload["site_context_summary"]
    # sanitized_observation 내부까지도 민감 키는 redact 됨.
    sanitized_payload = repr(payload)
    assert "p@ssw0rd" not in sanitized_payload


# ─── 15. OpenAI / 외부 API 호출 코드 없음 정적 검사 ─────────────────────


def _planner_source() -> str:
    path = Path(__file__).resolve().parent.parent / "gpt_planner.py"
    return path.read_text(encoding="utf-8")


def test_no_real_openai_or_http_calls_in_source():
    src = _planner_source()
    # openai SDK 임포트 금지.
    assert re.search(r"^\s*(from|import)\s+openai\b", src, re.MULTILINE) is None
    forbidden_patterns = (
        "chat.completions",
        "responses.create",
        "openai.",
        "requests.post",
        "requests.get",
        "requests.Session",
        "httpx.post",
        "httpx.get",
        "httpx.Client",
        "urllib.request.urlopen",
        "aiohttp.",
    )
    for pat in forbidden_patterns:
        assert pat not in src, f"forbidden external call pattern: {pat}"


# ─── 16. action 실행 코드 없음 정적 검사 ────────────────────────────────


def test_no_action_execution_in_source():
    src = _planner_source()
    forbidden_patterns = (
        "execute_action(",
        "page.click(",
        "page.fill(",
        "page.type(",
        "page.goto(",
        "page.press(",
        "webbrowser.open(",
        "subprocess.",
        "os.system(",
        "os.popen(",
        "send2trash",
    )
    for pat in forbidden_patterns:
        assert pat not in src, f"forbidden execution pattern: {pat}"
    # local_agent 의 실행 모듈을 import 하지 않는다.
    assert "from local_agent.actions" not in src
    assert "from local_agent.browser_actions" not in src
    assert "from local_agent.browser_reader" not in src


# ─── 17. 특정 도메인 키워드 하드코딩 없음 정적 검사 ──────────────────────


def test_no_domain_specific_keywords_in_source():
    src = _planner_source()
    forbidden_keywords = (
        "기성", "청구", "정산", "계약", "현장",
        "배민", "카페", "유튜브", "YouTube", "youtube",
        "API 신청", "OAuth", "리뷰", "댓글",
    )
    for kw in forbidden_keywords:
        assert kw not in src, f"domain keyword hardcoded: {kw!r}"


# ─── 18. max_steps 제한 적용 ────────────────────────────────────────────


def test_max_steps_limit_is_enforced():
    # 많은 safe 후보가 있어도 max_steps 보다 많은 step 을 만들지 않는다.
    site_map = _site_map_payload_rich()
    extra = []
    for i in range(30):
        extra.append({
            "kind": "link", "text": f"항목{i}", "risk": "low",
            "score": 3,
            "reasons": ["universal_safe_term", "safe_read_link"],
        })
    site_map["heuristic_candidates"]["safe_navigation_candidates"] = extra

    payload = build_planner_prompt_payload(
        user_request="목록 살펴보기",
        site_map_payload=site_map,
        max_steps=3,
    )
    assert payload["max_steps"] == 3
    assert len(payload["deterministic_fallback_plan"]["steps"]) <= 3


# ─── 19. fallback plan confidence 과도하게 높지 않음 ───────────────────


def test_fallback_plan_confidence_is_bounded():
    payload = build_planner_prompt_payload(
        user_request="검사",
        site_map_payload=_site_map_payload_rich(),
    )
    confidence = payload["deterministic_fallback_plan"]["confidence"]
    assert 0.0 <= confidence <= 0.5, (
        f"fallback plan confidence too high: {confidence}"
    )

    empty_payload = build_planner_prompt_payload(
        user_request="",
        site_map_payload=None,
    )
    assert empty_payload["deterministic_fallback_plan"]["confidence"] <= 0.2


# ─── 20. do_not_execute 필드 존재 ───────────────────────────────────────


def test_do_not_execute_list_present():
    payload = build_planner_prompt_payload(
        user_request="검사",
        site_map_payload=_site_map_payload_rich(),
    )
    plan = payload["deterministic_fallback_plan"]
    assert "do_not_execute" in plan
    assert isinstance(plan["do_not_execute"], list)
    # universal 안전 정책 토큰이 포함되어 있어야 한다.
    for must in (
        "submit_form", "delete", "payment",
        "credential_submit", "password_fill",
    ):
        assert must in plan["do_not_execute"]
    # expected_json_schema 에도 do_not_execute 필드가 존재.
    assert "do_not_execute" in payload["expected_json_schema"]


# ─── 추가 안정성 검사 ─────────────────────────────────────────────────────


def test_user_request_truncation():
    payload = build_planner_prompt_payload(
        user_request="X" * 5000,
        site_map_payload=_site_map_payload_rich(),
    )
    assert len(payload["user_request"]) <= 2000


# ─── getter helpers: default_available_actions / default_tenant_policy ──


def test_default_available_actions_getter_returns_nonempty_list():
    actions = default_available_actions()
    assert isinstance(actions, list)
    assert len(actions) > 0
    for item in actions:
        assert isinstance(item, dict)
        assert "name" in item


def test_default_available_actions_getter_does_not_mutate_source():
    snapshot = tuple(dict(a) for a in DEFAULT_AVAILABLE_ACTIONS)
    actions = default_available_actions()
    actions.append({"name": "mutated_action"})
    actions[0]["name"] = "MUTATED"
    # 원본 상수 (tuple 자체) 와 내부 dict 내용 모두 그대로여야 한다.
    assert len(DEFAULT_AVAILABLE_ACTIONS) == len(snapshot)
    for original, saved in zip(DEFAULT_AVAILABLE_ACTIONS, snapshot):
        assert original == saved


def test_default_tenant_policy_getter_forbids_auto_execute():
    policy = default_tenant_policy()
    assert isinstance(policy, dict)
    assert policy.get("allow_auto_execute") is False


def test_default_tenant_policy_getter_does_not_mutate_source():
    snapshot = dict(DEFAULT_TENANT_POLICY)
    policy = default_tenant_policy()
    policy["allow_auto_execute"] = True
    policy["new_key"] = "mutated"
    # 원본 상수의 top-level 키/값은 변하지 않아야 한다.
    assert DEFAULT_TENANT_POLICY.get("allow_auto_execute") is False
    assert "new_key" not in DEFAULT_TENANT_POLICY
    assert DEFAULT_TENANT_POLICY == snapshot


def test_build_planner_prompt_payload_unchanged_after_getter_addition():
    # getter 추가가 기존 build_planner_prompt_payload 동작을 바꾸지 않는지.
    payload = build_planner_prompt_payload(
        user_request="검사",
        site_map_payload=_site_map_payload_rich(),
    )
    assert payload["ok"] is True
    assert payload["planning_mode"] == "plan_only"
    assert payload["tenant_policy"]["allow_auto_execute"] is False
    names = {a["name"] for a in payload["available_actions"]}
    for must in (
        "web_open_url_readonly",
        "web_analyze_html",
        "web_build_site_map_prompt",
        "web_click_guarded",
        "web_type_guarded",
        "web_select_guarded",
        "web_scroll_guarded",
        "scan_file_tree",
    ):
        assert must in names


def test_danger_keyword_in_user_request_does_not_escape_into_steps():
    payload = build_planner_prompt_payload(
        user_request="저장 제출 삭제",
        site_map_payload=_site_map_payload_rich(),
    )
    for step in payload["deterministic_fallback_plan"]["steps"]:
        text = (step.get("target") or {}).get("text") or ""
        for kw in ("저장", "제출", "삭제"):
            assert kw not in text, (
                f"danger keyword {kw} leaked into step target text"
            )
