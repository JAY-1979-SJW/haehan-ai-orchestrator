"""GPT Planner payload builder (Stage 1, plan_only).

본 모듈은 사용자의 자연어 요청과 ``site_mapper`` 가 만든 범용 site map
payload 를 받아, 이후 LLM 에게 넘길 수 있는 "plan_only planner payload"
를 deterministic 하게 만든다.

엄격한 경계
  - 실제 GPT / OpenAI API 를 호출하지 않는다 (SDK 임포트조차 없음).
  - HTTP/네트워크 라이브러리를 사용하지 않는다.
  - 브라우저 또는 로컬 action 을 실행하지 않는다.
  - 특정 업무/도메인 키워드를 엔진 기본값으로 하드코딩하지 않는다.
  - 민감 정보 (쿠키/세션/토큰/비밀번호/hidden value/전체 경로 등) 를
    payload 에 포함시키지 않는다.

이 모듈이 만드는 payload 는 "실행용" 이 아니라 "계획 전용(plan_only)"
이며, 모든 step 은 ``auto_execute=False`` / ``requires_approval=True``
로 표시된다. 실제 실행은 별도의 guarded 레이어에서만 수행되어야 한다.
"""
from __future__ import annotations

from typing import Any


# ─── 기본 available_actions (범용 action 카탈로그) ──────────────────────

DEFAULT_AVAILABLE_ACTIONS: tuple[dict[str, Any], ...] = (
    {
        "name": "web_open_url_readonly",
        "category": "browser_read",
        "risk": "low",
        "requires_approval_when": ["medium", "high", "critical"],
        "auto_execute_allowed": False,
    },
    {
        "name": "web_analyze_html",
        "category": "analysis",
        "risk": "low",
        "requires_approval_when": ["high", "critical"],
        "auto_execute_allowed": False,
    },
    {
        "name": "web_build_site_map_prompt",
        "category": "analysis",
        "risk": "low",
        "requires_approval_when": ["high", "critical"],
        "auto_execute_allowed": False,
    },
    {
        "name": "web_click_guarded",
        "category": "browser_write_guarded",
        "risk": "low_to_high",
        "requires_approval_when": ["danger_write", "medium", "high", "critical"],
        "auto_execute_allowed": False,
    },
    {
        "name": "web_type_guarded",
        "category": "browser_write_guarded",
        "risk": "low_to_high",
        "requires_approval_when": ["danger_write", "medium", "high", "critical"],
        "auto_execute_allowed": False,
    },
    {
        "name": "web_select_guarded",
        "category": "browser_write_guarded",
        "risk": "low_to_high",
        "requires_approval_when": ["danger_write", "medium", "high", "critical"],
        "auto_execute_allowed": False,
    },
    {
        "name": "web_scroll_guarded",
        "category": "browser_read",
        "risk": "low",
        "requires_approval_when": ["high", "critical"],
        "auto_execute_allowed": False,
    },
    {
        "name": "scan_file_tree",
        "category": "filesystem_readonly",
        "risk": "low",
        "requires_approval_when": ["high", "critical"],
        "auto_execute_allowed": False,
    },
)


# ─── 기본 tenant_policy (모든 실행을 막는 planning-only 기본값) ─────────

DEFAULT_TENANT_POLICY: dict[str, Any] = {
    "allow_auto_execute": False,
    "allow_external_network": False,
    "allow_click": False,
    "allow_type": False,
    "allow_submit": False,
    "allow_delete": False,
    "allow_download": False,
    "allow_upload": False,
    "require_approval_for": ["medium", "high", "critical"],
    "blocked_actions": [
        "submit_form", "delete", "payment",
        "credential_submit", "password_fill",
    ],
}


def default_available_actions() -> list[dict]:
    return [dict(item) for item in DEFAULT_AVAILABLE_ACTIONS]


def default_tenant_policy() -> dict:
    return dict(DEFAULT_TENANT_POLICY)


# ─── 민감 key/value 토큰 테이블 ──────────────────────────────────────────

