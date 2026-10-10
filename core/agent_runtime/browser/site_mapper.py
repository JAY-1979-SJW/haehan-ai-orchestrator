"""local_agent 범용 site map payload builder (Stage 4 preparation).

본 모듈은 실제 GPT/OpenAI API 를 호출하지 않으며, 외부 네트워크로 아무것도
전송하지 않는다. ``web_reader.analyze_html_structure`` 또는
``browser_reader.open_url_readonly`` 의 결과를 받아, 이후 LLM 에게 넘길 수
있는 "범용(domain-agnostic) 관찰 payload" 를 deterministic 하게 만들 뿐이다.

설계 원칙
  - 특정 업무/도메인 키워드를 본 엔진 기본값으로 하드코딩하지 않는다.
  - 특정 도메인 힌트는 모두 외부 입력(``domain_profile``, ``keyword_hints``,
    ``user_goal``) 을 통해서만 들어온다.
  - 하드코딩이 허용되는 것은 저장/제출/삭제 같은 "universal safety policy"
    쓰기 동사뿐이며, 이는 특정 업무 영역과 무관한 안전 정책이다.
  - payload 에는 HTML 원문 전체, password/hidden input 의 value, cookie,
    token 류 원문, full local path, screenshot 경로, device token, API key
    원문이 절대 포함되지 않는다.
  - 본 모듈은 클릭/입력/제출/저장/삭제/업로드/네트워크 요청을 수행하지 않는다.

출력 payload 는 LLM 에게 "판단" 만 맡기고, 실행은 별도의 guarded action
레이어에서만 수행되도록 설계되어 있다.
"""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import suppress
from typing import Any
from urllib.parse import urlparse

# ─── Universal safety terms (도메인 키워드 아님, 안전 정책) ───────────────
#
# 주의: 아래 상수에는 특정 업무 키워드를 넣지 않는다. 업무/도메인 힌트는
# 전부 호출자가 ``domain_profile`` / ``keyword_hints`` / ``user_goal`` 로
# 주입해야 한다.

UNIVERSAL_SAFE_READ_TERMS: tuple[str, ...] = (
    "조회",
    "검색",
    "보기",
    "목록",
    "상세",
    "다음",
    "이전",
    "닫기",
    "확인",
    "cancel",
    "close",
    "search",
    "view",
    "list",
    "detail",
    "next",
    "previous",
)

UNIVERSAL_DANGER_WRITE_TERMS: tuple[str, ...] = (
    "저장",
    "제출",
    "등록",
    "삭제",
    "수정",
    "승인",
    "전송",
    "결제",
    "확정",
    "마감",
    "신청",
    "취소",
    "save",
    "submit",
    "register",
    "delete",
    "remove",
    "edit",
    "approve",
    "send",
    "payment",
    "confirm",
    "apply",
    "cancel",
)

PAGE_ROLE_CANDIDATES: tuple[str, ...] = (
    "dashboard",
    "menu_page",
    "list_page",
    "detail_page",
    "search_page",
    "form_page",
    "table_page",
    "login_page",
    "modal_page",
    "unknown",
)


# ─── 민감 키/값 토큰 테이블 ────────────────────────────────────────────────

_SENSITIVE_NAME_TOKENS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "cookie",
        "set-cookie",
        "authorization",
        "auth",
        "bearer",
        "session",
        "sessionid",
        "session_id",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "csrf",
        "xsrf",
        "csrf_token",
        "xsrf_token",
        "api_key",
        "apikey",
        "api-key",
        "device_token",
        "devicetoken",
    }
)

_ALWAYS_DROP_OBSERVATION_KEYS: frozenset[str] = frozenset(
    {
        "html",
        "raw_html",
        "page_html",
        "body_html",
        "outer_html",
        "inner_html",
        "screenshot_path",
        "screenshot_file",
        "absolute_path",
        "full_path",
        "local_path",
        "file_path",
        "device_token",
        "agent_token",
        "session_token",
        "cookies",
        "cookie",
        "authorization",
        "auth_header",
    }
)

_REDACTED = "<redacted>"


# ─── 공개 API ─────────────────────────────────────────────────────────────


