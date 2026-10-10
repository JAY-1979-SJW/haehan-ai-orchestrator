"""EUM 신청 폼 분석 결과(data/form_analysis.json)에서 입력칸·버튼 selector 를 뽑는 공용 함수.

registration.py(WEBMAN381M00 설치신청)·deregistration.py(WEBMAN382M00 철거신청)가 똑같이
복사해 쓰던 헬퍼를 한 곳으로 모았다. 분석 파일 읽기(_load_form_analysis)는 모듈별 로그 접두어와
FORM_ANALYSIS_PATH 를 그대로 쓰도록 각 모듈에 남기고, 여기는 읽은 결과만 받아 처리한다(파일·브라우저 접근 없음).
"""

from __future__ import annotations

from typing import Any

MENU_FIELD_IDS = {"menuSearchKeyowrd", "menuSearchKeyword"}
IGNORED_BUTTON_TEXT = {"닫기", "close"}


def analysis_entries(analysis: dict[str, Any], page_code: str) -> list[dict[str, Any]]:
    """폼 분석 결과에서 키나 url 에 page_code 가 들어간 항목만 고른다."""
    entries: list[dict[str, Any]] = []
    for key, value in analysis.items():
        if not isinstance(value, dict):
            continue
        url = str(value.get("url") or "")
        if page_code in str(key) or page_code in url:
            entries.append(value)
    return entries


def selector_from_field(field: dict[str, Any]) -> str | None:
    selector = str(field.get("selector") or "").strip()
    field_id = str(field.get("id") or "").strip()
    name = str(field.get("name") or "").strip()
    if field_id in MENU_FIELD_IDS:
        return None
    if selector:
        return selector
    if field_id:
        return f"#{field_id}"
    if name:
        return f"input[name='{name}']"
    return None


def selector_from_button(button: dict[str, Any]) -> str | None:
    text = str(button.get("text") or "").strip()
    if text.lower() in IGNORED_BUTTON_TEXT:
        return None
    selector = str(button.get("selector") or "").strip()
    button_id = str(button.get("id") or "").strip()
    if selector:
        return selector
    if button_id:
        return f"#{button_id}"
    return None


def field_selectors(entries: list[dict[str, Any]], keywords: list[str]) -> list[str]:
    """분석 항목의 입력칸 중 keywords(대소문자 무시)가 id·name·placeholder·label·type 에 걸리는 것의 selector."""
    selectors: list[str] = []
    keys = [keyword.lower() for keyword in keywords if keyword]
    for entry in entries:
        fields = entry.get("fields") or entry.get("inputs") or []
        textareas = entry.get("textareas") or []
        for field in [*fields, *textareas]:
            if not isinstance(field, dict):
                continue
            haystack = " ".join(
                str(field.get(part) or "") for part in ("id", "name", "placeholder", "label", "type")
            ).lower()
            if keys and not any(key in haystack for key in keys):
                continue
            selector = selector_from_field(field)
            if selector and selector not in selectors:
                selectors.append(selector)
    return selectors


def submit_selectors(entries: list[dict[str, Any]]) -> list[str]:
    """분석 항목의 버튼 selector(닫기 버튼 제외, 중복 제거, 순서 유지)."""
    selectors: list[str] = []
    for entry in entries:
        for button in entry.get("buttons") or []:
            if not isinstance(button, dict):
                continue
            selector = selector_from_button(button)
            if selector and selector not in selectors:
                selectors.append(selector)
    return selectors