_SENSITIVE_NAME_TOKENS: frozenset[str] = frozenset({
    "password", "passwd", "pwd",
    "cookie", "set-cookie",
    "authorization", "bearer",
    "session", "sessionid", "session_id",
    "token", "access_token", "refresh_token", "id_token",
    "csrf", "xsrf", "csrf_token", "xsrf_token",
    "api_key", "apikey", "api-key",
    "device_token", "devicetoken",
})

_ALWAYS_DROP_KEYS: frozenset[str] = frozenset({
    "html", "raw_html", "page_html", "body_html",
    "outer_html", "inner_html",
    "screenshot_path", "screenshot_file",
    "absolute_path", "full_path", "local_path", "file_path",
    "device_token", "agent_token", "session_token",
    "cookies", "cookie",
    "authorization", "auth_header",
})

_EXISTENCE_OK_KEYS: frozenset[str] = frozenset({
    "has_password", "has_hidden", "login_required_hint",
    "has_modal_candidates", "needs_user_confirmation",
    "requires_approval", "auto_execute",
})

_REDACTED = "<redacted>"

# plan_only 모드에서도 자동 제안 금지 action 들. domain 힌트 없이
# universal 하게 쓰여야 하는 안전 정책 토큰.
_NEVER_AUTO_PLAN_TOKENS: frozenset[str] = frozenset({
    "submit_form", "form_submit",
    "delete", "delete_account", "remove",
    "approve", "payment",
    "credential_submit", "password_fill",
    "upload_file", "upload",
    "download_file", "download",
    "logout", "signout",
})

_MAX_USER_REQUEST_LEN = 2000
_MAX_STEPS_CAP = 25


# ─── 공개 API ─────────────────────────────────────────────────────────────


def build_planner_prompt_payload(
    user_request: str,
    site_map_payload: dict | None = None,
    available_actions: list[dict] | None = None,
    tenant_policy: dict | None = None,
    max_steps: int = 10,
) -> dict:
    """plan_only GPT planner payload 를 deterministic 하게 구성.

    실제 GPT/OpenAI API 를 호출하지 않는다. 네트워크/브라우저/로컬 action
    도 실행하지 않는다. 호출자가 나중에 LLM 에 넘길 planner 지시문과
    기대하는 JSON schema, deterministic fallback plan 만 묶어서 반환한다.
    """
    warnings: list[str] = []
    normalized_request = _normalize_user_request(user_request)
    if not normalized_request:
        warnings.append("user_request_missing")

    actions = _normalize_available_actions(available_actions)
    policy = _normalize_tenant_policy(tenant_policy)
    steps_cap = _normalize_max_steps(max_steps)

    site_payload = _sanitize_site_payload(site_map_payload)
    if site_map_payload and not site_payload:
        warnings.append("site_map_payload_dropped_non_dict")

    site_context_summary = _build_site_context_summary(site_payload)
    if site_payload is None:
        warnings.append("site_map_payload_missing")

    fallback_plan = build_deterministic_fallback_plan(
        user_request=normalized_request,
        site_map_payload=site_payload,
        available_actions=actions,
        tenant_policy=policy,
        max_steps=steps_cap,
    )

    payload = {
        "ok": True,
        "purpose": "gpt_planner_payload",
        "user_request": normalized_request,
        "planning_mode": "plan_only",
        "available_actions": list(actions),
        "tenant_policy": dict(policy),
        "site_context_summary": site_context_summary,
        "planner_instruction": _build_planner_instruction(steps_cap),
        "expected_json_schema": _build_expected_json_schema(),
        "deterministic_fallback_plan": fallback_plan,
        "warnings": warnings,
        "max_steps": steps_cap,
    }
    return sanitize_planner_payload(payload)