def build_site_map_prompt_payload(
    page_observation: dict,
    user_goal: str | None = None,
    domain_profile: dict | None = None,
    keyword_hints: list[str] | None = None,
    max_items: int = 80,
) -> dict:
    """generic site map prompt payload 반환 (deterministic, IO 없음).

    실제 GPT/OpenAI API 를 호출하지 않는다. 외부 네트워크 요청이나 웹사이트
    접속, 클릭/입력/저장/삭제 동작은 전혀 수행하지 않는다.
    """
    warnings: list[str] = []
    if not isinstance(page_observation, dict):
        return _empty_payload(
            user_goal,
            warning="page_observation_not_dict",
        )

    goal = _normalize_goal(user_goal)
    hints = _normalize_hints(keyword_hints)
    profile = _normalize_domain_profile(domain_profile)
    limit = _normalize_max_items(max_items)

    # page_structure 는 browser_reader 결과의 경우 nested 로 들어오고,
    # web_reader 결과를 직접 넘기는 경우엔 최상위에 있음.
    page_structure = page_observation.get("page_structure")
    if not isinstance(page_structure, dict):
        page_structure = page_observation

    title = _coerce_str(
        page_observation.get("title") or page_structure.get("page_title") or "",
        max_len=300,
    )
    current_url = _coerce_str(
        page_observation.get("current_url") or page_observation.get("url") or "",
        max_len=500,
    )
    host = ""
    if current_url:
        try:
            host = (urlparse(current_url).hostname or "")[:200]
        except ValueError:
            host = ""
    login_required_hint = bool(page_observation.get("login_required_hint", False))
    modal_candidates = page_observation.get("modal_candidates") or []
    has_modal = bool(modal_candidates)

    sanitized = sanitize_for_gpt_payload(page_structure, max_items=limit)

    counts = {
        "links": len(sanitized.get("links") or []),
        "buttons": len(sanitized.get("buttons") or []),
        "forms": len(sanitized.get("forms") or []),
        "tables": len(sanitized.get("tables") or []),
        "inputs": len(sanitized.get("inputs") or []),
    }
    if not any(counts.values()) and not title and not host:
        warnings.append("observation_empty")

    page_role_candidates = _score_page_roles(
        sanitized,
        login_required_hint=login_required_hint,
        has_modal=has_modal,
    )
    domain_matches = _score_domain_profile(sanitized, title, profile, goal)
    danger_elements = _collect_danger_elements(sanitized, profile)[:limit]
    safe_navigation = _collect_safe_navigation(
        sanitized,
        profile,
        hints,
    )[:limit]
    task_candidates = _build_task_candidates(
        sanitized=sanitized,
        profile=profile,
        hints=hints,
        goal=goal,
        title=title,
        page_role_candidates=page_role_candidates,
    )[:limit]

    payload = {
        "ok": True,
        "purpose": "generic_site_map_analysis",
        "user_goal": goal,
        "page_summary": {
            "title": title[:200],
            "current_url_host": host,
            "login_required_hint": login_required_hint,
            "has_modal_candidates": has_modal,
            "counts": counts,
        },
        "sanitized_observation": sanitized,
        "heuristic_candidates": {
            "page_role_candidates": page_role_candidates,
            "domain_profile_matches": domain_matches,
            "task_candidates": task_candidates,
            "danger_elements": danger_elements,
            "safe_navigation_candidates": safe_navigation,
        },
        "gpt_instruction": _build_gpt_instruction(),
        "expected_json_schema": _build_expected_json_schema(),
        "warnings": warnings,
    }
    return payload


def sanitize_for_gpt_payload(
    page_structure: dict,
    max_items: int = 80,
) -> dict:
    """observation 의 구조만 추려 LLM 에 넘길 수 있는 형태로 가공.

    어떤 경우에도 다음을 포함하지 않는다.
      - HTML 원문 전체
      - input 의 value (password / hidden 포함)
      - cookie / session / token / authorization / csrf 원문
      - 로컬 파일 전체 경로, screenshot 경로, device token
    민감 키는 ``<redacted>`` 로 치환되거나 항목 자체에서 제거된다.
    """
    if not isinstance(page_structure, dict):
        return _empty_sanitized()

    limit = _normalize_max_items(max_items)

    links = _sanitize_list(
        page_structure.get("links"),
        _sanitize_link,
        limit,
    )
    buttons = _sanitize_list(
        page_structure.get("buttons"),
        _sanitize_button,
        limit,
    )
    forms = _sanitize_list(
        page_structure.get("forms"),
        _sanitize_form,
        limit,
    )
    tables = _sanitize_list(
        page_structure.get("tables"),
        _sanitize_table,
        limit,
    )
    inputs = _sanitize_list(
        page_structure.get("inputs"),
        _sanitize_input,
        limit,
    )

    return {
        "links": links,
        "buttons": buttons,
        "forms": forms,
        "tables": tables,
        "inputs": inputs,
    }


# ─── 정규화 ──────────────────────────────────────────────────────────────


def _normalize_goal(goal: Any) -> str | None:
    if not isinstance(goal, str):
        return None
    trimmed = goal.strip()
    if not trimmed:
        return None
    return trimmed[:500]


