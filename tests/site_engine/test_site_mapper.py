"""core.agent_runtime.browser.site_mapper 검증 (Stage 4 preparation).

본 테스트는 합성된 page_observation dict 만 사용한다.
  - 실제 웹사이트 접속 금지.
  - 실제 GPT / OpenAI API 호출 금지.
  - 실제 브라우저/네트워크 호출 금지.

모든 테스트는 `build_site_map_prompt_payload` 가 deterministic 하게 payload
dict 를 만드는지, 민감정보가 차단되는지, 특정 도메인 키워드가 엔진 기본값에
하드코딩되어 있지 않은지 검증한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ─── 샘플 fixture ─────────────────────────────────────────────────────────


def _sample_table_observation() -> dict:
    """table / list 위주의 페이지 관찰 결과."""
    return {
        "url": "https://example.com/",
        "current_url": "https://example.com/list",
        "title": "Sample List View",
        "login_required_hint": False,
        "modal_candidates": [],
        "page_structure": {
            "page_title": "Sample List View",
            "links": [
                {"text": "목록", "href": "/list", "risk_hint": "safe_read", "keyword_score": 0},
                {"text": "상세", "href": "/detail/1", "risk_hint": "safe_read", "keyword_score": 0},
                {"text": "조회", "href": "/query", "risk_hint": "safe_read", "keyword_score": 0},
                {"text": "삭제", "href": "/admin/delete?id=1", "risk_hint": "danger_write", "keyword_score": 0},
            ],
            "buttons": [
                {"text": "검색", "type": "button", "risk_level": "safe_read", "reason": "keyword:검색"},
                {"text": "저장", "type": "submit", "risk_level": "danger_write", "reason": "keyword:저장"},
                {"text": "제출", "type": "submit", "risk_level": "danger_write", "reason": "type:submit"},
                {"text": "삭제", "type": "button", "risk_level": "danger_write", "reason": "keyword:삭제"},
            ],
            "forms": [],
            "inputs": [],
            "tables": [
                {"headers": ["번호", "상태"], "row_count": 5, "column_count": 2},
                {"headers": ["코드", "이름"], "row_count": 3, "column_count": 2},
            ],
        },
    }


def _sample_form_observation(with_password: bool = True) -> dict:
    """form / input 위주 페이지 관찰 결과."""
    inputs = [
        {"name": "q", "type": "text", "placeholder": "검색어", "label": "검색어"},
        {"name": "category", "type": "text", "placeholder": "", "label": ""},
        {"name": "memo", "type": "text", "placeholder": "", "label": ""},
    ]
    if with_password:
        inputs.append(
            {"name": "password", "type": "password", "placeholder": "", "label": ""},
        )
    inputs.append(
        {"name": "csrf_token", "type": "hidden", "placeholder": "", "label": ""},
    )
    return {
        "url": "https://example.com/login",
        "current_url": "https://example.com/login",
        "title": "Sign in",
        "login_required_hint": with_password,
        "modal_candidates": [],
        "page_structure": {
            "page_title": "Sign in",
            "links": [],
            "buttons": [
                {"text": "Sign in", "type": "submit", "risk_level": "danger_write", "reason": "type:submit"},
            ],
            "forms": [
                {
                    "method": "post",
                    "action": "/auth/login",
                    "field_count": len(inputs),
                    "has_password": with_password,
                    "has_hidden": True,
                    "risk_level": "danger_write",
                }
            ],
            "inputs": inputs,
            "tables": [],
        },
    }


def _sample_menu_observation() -> dict:
    """links 가 많은 menu-like 관찰 결과."""
    return {
        "url": "https://example.com/home",
        "current_url": "https://example.com/home",
        "title": "Main Menu",
        "login_required_hint": False,
        "modal_candidates": [],
        "page_structure": {
            "page_title": "Main Menu",
            "links": [
                {"text": f"메뉴 {i}", "href": f"/menu/{i}", "risk_hint": "safe_read", "keyword_score": 0}
                for i in range(1, 9)
            ]
            + [
                {"text": "조회", "href": "/query", "risk_hint": "safe_read", "keyword_score": 0},
                {"text": "상세", "href": "/detail/1", "risk_hint": "safe_read", "keyword_score": 0},
            ],
            "buttons": [],
            "forms": [],
            "inputs": [],
            "tables": [],
        },
    }


def _sample_domain_profile() -> dict:
    """테스트용 합성 도메인 프로파일. (production 엔진은 이런 값을 절대 하드코딩하지 않음)"""
    return {
        "profile_key": "sample_domain",
        "description": "테스트용 합성 업무 도메인",
        "keywords": ["샘플업무", "샘플관리"],
        "preferred_navigation_terms": ["샘플관리"],
        "danger_terms": ["샘플삭제"],
        "task_candidates": [
            {
                "task": "sample_task",
                "keywords": ["샘플업무"],
                "description": "샘플 업무 진입",
            }
        ],
    }


# ─── 1. domain_profile 없이도 generic page_role 후보 생성 ────────────────


def test_generic_page_role_candidates_without_profile() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    payload = build_site_map_prompt_payload(_sample_table_observation())
    assert payload["ok"] is True
    roles = payload["heuristic_candidates"]["page_role_candidates"]
    role_names = {r["role"] for r in roles}
    assert role_names  # at least one role
    assert "table_page" in role_names


# ─── 2. table 구조만으로 table_page/list_page 후보 생성 ──────────────────


def test_table_observation_produces_table_and_list_roles() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    payload = build_site_map_prompt_payload(_sample_table_observation())
    role_names = {r["role"] for r in payload["heuristic_candidates"]["page_role_candidates"]}
    assert "table_page" in role_names
    assert "list_page" in role_names


# ─── 3. form/input 구조만으로 form_page/search_page 후보 생성 ─────────────


def test_form_observation_produces_form_and_search_roles() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    obs = _sample_form_observation(with_password=False)
    obs["page_structure"]["buttons"].append(
        {"text": "검색", "type": "button", "risk_level": "safe_read", "reason": "keyword:검색"},
    )
    payload = build_site_map_prompt_payload(obs)
    role_names = {r["role"] for r in payload["heuristic_candidates"]["page_role_candidates"]}
    assert "form_page" in role_names
    assert "search_page" in role_names


# ─── 4. login_required_hint/password input으로 login_page 후보 ───────────


def test_login_page_role_detected() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    payload = build_site_map_prompt_payload(_sample_form_observation(True))
    roles = payload["heuristic_candidates"]["page_role_candidates"]
    top = roles[0]
    assert top["role"] == "login_page"
    assert top["score"] > 0.5


# ─── 5. domain_profile 이 있을 때만 profile keyword 매칭 ─────────────────


def test_domain_profile_matches_populate_only_when_profile_given() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    obs = _sample_table_observation()
    obs["title"] = "샘플업무 진입"
    obs["page_structure"]["page_title"] = "샘플업무 진입"

    no_profile = build_site_map_prompt_payload(obs)
    assert no_profile["heuristic_candidates"]["domain_profile_matches"] == []

    with_profile = build_site_map_prompt_payload(
        obs,
        domain_profile=_sample_domain_profile(),
    )
    matches = with_profile["heuristic_candidates"]["domain_profile_matches"]
    assert len(matches) == 1
    assert matches[0]["profile_key"] == "sample_domain"
    assert any("샘플업무" in r for r in matches[0]["reasons"])


# ─── 6. domain_profile 없으면 특정 업무 task 를 만들지 않음 ──────────────


def test_no_specific_tasks_without_domain_profile() -> None:
    from core.agent_runtime.browser.site_mapper import (
        GENERIC_TASK_POOL,
        build_site_map_prompt_payload,
    )

    payload = build_site_map_prompt_payload(_sample_table_observation())
    task_names = {c["task"] for c in payload["heuristic_candidates"]["task_candidates"]}
    allowed = set(GENERIC_TASK_POOL)
    unknown = task_names - allowed
    assert not unknown, f"엔진이 도메인 없이 특정 업무 task 를 만들었다: {unknown}"


def test_domain_profile_task_candidate_picked_up() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    obs = _sample_table_observation()
    obs["title"] = "샘플업무 진입"
    obs["page_structure"]["page_title"] = "샘플업무 진입"
    payload = build_site_map_prompt_payload(
        obs,
        domain_profile=_sample_domain_profile(),
    )
    names = {c["task"] for c in payload["heuristic_candidates"]["task_candidates"]}
    assert "sample_task" in names


# ─── 7. user_goal 이 있을 때 task 후보 점수에 반영 ──────────────────────


def test_user_goal_boosts_task_confidence() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    base = build_site_map_prompt_payload(_sample_table_observation())
    boosted = build_site_map_prompt_payload(
        _sample_table_observation(),
        user_goal="table 확인",
    )

    def _conf(payload: dict, task_name: str) -> float:
        for c in payload["heuristic_candidates"]["task_candidates"]:
            if c["task"] == task_name:
                return float(c["confidence"])
        return -1.0

    # 같은 일반 task 가 존재해야 하고, boosted 가 더 높은 confidence 여야 함.
    assert _conf(boosted, "inspect_table") >= _conf(base, "inspect_table")
    assert _conf(boosted, "inspect_table") > 0.0
    # goal 이 있으면 ask_user_to_identify_goal 이 제거됨
    boosted_names = {c["task"] for c in boosted["heuristic_candidates"]["task_candidates"]}
    assert "ask_user_to_identify_goal" not in boosted_names


# ─── 8. keyword_hints 가 있을 때 safe 후보 점수에 반영 ───────────────────


def test_keyword_hints_boost_safe_navigation_score() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    obs = _sample_table_observation()
    obs["page_structure"]["links"].append(
        {"text": "샘플관리", "href": "/sample", "risk_hint": "safe_read", "keyword_score": 0},
    )

    no_hint = build_site_map_prompt_payload(obs)
    with_hint = build_site_map_prompt_payload(obs, keyword_hints=["샘플관리"])

    def _score(payload: dict, text: str) -> int:
        for c in payload["heuristic_candidates"]["safe_navigation_candidates"]:
            if c["text"] == text:
                return int(c.get("score", 0))
        return -1

    assert _score(with_hint, "샘플관리") > _score(no_hint, "샘플관리")


# ─── 9. 저장/제출/삭제 버튼은 danger_elements 로 분류 ────────────────────


def test_write_buttons_collected_as_danger_elements() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    payload = build_site_map_prompt_payload(_sample_table_observation())
    texts = {e["text"] for e in payload["heuristic_candidates"]["danger_elements"]}
    assert {"저장", "제출", "삭제"}.issubset(texts)


# ─── 10. 조회/검색/목록/상세 링크는 safe_navigation_candidates ───────────


def test_safe_read_items_collected_as_safe_navigation() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    payload = build_site_map_prompt_payload(_sample_table_observation())
    safe = payload["heuristic_candidates"]["safe_navigation_candidates"]
    safe_texts = {c["text"] for c in safe}
    assert {"조회", "목록", "상세", "검색"}.issubset(safe_texts)


# ─── 11. danger 요소가 safe_next_actions 에 들어가지 않음 ────────────────


def test_danger_items_not_in_safe_navigation() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    payload = build_site_map_prompt_payload(_sample_table_observation())
    safe_texts = {c["text"] for c in payload["heuristic_candidates"]["safe_navigation_candidates"]}
    for bad in ("저장", "제출", "삭제"):
        assert bad not in safe_texts


# ─── 12. password/hidden/csrf/token/cookie 값 redaction ─────────────────


def test_sensitive_values_redacted_in_payload() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    obs = _sample_form_observation(with_password=True)
    # 일부러 raw value / 민감 href 주입 (실제 web_reader 는 주지 않지만 방어 검증)
    obs["page_structure"]["links"] = [
        {"text": "check", "href": "/x?token=VERY_SECRET_TOKEN_1", "risk_hint": "safe_read"},
        {"text": "session", "href": "/x?session_id=SESSION_XYZ_2", "risk_hint": "safe_read"},
    ]
    obs["page_structure"]["inputs"] = obs["page_structure"]["inputs"] + [
        {"name": "authorization", "type": "text", "placeholder": "bearer ey.REAL_JWT_3"},
        {"name": "cookie", "type": "text", "placeholder": ""},
    ]

    payload = build_site_map_prompt_payload(obs)
    serialized = json.dumps(payload, ensure_ascii=False)
    for leaked in (
        "VERY_SECRET_TOKEN_1",
        "SESSION_XYZ_2",
        "REAL_JWT_3",
    ):
        assert leaked not in serialized, f"민감값 누출: {leaked}"

    # password / hidden input 은 value 키 자체가 없어야 함.
    for inp in payload["sanitized_observation"]["inputs"]:
        assert "value" not in inp


# ─── 13. raw HTML 이 payload 에 포함되지 않음 ───────────────────────────


def test_raw_html_not_in_payload() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    obs = _sample_table_observation()
    obs["html"] = "<html>UNIQUE_RAW_HTML_MARKER_ABC</html>"
    obs["page_structure"]["raw_html"] = "<div>UNIQUE_RAW_HTML_MARKER_XYZ</div>"

    payload = build_site_map_prompt_payload(obs)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "UNIQUE_RAW_HTML_MARKER_ABC" not in serialized
    assert "UNIQUE_RAW_HTML_MARKER_XYZ" not in serialized


# ─── 14. expected_json_schema 필수 필드 존재 ────────────────────────────


def test_expected_json_schema_has_required_fields() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    payload = build_site_map_prompt_payload(_sample_table_observation())
    schema = payload["expected_json_schema"]
    for key in (
        "site_type",
        "confidence",
        "page_role",
        "candidate_tasks",
        "safe_next_actions",
        "danger_elements",
        "questions_for_user",
        "do_not_execute",
    ):
        assert key in schema, f"schema missing required field: {key}"
    # page_role 에 필수 역할 값이 모두 기술되어 있음.
    for role in (
        "login_page",
        "form_page",
        "table_page",
        "menu_page",
        "unknown",
    ):
        assert role in schema["page_role"]


# ─── 15. gpt_instruction 에 저장/제출/삭제 금지 지침 포함 ────────────────


def test_gpt_instruction_forbids_write_actions() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    payload = build_site_map_prompt_payload(_sample_table_observation())
    instr = payload["gpt_instruction"]
    for tok in ("저장", "제출", "삭제"):
        assert tok in instr, f"instruction missing block for {tok}"
    for en in ("Save", "Submit", "Delete"):
        assert en in instr, f"instruction missing block for {en}"


# ─── 16. max_items 제한 적용 ─────────────────────────────────────────────


def test_max_items_limit_applied() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    many_links = [
        {"text": f"조회 {i}", "href": f"/q/{i}", "risk_hint": "safe_read", "keyword_score": 0} for i in range(200)
    ]
    obs = {
        "url": "https://example.com/",
        "current_url": "https://example.com/",
        "title": "many",
        "page_structure": {
            "page_title": "many",
            "links": many_links,
            "buttons": [],
            "forms": [],
            "inputs": [],
            "tables": [],
        },
    }
    payload = build_site_map_prompt_payload(obs, max_items=10)
    assert len(payload["sanitized_observation"]["links"]) == 10
    assert len(payload["heuristic_candidates"]["safe_navigation_candidates"]) <= 10


# ─── 17. 빈 observation 도 ok=true 또는 안전한 warning 으로 처리 ─────────


def test_empty_observation_returns_ok_with_warning() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    payload = build_site_map_prompt_payload({})
    assert payload["ok"] is True
    assert isinstance(payload["warnings"], list)
    assert "observation_empty" in payload["warnings"]
    # empty 에서도 필수 필드 존재.
    assert payload["expected_json_schema"]
    assert payload["heuristic_candidates"]["safe_navigation_candidates"] == []
    assert payload["heuristic_candidates"]["danger_elements"] == []


def test_non_dict_observation_returns_ok_with_warning() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    payload = build_site_map_prompt_payload("not-a-dict")  # type: ignore[arg-type]
    assert payload["ok"] is True
    assert "page_observation_not_dict" in payload["warnings"]


# ─── 18. web_build_site_map_prompt action 통합 ──────────────────────────


def test_action_web_build_site_map_prompt_returns_ok() -> None:
    from core.agent_runtime.connection.actions import execute_action

    result = execute_action(
        "web_build_site_map_prompt",
        {
            "page_observation": _sample_table_observation(),
            "user_goal": "table 조회",
            "max_items": 50,
        },
    )
    assert result.success is True
    payload = result.data["site_map_prompt_payload"]
    assert payload["ok"] is True
    assert payload["user_goal"] == "table 조회"
    assert "roles=" in result.summary


def test_action_web_build_site_map_prompt_missing_observation() -> None:
    from core.agent_runtime.connection.actions import execute_action

    result = execute_action("web_build_site_map_prompt", {})
    assert result.success is False
    assert result.error_code == "MISSING_PAGE_OBSERVATION"


def test_action_web_build_site_map_prompt_invalid_goal_type() -> None:
    from core.agent_runtime.connection.actions import execute_action

    result = execute_action(
        "web_build_site_map_prompt",
        {
            "page_observation": _sample_table_observation(),
            "user_goal": 12345,
        },
    )
    assert result.success is False
    assert result.error_code == "INVALID_USER_GOAL"


# ─── 19. production site_mapper.py 에 특정 도메인 키워드 하드코딩 금지 ────


def test_production_site_mapper_has_no_domain_keywords() -> None:
    import core.agent_runtime.browser.site_mapper as sm

    src_path = Path(sm.__file__)
    text = src_path.read_text(encoding="utf-8")

    # grep 검사와 동일한 대안목록. 테스트 자신은 아래 목록을 문자열로 가진다
    # (production 코드가 아니므로 허용).
    forbidden_patterns = [
        "기성",
        "청구",
        "정산",
        "계약",
        "현장",
        "배민",
        "카페",
        "유튜브",
        "YouTube",
        "youtube",
        "API 신청",
        "OAuth",
        "리뷰",
        "댓글",
    ]
    hits = [p for p in forbidden_patterns if p in text]
    assert forbidden_patterns, "forbidden_patterns 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert not hits, f"production site_mapper.py 에 특정 도메인 키워드가 하드코딩됨: {hits}"


def test_production_site_mapper_has_no_network_or_llm_calls() -> None:
    import core.agent_runtime.browser.site_mapper as sm

    src_path = Path(sm.__file__)
    text = src_path.read_text(encoding="utf-8")
    banned = [
        "import openai",
        "from openai",
        "requests.post",
        "requests.get",
        "httpx.post",
        "httpx.get",
        "urllib.request",
        "urlopen",
        "chat.completions",
        "responses.create",
        ".click(",
        ".fill(",
        ".type(",
    ]
    hits = [p for p in banned if p in text]
    assert not hits, f"production site_mapper.py 에 금지된 호출 패턴이 포함됨: {hits}"


# ─── 20. universal danger/safe terms 존재 확인 ───────────────────────────


def test_universal_terms_present_and_generic() -> None:
    from core.agent_runtime.browser.site_mapper import (
        UNIVERSAL_DANGER_WRITE_TERMS,
        UNIVERSAL_SAFE_READ_TERMS,
    )

    # universal danger 는 안전 정책 수준으로 모두 포함되어야 함.
    for t in ("저장", "제출", "삭제", "save", "submit", "delete"):
        assert t in UNIVERSAL_DANGER_WRITE_TERMS, f"missing danger term {t!r}"
    for t in ("조회", "검색", "목록", "상세", "search", "view", "list"):
        assert t in UNIVERSAL_SAFE_READ_TERMS, f"missing safe term {t!r}"

    # universal 목록에 특정 업무 단어가 없는지 (= 안전 정책 범주만) 확인.
    banned_in_engine_defaults = [
        "기성",
        "청구",
        "정산",
        "계약",
        "배민",
        "카페",
        "유튜브",
        "YouTube",
        "리뷰",
        "댓글",
    ]
    combined = UNIVERSAL_SAFE_READ_TERMS + UNIVERSAL_DANGER_WRITE_TERMS
    for w in banned_in_engine_defaults:
        assert w not in combined, f"universal term 목록이 도메인 키워드로 오염됨: {w!r}"


# ─── 추가: GPT instruction 문자열이 비-LLM 결정적으로 생성되는지 ─────────


def test_gpt_instruction_is_deterministic_string() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    a = build_site_map_prompt_payload(_sample_menu_observation())
    b = build_site_map_prompt_payload(_sample_menu_observation())
    assert a["gpt_instruction"] == b["gpt_instruction"]
    assert isinstance(a["gpt_instruction"], str)
    assert len(a["gpt_instruction"]) > 100


# ─── 추가: domain_profile.danger_terms 가 danger 분류에 반영 ─────────────


def test_domain_profile_danger_terms_extend_classification() -> None:
    from core.agent_runtime.browser.site_mapper import build_site_map_prompt_payload

    obs = {
        "url": "https://example.com/",
        "current_url": "https://example.com/",
        "title": "x",
        "page_structure": {
            "page_title": "x",
            "links": [
                {"text": "샘플삭제", "href": "/x", "risk_hint": "safe_read", "keyword_score": 0},
            ],
            "buttons": [],
            "forms": [],
            "inputs": [],
            "tables": [],
        },
    }
    payload = build_site_map_prompt_payload(
        obs,
        domain_profile=_sample_domain_profile(),
    )
    danger_texts = {e["text"] for e in payload["heuristic_candidates"]["danger_elements"]}
    safe_texts = {c["text"] for c in payload["heuristic_candidates"]["safe_navigation_candidates"]}
    assert "샘플삭제" in danger_texts
    assert "샘플삭제" not in safe_texts