def build_deterministic_fallback_plan(
    user_request: str,
    site_map_payload: dict | None,
    available_actions: list[dict],
    tenant_policy: dict,
    max_steps: int = 10,
) -> dict:
    """GPT 호출 이전에도 사용할 수 있는 안전한 plan_only fallback plan.

    - 모든 step 은 ``auto_execute=False`` / ``requires_approval=True``.
    - 위험 요소 (danger_elements / blocked_actions) 는 절대 steps 로
      들어가지 않고 ``blocked_or_deferred`` 에 분리된다.
    - site_map_payload 가 없거나 user_request 가 비어있으면 질문으로만
      응답하고 실행 후보는 최소화한다.
    """
    steps_cap = _normalize_max_steps(max_steps)
    policy = _normalize_tenant_policy(tenant_policy)

    questions: list[str] = []
    steps: list[dict] = []
    blocked: list[dict] = []
    safety_notes: list[str] = [
        "plan_only mode: no step is executed automatically.",
        "approval is required before any guarded browser action runs.",
        "sensitive values (password/cookie/token/api_key) must never be requested.",
    ]

    if not user_request:
        questions.append(
            "어떤 작업을 원하시는지 한국어로 구체적으로 알려주세요."
        )

    site_map = site_map_payload if isinstance(site_map_payload, dict) else None

    if site_map is None:
        questions.append(
            "대상 사이트 URL 또는 현재 페이지 관찰 정보가 필요합니다."
        )
        steps.append(_build_step(
            step_id=f"S{len(steps) + 1}",
            action="web_open_url_readonly",
            description=(
                "대상 사이트의 read-only 분석 준비. 실제 URL 은 사용자가 "
                "확인/승인한 뒤에만 주어진다."
            ),
            target={"url": None, "selector": None, "text": None},
            risk="low",
            reason="no_site_context_yet",
        ))
    else:
        summary = _build_site_context_summary(site_map)
        if summary.get("login_required_hint"):
            questions.append(
                "사이트가 로그인을 필요로 합니다. 자동화가 아닌 사용자 "
                "직접 로그인이 필요한지 확인해 주세요."
            )
        if summary.get("has_modal"):
            questions.append(
                "현재 모달이 열려 있습니다. 닫기(close) / 확인(confirm) "
                "중 어떤 동작을 원하시는지 알려주세요."
            )

        current_url_host = summary.get("host") or ""
        if current_url_host:
            steps.append(_build_step(
                step_id=f"S{len(steps) + 1}",
                action="web_open_url_readonly",
                description=(
                    f"대상 호스트({current_url_host}) 의 현재 페이지를 "
                    "read-only 로 열어 관찰만 수행한다."
                ),
                target={"url": None, "selector": None, "text": None},
                risk="low",
                reason="verify_current_page_readonly",
            ))

        heuristics = site_map.get("heuristic_candidates") or {}
        safe_candidates = heuristics.get("safe_navigation_candidates") or []
        danger_elements = heuristics.get("danger_elements") or []

        for cand in safe_candidates:
            if len(steps) >= steps_cap:
                break
            if not isinstance(cand, dict):
                continue
            text = _clip(cand.get("text"), 200)
            kind = _clip(cand.get("kind"), 32) or "link"
            if not text:
                continue
            if _looks_like_never_auto(text):
                # 안전 후보로 분류되었더라도 universal 안전 정책상
                # 절대 자동 제안하지 않는다.
                blocked.append({
                    "action": "click_on_danger_text_candidate",
                    "risk": "high",
                    "reason": f"text_matches_universal_danger:{text}",
                })
                continue
            step_action = _pick_guarded_action_for_kind(kind)
            steps.append(_build_step(
                step_id=f"S{len(steps) + 1}",
                action=step_action,
                description=(
                    f"safe_navigation 후보({kind}): '{text}' 를 사용자 "
                    "승인 뒤 inspect 할 수 있다."
                ),
                target={"url": None, "selector": None, "text": text},
                risk="low",
                reason="safe_navigation_candidate",
            ))

        for dg in danger_elements:
            if not isinstance(dg, dict):
                continue
            text = _clip(dg.get("text"), 200)
            blocked.append({
                "action": f"{_clip(dg.get('kind'), 32) or 'element'}:{text}",
                "risk": _clip(dg.get("risk"), 16) or "high",
                "reason": _clip(dg.get("reason"), 200) or "danger_write",
            })

    # tenant_policy.blocked_actions 는 항상 blocked_or_deferred 에 반영.
    for name in policy.get("blocked_actions") or []:
        if not isinstance(name, str) or not name:
            continue
        blocked.append({
            "action": name,
            "risk": "critical",
            "reason": "tenant_policy_blocked",
        })

    # confidence 는 과도하게 높지 않도록 상한 유지.
    if not user_request and site_map is None:
        confidence = 0.1
    elif site_map is None:
        confidence = 0.2
    elif not user_request:
        confidence = 0.3
    else:
        confidence = 0.45

    steps = steps[:steps_cap]

    plan = {
        "goal": user_request or "",
        "confidence": confidence,
        "mode": "plan_only",
        "needs_user_confirmation": True,
        "questions_for_user": questions,
        "steps": steps,
        "blocked_or_deferred": blocked,
        "safety_notes": safety_notes,
        "do_not_execute": sorted(_NEVER_AUTO_PLAN_TOKENS),
    }
    return plan