def _normalize_hints(hints: Any) -> list[str]:
    if not isinstance(hints, list):
        return []
    out: list[str] = []
    for h in hints:
        if isinstance(h, str) and h.strip():
            out.append(h.strip()[:60])
        if len(out) >= 50:
            break
    return out


def _normalize_max_items(value: Any) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 80
    if v <= 0:
        v = 80
    return min(v, 2000)


def _normalize_domain_profile(profile: Any) -> dict | None:
    if not isinstance(profile, dict):
        return None
    normalized: dict[str, Any] = {
        "profile_key": _coerce_str(profile.get("profile_key", ""), 64),
        "description": _coerce_str(profile.get("description", ""), 200),
        "keywords": _coerce_str_list(profile.get("keywords"), 50, 60),
        "preferred_navigation_terms": _coerce_str_list(
            profile.get("preferred_navigation_terms"),
            50,
            60,
        ),
        "danger_terms": _coerce_str_list(profile.get("danger_terms"), 50, 60),
        "task_candidates": [],
    }
    for t in profile.get("task_candidates") or []:
        if not isinstance(t, dict):
            continue
        task_name = _coerce_str(t.get("task", ""), 80)
        if not task_name:
            continue
        normalized["task_candidates"].append(
            {
                "task": task_name,
                "keywords": _coerce_str_list(t.get("keywords"), 20, 60),
                "description": _coerce_str(t.get("description", ""), 200),
            }
        )
        if len(normalized["task_candidates"]) >= 50:
            break
    return normalized


# ─── sanitize helpers ────────────────────────────────────────────────────


def _empty_sanitized() -> dict:
    return {
        "links": [],
        "buttons": [],
        "forms": [],
        "tables": [],
        "inputs": [],
    }


def _sanitize_list(src, fn, limit: int) -> list[dict]:
    if not isinstance(src, list):
        return []
    out: list[dict] = []
    for item in src[:limit]:
        shaped = fn(item)
        if shaped is not None:
            out.append(shaped)
    return out


def _coerce_str(value: Any, max_len: int) -> str:
    if value is None:
        return ""
    s = str(value)
    return s[:max_len] if max_len > 0 else s