def sanitize_planner_payload(payload: Any) -> Any:
    """payload 내부에서 민감 key/값을 재귀적으로 제거/치환.

    허용:
      - ``has_password``, ``has_hidden`` 같은 boolean 존재 여부 플래그.
    차단:
      - raw_html / password / cookie / token / authorization / api_key / csrf
        의 원문 값, 로컬 절대경로, screenshot 경로, device token.
    """
    return _deep_sanitize(payload)


# ─── helpers ──────────────────────────────────────────────────────────────


def _normalize_user_request(req: Any) -> str:
    if not isinstance(req, str):
        return ""
    trimmed = req.strip()
    if not trimmed:
        return ""
    return trimmed[:_MAX_USER_REQUEST_LEN]


def _normalize_available_actions(actions: Any) -> list[dict]:
    if actions is None:
        return [dict(a) for a in DEFAULT_AVAILABLE_ACTIONS]
    if not isinstance(actions, list):
        return [dict(a) for a in DEFAULT_AVAILABLE_ACTIONS]
    out: list[dict] = []
    for item in actions:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        out.append({
            "name": name[:120],
            "category": _clip(item.get("category"), 64) or "unspecified",
            "risk": _clip(item.get("risk"), 32) or "unknown",
            "requires_approval_when": _clip_str_list(
                item.get("requires_approval_when"), 16, 32,
            ),
            "auto_execute_allowed": bool(item.get("auto_execute_allowed", False)),
        })
    if not out:
        return [dict(a) for a in DEFAULT_AVAILABLE_ACTIONS]
    return out


def _normalize_tenant_policy(policy: Any) -> dict:
    merged = dict(DEFAULT_TENANT_POLICY)
    # 기본값은 항상 안전 쪽. 외부 입력이 더 허용적이어도 default 를
    # 유지할 항목 (auto_execute 등) 이 있으나, 이번 단계에서는 외부
    # override 를 허용하되 결과 payload 의 plan_only / auto_execute=False
    # 보장은 fallback plan 생성 단계에서 강제한다.
    if isinstance(policy, dict):
        for key in (
            "allow_auto_execute", "allow_external_network",
            "allow_click", "allow_type", "allow_submit",
            "allow_delete", "allow_download", "allow_upload",
        ):
            if key in policy:
                merged[key] = bool(policy.get(key))
        if isinstance(policy.get("require_approval_for"), list):
            merged["require_approval_for"] = _clip_str_list(
                policy.get("require_approval_for"), 16, 32,
            ) or list(DEFAULT_TENANT_POLICY["require_approval_for"])
        if isinstance(policy.get("blocked_actions"), list):
            extras = _clip_str_list(policy.get("blocked_actions"), 50, 64)
            union: list[str] = list(DEFAULT_TENANT_POLICY["blocked_actions"])
            for name in extras:
                if name not in union:
                    union.append(name)
            merged["blocked_actions"] = union
    # plan_only 단계에서는 auto_execute 를 무조건 false 로 고정.
    merged["allow_auto_execute"] = False
    return merged


def _normalize_max_steps(value: Any) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 10
    if v <= 0:
        v = 10
    return min(v, _MAX_STEPS_CAP)


def _sanitize_site_payload(payload: Any) -> dict | None:
    if not isinstance(payload, dict):
        return None
    return _deep_sanitize(payload)