def _coerce_str_list(value: Any, max_items: int, max_len: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for v in value:
        if isinstance(v, str) and v.strip():
            out.append(v.strip()[:max_len])
        if len(out) >= max_items:
            break
    return out


def _is_sensitive_name(name: str) -> bool:
    if not name:
        return False
    lowered = name.strip().lower()
    if lowered in _SENSITIVE_NAME_TOKENS:
        return True
    for token in _SENSITIVE_NAME_TOKENS:
        if token in lowered:
            return True
    return False


def _redact_href(href: str) -> str:
    """href 의 query 문자열에 민감 토큰이 보이면 전체를 <redacted> 로 치환."""
    if not href:
        return ""
    low = href.lower()
    for tok in _SENSITIVE_NAME_TOKENS:
        if f"{tok}=" in low or f"{tok}%3d" in low:
            return _REDACTED
    return href


def _sanitize_link(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None
    out: dict[str, Any] = {
        "text": _coerce_str(item.get("text", ""), 200),
        "href": _redact_href(_coerce_str(item.get("href", ""), 500)),
        "risk_hint": _coerce_str(item.get("risk_hint", "safe_read"), 32),
    }
    if "keyword_score" in item:
        with suppress(TypeError, ValueError):
            out["keyword_score"] = int(item.get("keyword_score") or 0)
    return out


def _sanitize_button(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None
    return {
        "text": _coerce_str(item.get("text", ""), 200),
        "type": _coerce_str(item.get("type", ""), 32),
        "risk_level": _coerce_str(item.get("risk_level", "unknown"), 32),
        "reason": _coerce_str(item.get("reason", ""), 120),
    }


def _sanitize_form(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None
    method = _coerce_str(item.get("method", "get"), 10).lower()
    action = _redact_href(_coerce_str(item.get("action", ""), 300))
    try:
        field_count = int(item.get("field_count") or 0)
    except (TypeError, ValueError):
        field_count = 0
    return {
        "method": method,
        "action": action,
        "field_count": field_count,
        "has_password": bool(item.get("has_password", False)),
        "has_hidden": bool(item.get("has_hidden", False)),
        "risk_level": _coerce_str(item.get("risk_level", "unknown"), 32),
    }


def _sanitize_table(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None
    headers_raw = item.get("headers") or []
    headers: list[str] = []
    if isinstance(headers_raw, list):
        for h in headers_raw[:50]:
            headers.append(_coerce_str(h, 200))
    try:
        row_count = int(item.get("row_count") or 0)
    except (TypeError, ValueError):
        row_count = 0
    try:
        column_count = int(item.get("column_count") or 0)
    except (TypeError, ValueError):
        column_count = 0
    return {
        "headers": headers,
        "row_count": row_count,
        "column_count": column_count,
    }


def _sanitize_input(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None
    name_raw = _coerce_str(item.get("name", ""), 200)
    itype = _coerce_str(item.get("type", "text"), 32).lower()
    placeholder = _coerce_str(item.get("placeholder", ""), 200)
    label = _coerce_str(item.get("label", ""), 200)

    # 민감 이름이면 이름과 placeholder/label 를 redact (존재 자체는 공개).
    if _is_sensitive_name(name_raw):
        return {
            "name": _REDACTED,
            "type": itype if itype else "sensitive",
            "placeholder": "",
            "label": "",
        }
    # password / hidden 은 value 가 없고, placeholder/label 도 민감 토큰이 아니어야 함.
    if itype in ("password", "hidden"):
        return {
            "name": name_raw,
            "type": itype,
            "placeholder": "" if _is_sensitive_name(placeholder) else placeholder,
            "label": "" if _is_sensitive_name(label) else label,
        }
    return {
        "name": name_raw,
        "type": itype,
        "placeholder": placeholder,
        "label": label,
    }


# ─── page role heuristic (generic) ───────────────────────────────────────


def _bump_role(
    merged: dict[str, dict[str, Any]],
    role: str,
    score: float,
    reasons: Iterable[str],
) -> None:
    score = round(max(0.0, min(score, 0.99)), 3)
    entry = merged.get(role)
    if entry is None:
        merged[role] = {
            "role": role,
            "score": score,
            "reasons": list(reasons),
        }
        return
    if score > entry["score"]:
        entry["score"] = score
    for r in reasons:
        if r not in entry["reasons"]:
            entry["reasons"].append(r)


def _bump_login_modal_roles(
    merged: dict[str, dict[str, Any]],
    login_required_hint: bool,
    has_password_input: bool,
    has_modal: bool,
) -> None:
    if login_required_hint or has_password_input:
        reasons = []
        if login_required_hint:
            reasons.append("login_required_hint")
        if has_password_input:
            reasons.append("password_input")
        _bump_role(merged, "login_page", 0.9, reasons)

    if has_modal:
        _bump_role(merged, "modal_page", 0.7, ["modal_candidates"])


def _bump_table_roles(merged: dict[str, dict[str, Any]], tables: list) -> None:
    if tables:
        total_rows = sum(int(t.get("row_count") or 0) for t in tables if isinstance(t, dict))
        reasons = [f"tables:{len(tables)}", f"rows:{total_rows}"]
        _bump_role(
            merged,
            "table_page",
            0.6 + 0.05 * min(len(tables), 5),
            reasons,
        )
        if total_rows >= 2:
            _bump_role(
                merged,
                "list_page",
                0.5 + 0.03 * min(total_rows, 10),
                reasons,
            )


def _bump_form_roles(
    merged: dict[str, dict[str, Any]],
    forms: list,
    inputs: list,
    buttons: list,
) -> None:
    if forms:
        reasons = [f"forms:{len(forms)}", f"inputs:{len(inputs)}"]
        _bump_role(
            merged,
            "form_page",
            0.5 + 0.08 * min(len(forms), 3) + 0.01 * min(len(inputs), 10),
            reasons,
        )
        has_search_affordance = any(
            _matches_terms(_coerce_str(b.get("text", ""), 200), UNIVERSAL_SAFE_READ_TERMS)
            for b in buttons
            if isinstance(b, dict)
        )
        if has_search_affordance:
            _bump_role(merged, "search_page", 0.6, [*reasons, "safe_read_button"])


def _bump_layout_roles(
    merged: dict[str, dict[str, Any]],
    links: list,
    buttons: list,
    forms: list,
    tables: list,
) -> None:
    if len(links) >= 5 and len(buttons) <= max(2, len(links) // 4):
        _bump_role(
            merged,
            "menu_page",
            0.5 + 0.02 * min(len(links), 20),
            [f"links:{len(links)}", f"buttons:{len(buttons)}"],
        )

    if len(tables) >= 2 and len(forms) <= 1:
        _bump_role(
            merged,
            "dashboard",
            0.55,
            [f"tables:{len(tables)}", f"forms:{len(forms)}"],
        )


def _score_page_roles(
    sanitized: dict,
    *,
    login_required_hint: bool,
    has_modal: bool,
) -> list[dict]:
    """구조 신호만 보고 페이지 역할 후보를 점수화. 도메인 키워드 미사용."""
    links = sanitized.get("links") or []
    buttons = sanitized.get("buttons") or []
    forms = sanitized.get("forms") or []
    tables = sanitized.get("tables") or []
    inputs = sanitized.get("inputs") or []

    has_password_input = any((i.get("type") == "password") for i in inputs if isinstance(i, dict))
    merged: dict[str, dict[str, Any]] = {}

    _bump_login_modal_roles(merged, login_required_hint, has_password_input, has_modal)
    _bump_table_roles(merged, tables)
    _bump_form_roles(merged, forms, inputs, buttons)

    if tables and len(forms) == 0:
        _bump_role(merged, "list_page", 0.55, [f"tables:{len(tables)}", "no_form"])

    _bump_layout_roles(merged, links, buttons, forms, tables)

    if not merged:
        _bump_role(merged, "unknown", 0.3, ["no_structural_signal"])

    return sorted(merged.values(), key=lambda r: r["score"], reverse=True)


# ─── domain profile matching ─────────────────────────────────────────────


def _score_domain_profile(
    sanitized: dict,
    title: str,
    profile: dict | None,
    goal: str | None,
) -> list[dict]:
    """domain_profile 이 제공된 경우에만 profile keyword 매칭 결과 반환."""
    if not profile:
        return []
    blob = _build_text_blob(sanitized, title, goal)
    if not blob:
        return []
    reasons: list[str] = []
    score = 0.0
    for kw in profile.get("keywords") or []:
        if kw and kw in blob:
            reasons.append(f"keyword:{kw}")
            score += 0.25
    for task in profile.get("task_candidates") or []:
        for kw in task.get("keywords") or []:
            if kw and kw in blob:
                reasons.append(f"task_keyword:{kw}")
                score += 0.15
    if not reasons:
        return []
    return [
        {
            "profile_key": profile.get("profile_key", ""),
            "score": round(min(score, 0.99), 3),
            "reasons": reasons[:10],
        }
    ]


def _build_text_blob(sanitized: dict, title: str, goal: str | None) -> str:
    chunks: list[str] = [title or "", goal or ""]
    for link in sanitized.get("links") or []:
        if isinstance(link, dict):
            chunks.append(link.get("text", ""))
    for btn in sanitized.get("buttons") or []:
        if isinstance(btn, dict):
            chunks.append(btn.get("text", ""))
    for table in sanitized.get("tables") or []:
        if isinstance(table, dict):
            for h in table.get("headers") or []:
                chunks.append(str(h))
    for inp in sanitized.get("inputs") or []:
        if isinstance(inp, dict):
            chunks.append(inp.get("placeholder", ""))
            chunks.append(inp.get("label", ""))
    return " ".join(c for c in chunks if c)


# ─── danger / safe 분리 ─────────────────────────────────────────────────


def _matches_terms(text: str, terms: tuple[str, ...]) -> bool:
    if not text:
        return False
    lowered = text.lower()
    for t in terms:
        if not t:
            continue
        if t in text or t.lower() in lowered:
            return True
    return False


def _profile_danger_terms(profile: dict | None) -> tuple[str, ...]:
    if not profile:
        return ()
    return tuple(profile.get("danger_terms") or ())


def _profile_nav_terms(profile: dict | None) -> tuple[str, ...]:
    if not profile:
        return ()
    return tuple(profile.get("preferred_navigation_terms") or ())


def _is_danger(text: str, risk_level: str, extra_terms: tuple[str, ...]) -> bool:
    if risk_level == "danger_write":
        return True
    if _matches_terms(text, UNIVERSAL_DANGER_WRITE_TERMS):
        return True
    if extra_terms and _matches_terms(text, extra_terms):
        return True
    return False


def _danger_buttons(sanitized: dict, extra_danger: tuple[str, ...]) -> list[dict]:
    out: list[dict] = []

    for btn in sanitized.get("buttons") or []:
        if not isinstance(btn, dict):
            continue
        text = btn.get("text", "")
        rl = btn.get("risk_level", "unknown")
        if _is_danger(text, rl, extra_danger):
            out.append(
                {
                    "kind": "button",
                    "text": text,
                    "risk": "high",
                    "reason": btn.get("reason") or _danger_reason(text, rl, extra_danger),
                }
            )
    return out


def _danger_links(sanitized: dict, extra_danger: tuple[str, ...]) -> list[dict]:
    out: list[dict] = []

    for link in sanitized.get("links") or []:
        if not isinstance(link, dict):
            continue
        text = link.get("text", "")
        rh = link.get("risk_hint", "safe_read")
        if _is_danger(text, rh, extra_danger):
            out.append(
                {
                    "kind": "link",
                    "text": text,
                    "risk": "high",
                    "reason": _danger_reason(text, rh, extra_danger),
                }
            )
    return out


def _danger_forms(sanitized: dict) -> list[dict]:
    out: list[dict] = []

    for form in sanitized.get("forms") or []:
        if not isinstance(form, dict):
            continue
        method = (form.get("method") or "get").lower()
        has_password = bool(form.get("has_password"))
        risk_level = form.get("risk_level", "unknown")
        if method == "post" or has_password or risk_level == "danger_write":
            reason_parts: list[str] = []
            if method == "post":
                reason_parts.append("post_method")
            if has_password:
                reason_parts.append("has_password")
            if risk_level == "danger_write":
                reason_parts.append("form_danger_write")
            out.append(
                {
                    "kind": "form",
                    "text": f"form[{method.upper()}]",
                    "risk": "high",
                    "reason": ",".join(reason_parts) or "form_write",
                }
            )
    return out


def _collect_danger_elements(sanitized: dict, profile: dict | None) -> list[dict]:
    extra_danger = _profile_danger_terms(profile)
    out: list[dict] = []
    out.extend(_danger_buttons(sanitized, extra_danger))
    out.extend(_danger_links(sanitized, extra_danger))
    out.extend(_danger_forms(sanitized))
    return out


def _danger_reason(text: str, risk_level: str, extra_terms: tuple[str, ...]) -> str:
    if risk_level == "danger_write":
        return "classified_danger_write"
    if _matches_terms(text, UNIVERSAL_DANGER_WRITE_TERMS):
        return "universal_danger_term"
    if extra_terms and _matches_terms(text, extra_terms):
        return "domain_danger_term"
    return "danger_write"


def _score_safe_candidate(
    kind: str,
    text: str,
    base_risk: str,
    extra_danger: tuple[str, ...],
    pref_terms: tuple[str, ...],
    hints: list[str],
) -> dict | None:
    """safe navigation 후보 1건 점수화. danger 이거나 신호가 없으면 None."""
    # danger first — 어떤 신호든 danger 면 safe 후보 금지.
    if _is_danger(text, base_risk, extra_danger):
        return None
    score = 0
    reasons: list[str] = []
    if _matches_terms(text, UNIVERSAL_SAFE_READ_TERMS):
        reasons.append("universal_safe_term")
        score += 2
    for t in pref_terms:
        if t and t in text:
            reasons.append(f"profile_term:{t}")
            score += 2
    for kw in hints:
        if kw and kw in text:
            reasons.append(f"hint:{kw}")
            score += 2
    if base_risk == "safe_read":
        # safe_read 상태인 링크/버튼은 기본 가산점 +1. reason 이 이미 있어도
        # hint 와 합산되어 no_hint vs with_hint 구분이 안전하게 유지된다.
        reasons.append(f"safe_read_{kind}")
        score += 1
    if not reasons:
        return None
    return {
        "kind": kind,
        "text": text,
        "risk": "low",
        "score": score,
        "reasons": reasons[:10],
    }


def _collect_safe_navigation(
    sanitized: dict,
    profile: dict | None,
    hints: list[str],
) -> list[dict]:
    extra_danger = _profile_danger_terms(profile)
    pref_terms = _profile_nav_terms(profile)
    out: list[dict] = []

    def _handle(kind: str, text: str, base_risk: str) -> None:
        cand = _score_safe_candidate(kind, text, base_risk, extra_danger, pref_terms, hints)
        if cand is not None:
            out.append(cand)

    for link in sanitized.get("links") or []:
        if not isinstance(link, dict):
            continue
        _handle(
            "link",
            _coerce_str(link.get("text", ""), 200),
            _coerce_str(link.get("risk_hint", "safe_read"), 32),
        )

    for btn in sanitized.get("buttons") or []:
        if not isinstance(btn, dict):
            continue
        _handle(
            "button",
            _coerce_str(btn.get("text", ""), 200),
            _coerce_str(btn.get("risk_level", "unknown"), 32),
        )

    return sorted(out, key=lambda r: r.get("score", 0), reverse=True)


# ─── task candidates (generic pool + optional profile) ───────────────────


GENERIC_TASK_POOL: tuple[str, ...] = (
    "navigate_to_relevant_section",
    "inspect_table",
    "inspect_form",
    "search_or_filter",
    "review_page_structure",
    "ask_user_to_identify_goal",
)


def _generic_task_candidates(sanitized: dict, goal: str | None, roles: set) -> list[dict]:
    out: list[dict] = []
    links = sanitized.get("links") or []
    buttons = sanitized.get("buttons") or []
    forms = sanitized.get("forms") or []
    tables = sanitized.get("tables") or []

    if tables:
        out.append(
            {
                "task": "inspect_table",
                "confidence": 0.6 if "table_page" in roles else 0.4,
                "reasons": [f"tables:{len(tables)}"],
                "requires_user_confirmation": True,
            }
        )
    if forms:
        out.append(
            {
                "task": "inspect_form",
                "confidence": 0.5 if "form_page" in roles else 0.35,
                "reasons": [f"forms:{len(forms)}"],
                "requires_user_confirmation": True,
            }
        )
    if links:
        out.append(
            {
                "task": "navigate_to_relevant_section",
                "confidence": 0.4,
                "reasons": [f"links:{len(links)}"],
                "requires_user_confirmation": True,
            }
        )
    safe_read_buttons = [
        b
        for b in buttons
        if isinstance(b, dict) and _matches_terms(_coerce_str(b.get("text", ""), 200), UNIVERSAL_SAFE_READ_TERMS)
    ]
    if safe_read_buttons:
        out.append(
            {
                "task": "search_or_filter",
                "confidence": 0.5,
                "reasons": [f"safe_read_buttons:{len(safe_read_buttons)}"],
                "requires_user_confirmation": True,
            }
        )
    out.append(
        {
            "task": "review_page_structure",
            "confidence": 0.3,
            "reasons": ["baseline"],
            "requires_user_confirmation": False,
        }
    )
    if not goal:
        out.append(
            {
                "task": "ask_user_to_identify_goal",
                "confidence": 0.8,
                "reasons": ["user_goal_missing"],
                "requires_user_confirmation": True,
            }
        )
    return out


def _profile_task_candidates(sanitized: dict, profile: dict | None, goal: str | None, title: str) -> list[dict]:
    out: list[dict] = []
    # domain_profile 에서만 특정 업무 task 이름을 가져온다. 엔진 자체는
    # 특정 업무 task 를 발명하지 않는다.
    if profile:
        blob = _build_text_blob(sanitized, title, goal)
        for task_def in profile.get("task_candidates") or []:
            task_name = task_def.get("task")
            if not task_name:
                continue
            matched = [kw for kw in task_def.get("keywords") or [] if kw and kw in blob]
            if not matched:
                continue
            out.append(
                {
                    "task": task_name,
                    "confidence": round(min(0.5 + 0.1 * len(matched), 0.95), 3),
                    "reasons": [f"profile_keyword:{kw}" for kw in matched[:5]],
                    "requires_user_confirmation": True,
                }
            )
    return out


def _boost_confidence_for_goal(out: list[dict], goal: str | None) -> None:
    # user_goal 이 주어지면 task 후보 점수를 전체적으로 소폭 상향.
    # (사용자가 방향을 제시했으므로 "baseline 탐색" 의 가치가 높아짐)
    if goal:
        for c in out:
            if c.get("task") == "ask_user_to_identify_goal":
                continue
            c["confidence"] = round(min(float(c.get("confidence", 0)) + 0.1, 0.99), 3)


def _boost_for_profile_goal_match(out: list[dict], goal: str | None, profile: dict | None) -> None:
    # user_goal 과 profile task keyword 의 직접 매칭이 있으면 추가 보정.
    if goal and profile:
        goal_lower = goal.lower()
        for task_def in profile.get("task_candidates") or []:
            task_name = task_def.get("task")
            for kw in task_def.get("keywords") or []:
                if not kw:
                    continue
                if kw in goal or kw.lower() in goal_lower:
                    for c in out:
                        if c.get("task") == task_name:
                            c["confidence"] = round(
                                min(float(c.get("confidence", 0)) + 0.05, 0.99),
                                3,
                            )
                            c.setdefault("reasons", []).append(f"goal_match:{kw}")
                    break


def _boost_for_goal_hints(out: list[dict], goal: str | None, hints: list[str]) -> None:
    # keyword_hints 가 goal 에 포함되어 있으면 generic task 에도 소폭 보정.
    if goal and hints:
        for kw in hints:
            if kw and kw in goal:
                for c in out:
                    if c.get("task") in GENERIC_TASK_POOL:
                        c.setdefault("reasons", []).append(f"goal_hint:{kw}")


def _build_task_candidates(
    *,
    sanitized: dict,
    profile: dict | None,
    hints: list[str],
    goal: str | None,
    title: str,
    page_role_candidates: list[dict],
) -> list[dict]:
    roles = {r.get("role") for r in page_role_candidates if isinstance(r, dict)}
    out = _generic_task_candidates(sanitized, goal, roles)
    out.extend(_profile_task_candidates(sanitized, profile, goal, title))
    _boost_confidence_for_goal(out, goal)
    _boost_for_profile_goal_match(out, goal, profile)
    _boost_for_goal_hints(out, goal, hints)

    return sorted(
        out,
        key=lambda c: float(c.get("confidence", 0)),
        reverse=True,
    )


# ─── GPT instruction / schema ────────────────────────────────────────────


def _build_gpt_instruction() -> str:
    """실제 GPT 호출은 하지 않는다. 호출자가 나중에 LLM 에 줄 instruction 문자열만 만든다."""
    return (
        "You are a domain-agnostic site map analyst facing an unfamiliar workflow "
        "web site.\n"
        "Use ONLY the observation data provided in this payload. Do not browse, "
        "do not call any network resource, and do not invent content that is "
        "not listed in sanitized_observation.\n"
        "\n"
        "Rules:\n"
        "1. Do not assume a specific business domain. If a domain_profile is "
        "supplied, treat it as a hint only — prefer evidence from the "
        "observation over the profile name.\n"
        "2. If user_goal is provided, suggest candidate navigation paths that "
        "match it. If it is missing, ask the user to clarify via "
        "questions_for_user.\n"
        "3. NEVER list Save / Submit / Delete / Remove / Approve / Register / "
        "Edit / Confirm / Apply / Send / Payment actions "
        "(or their Korean equivalents 저장 / 제출 / 삭제 / 수정 / 승인 / 등록 "
        "/ 전송 / 결제 / 확정 / 마감 / 신청 / 취소) "
        "as safe_next_actions. Those belong in danger_elements.\n"
        "4. When confidence is low, set requires_user_confirmation=true and "
        "add clarifying items to questions_for_user instead of acting.\n"
        "5. Never request, infer, or echo passwords, session identifiers, "
        "cookies, CSRF tokens, hidden form values, bearer tokens, or API "
        "keys. Treat them as entirely out of scope.\n"
        "6. Respond strictly in the JSON shape defined by expected_json_schema. "
        "Do not add fields that are not in that schema.\n"
    )


def _build_expected_json_schema() -> dict:
    """실제 GPT 호출은 하지 않는다. 기대하는 GPT 출력 형태만 기술한 dict."""
    return {
        "site_type": "unknown|string_from_profile_or_inferred_generic",
        "confidence": 0.0,
        "page_role": "|".join(PAGE_ROLE_CANDIDATES),
        "candidate_tasks": [
            {
                "task": "string",
                "confidence": 0.0,
                "candidate_paths": [[{"text": "menu label", "risk": "low"}]],
                "requires_user_confirmation": True,
            }
        ],
        "safe_next_actions": [
            {
                "action": "click|inspect|ask_user",
                "target_text": "string",
                "risk": "low|medium",
                "reason": "string",
            }
        ],
        "danger_elements": [
            {
                "text": "string",
                "risk": "high|critical",
                "reason": "string",
            }
        ],
        "questions_for_user": [],
        "do_not_execute": [],
    }


def _empty_payload(user_goal: Any, *, warning: str) -> dict:
    """page_observation 이 dict 가 아닐 때의 안전 기본값."""
    goal = _normalize_goal(user_goal)
    return {
        "ok": True,
        "purpose": "generic_site_map_analysis",
        "user_goal": goal,
        "page_summary": {
            "title": "",
            "current_url_host": "",
            "login_required_hint": False,
            "has_modal_candidates": False,
            "counts": {
                "links": 0,
                "buttons": 0,
                "forms": 0,
                "tables": 0,
                "inputs": 0,
            },
        },
        "sanitized_observation": _empty_sanitized(),
        "heuristic_candidates": {
            "page_role_candidates": [{"role": "unknown", "score": 0.3, "reasons": ["no_structural_signal"]}],
            "domain_profile_matches": [],
            "task_candidates": [],
            "danger_elements": [],
            "safe_navigation_candidates": [],
        },
        "gpt_instruction": _build_gpt_instruction(),
        "expected_json_schema": _build_expected_json_schema(),
        "warnings": [warning] if warning else [],
    }


__all__ = [
    "GENERIC_TASK_POOL",
    "PAGE_ROLE_CANDIDATES",
    "UNIVERSAL_DANGER_WRITE_TERMS",
    "UNIVERSAL_SAFE_READ_TERMS",
    "build_site_map_prompt_payload",
    "sanitize_for_gpt_payload",
]