def _build_site_context_summary(site_map: dict | None) -> dict:
    if not isinstance(site_map, dict):
        return {
            "title": "",
            "host": "",
            "login_required_hint": False,
            "has_modal": False,
            "page_role_candidates": [],
            "counts": {
                "links": 0, "buttons": 0, "forms": 0,
                "tables": 0, "inputs": 0,
            },
        }
    page_summary = site_map.get("page_summary") or {}
    heuristics = site_map.get("heuristic_candidates") or {}
    role_cands = heuristics.get("page_role_candidates") or []
    top_roles: list[dict] = []
    for r in role_cands[:3]:
        if isinstance(r, dict):
            top_roles.append({
                "role": _clip(r.get("role"), 32) or "unknown",
                "score": float(r.get("score") or 0.0),
            })
    counts = page_summary.get("counts") or {}
    return {
        "title": _clip(page_summary.get("title"), 200),
        "host": _clip(page_summary.get("current_url_host"), 200),
        "login_required_hint": bool(page_summary.get("login_required_hint", False)),
        "has_modal": bool(page_summary.get("has_modal_candidates", False)),
        "page_role_candidates": top_roles,
        "counts": {
            "links": int(counts.get("links") or 0),
            "buttons": int(counts.get("buttons") or 0),
            "forms": int(counts.get("forms") or 0),
            "tables": int(counts.get("tables") or 0),
            "inputs": int(counts.get("inputs") or 0),
        },
    }


def _build_planner_instruction(max_steps: int) -> str:
    return (
        "You are a domain-agnostic planning assistant. The user request is a "
        "natural language task and the site_context_summary describes the "
        "current page as observed by a read-only analyzer.\n"
        "\n"
        "Rules:\n"
        f"1. Mode is plan_only. Every step MUST set auto_execute=false and "
        f"requires_approval=true. Produce at most {max_steps} steps.\n"
        "2. Use ONLY the actions listed in available_actions. Do not invent "
        "new action names.\n"
        "3. If the site is unfamiliar or the request is ambiguous, do NOT "
        "guess. Add clarifying items to questions_for_user and keep "
        "confidence low.\n"
        "4. Never plan write-like behavior automatically. Save / Submit / "
        "Delete / Approve / Payment / Logout / Credential entry and their "
        "Korean equivalents (저장 / 제출 / 등록 / 수정 / 삭제 / 승인 / "
        "전송 / 결제 / 확정 / 마감 / 신청 / 취소 / 로그아웃) must go into "
        "blocked_or_deferred, not steps.\n"
        "5. High or critical risk items are ALWAYS requires_approval=true. "
        "They may only appear as planning hints or in blocked_or_deferred.\n"
        "6. Never request, infer, or echo passwords, session identifiers, "
        "cookies, CSRF tokens, hidden form values, bearer tokens, or API "
        "keys. Treat them as entirely out of scope.\n"
        "7. Respond strictly in the JSON shape defined by "
        "expected_json_schema. Do not add fields outside that schema.\n"
        "8. Populate do_not_execute with any behavior the plan explicitly "
        "forbids (e.g. submit_form, delete, payment, credential_submit, "
        "password_fill).\n"
    )


def _build_expected_json_schema() -> dict:
    return {
        "goal": "string",
        "confidence": 0.0,
        "mode": "plan_only",
        "needs_user_confirmation": True,
        "questions_for_user": [],
        "steps": [
            {
                "step_id": "S1",
                "action": "web_open_url_readonly",
                "description": "string",
                "target": {
                    "url": "string|null",
                    "selector": "string|null",
                    "text": "string|null",
                },
                "risk": "low|medium|high|critical",
                "requires_approval": True,
                "auto_execute": False,
                "reason": "string",
            }
        ],
        "blocked_or_deferred": [
            {
                "action": "string",
                "risk": "high|critical",
                "reason": "string",
            }
        ],
        "safety_notes": [],
        "do_not_execute": [],
    }


def _build_step(
    step_id: str,
    action: str,
    description: str,
    target: dict,
    risk: str,
    reason: str,
) -> dict:
    # auto_execute 는 본 모듈에서 항상 False. requires_approval 은 항상 True.
    return {
        "step_id": step_id,
        "action": action,
        "description": description[:500],
        "target": {
            "url": _clip_or_none(target.get("url"), 500),
            "selector": _clip_or_none(target.get("selector"), 200),
            "text": _clip_or_none(target.get("text"), 200),
        },
        "risk": risk if risk in ("low", "medium", "high", "critical") else "low",
        "requires_approval": True,
        "auto_execute": False,
        "reason": reason[:300],
    }


def _pick_guarded_action_for_kind(kind: str) -> str:
    # 둘 다 guarded click 계열로 수렴. 엔진 자체는 특정 업무 action 을
    # 만들지 않는다.
    if kind in ("button", "link"):
        return "web_click_guarded"
    return "web_click_guarded"


def _looks_like_never_auto(text: str) -> bool:
    if not text:
        return False
    lowered = text.strip().lower()
    for tok in _NEVER_AUTO_PLAN_TOKENS:
        if tok in lowered:
            return True
    # universal 한국어 위험 동사 토큰 (site_mapper 와 동일 철학).
    ko_danger = (
        "저장",  # 저장
        "제출",  # 제출
        "등록",  # 등록
        "삭제",  # 삭제
        "수정",  # 수정
        "승인",  # 승인
        "전송",  # 전송
        "결제",  # 결제
        "확정",  # 확정
        "마감",  # 마감
        "신청",  # 신청
        "취소",  # 취소
        "로그아웃",  # 로그아웃
    )
    for t in ko_danger:
        if t in text:
            return True
    return False


def _clip(value: Any, max_len: int) -> str:
    if value is None:
        return ""
    s = str(value)
    return s[:max_len] if max_len > 0 else s


def _clip_or_none(value: Any, max_len: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed[:max_len]


def _clip_str_list(value: Any, max_items: int, max_len: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for v in value:
        if isinstance(v, str) and v.strip():
            out.append(v.strip()[:max_len])
        if len(out) >= max_items:
            break
    return out


# ─── deep sanitize ────────────────────────────────────────────────────────


def _is_sensitive_key(name: str) -> bool:
    if not name:
        return False
    lowered = name.strip().lower()
    if lowered in _EXISTENCE_OK_KEYS:
        return False
    if lowered in _ALWAYS_DROP_KEYS:
        return True
    if lowered in _SENSITIVE_NAME_TOKENS:
        return True
    for tok in _SENSITIVE_NAME_TOKENS:
        if tok in lowered:
            return True
    return False


def _should_drop_key(name: str) -> bool:
    if not name:
        return False
    return name.strip().lower() in _ALWAYS_DROP_KEYS


def _looks_like_sensitive_string(value: str) -> bool:
    if not value:
        return False
    lowered = value.lower()
    # bearer / authorization header style payloads.
    if lowered.startswith("bearer ") and len(value) > 10:
        return True
    if lowered.startswith("basic ") and len(value) > 10:
        return True
    # Obvious token-like patterns: sk-..., pk_..., ghp_..., eyJ... (JWT).
    markers = ("sk-", "sk_", "pk-", "pk_", "ghp_", "xoxb-", "xoxp-")
    for m in markers:
        if lowered.startswith(m) and len(value) > 12:
            return True
    if value.startswith("eyJ") and len(value) > 20:
        return True
    return False


def _deep_sanitize(value: Any, depth: int = 0) -> Any:
    if depth > 40:
        return _REDACTED
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            if _should_drop_key(key):
                # raw_html / cookies / absolute_path 같은 항목은 존재 자체를
                # 제거한다 (존재 플래그가 따로 제공되는 경우가 많음).
                continue
            if _is_sensitive_key(key) and key.strip().lower() not in _EXISTENCE_OK_KEYS:
                # 존재 여부 플래그로 허용된 키가 아니라면 값만 redact.
                out[key] = _REDACTED
                continue
            out[key] = _deep_sanitize(v, depth + 1)
        return out
    if isinstance(value, list):
        return [_deep_sanitize(v, depth + 1) for v in value]
    if isinstance(value, tuple):
        return [_deep_sanitize(v, depth + 1) for v in value]
    if isinstance(value, str):
        if _looks_like_sensitive_string(value):
            return _REDACTED
        return value
    return value


__all__ = [
    "build_planner_prompt_payload",
    "build_deterministic_fallback_plan",
    "sanitize_planner_payload",
    "DEFAULT_AVAILABLE_ACTIONS",
    "DEFAULT_TENANT_POLICY",
    "default_available_actions",
    "default_tenant_policy",
]
