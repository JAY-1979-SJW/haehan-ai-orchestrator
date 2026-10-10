"""Instagram 댓글 키워드 Rule 엔진 — 순수 함수 (DB/네트워크 의존 없음).

판단 순서(지시문 §13 그대로):
account enabled -> rule enabled -> media scope -> text 존재 -> exclusion -> positive keyword
-> priority 순으로 최초 일치 rule 1개만 선택.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


@dataclass
class RuleMatchResult:
    matched: bool
    rule: dict[str, Any] | None = None
    matched_keyword: str | None = None
    reason: str = ""


def _media_scope_ok(rule: dict[str, Any], media_id: str | None) -> bool:
    if rule["scope_type"] == "ALL_MEDIA":
        return True
    if rule["scope_type"] == "SPECIFIC_MEDIA":
        return bool(media_id) and rule.get("media_id") == media_id
    return False


def _rule_matches_text(rule: dict[str, Any], normalized_comment: str) -> tuple[bool, str | None]:
    for kw in rule.get("exclusion_keywords") or []:
        if normalize_text(kw) and normalize_text(kw) in normalized_comment:
            return False, None
    for kw in rule.get("keywords") or []:
        nkw = normalize_text(kw)
        if nkw and nkw in normalized_comment:
            return True, kw
    return False, None


def evaluate(
    *,
    account_automation_enabled: bool,
    comment_text: str | None,
    media_id: str | None,
    rules: list[dict[str, Any]],
) -> RuleMatchResult:
    if not account_automation_enabled:
        return RuleMatchResult(matched=False, reason="ACCOUNT_DISABLED")
    if not comment_text or not comment_text.strip():
        return RuleMatchResult(matched=False, reason="EMPTY_TEXT")

    normalized = normalize_text(comment_text)

    # SPECIFIC_MEDIA 우선, 그 다음 ALL_MEDIA — 각 그룹 내에서는 priority asc, 이미 list_rules가 정렬해서 줌
    ordered = sorted(
        [r for r in rules if r.get("enabled")],
        key=lambda r: (
            0 if r["scope_type"] == "SPECIFIC_MEDIA" else 1,
            r.get("priority", 100),
            r.get("created_at", ""),
        ),
    )

    for rule in ordered:
        if not _media_scope_ok(rule, media_id):
            continue
        ok, matched_keyword = _rule_matches_text(rule, normalized)
        if ok:
            return RuleMatchResult(matched=True, rule=rule, matched_keyword=matched_keyword, reason="MATCHED")

    return RuleMatchResult(matched=False, reason="NO_MATCH")


_TEMPLATE_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")

_ALLOWED_TEMPLATE_VARS = {"username", "keyword"}


def render_template(message: str, *, username: str | None, keyword: str | None) -> str:
    values = {"username": username or "", "keyword": keyword or ""}

    def _sub(m: re.Match) -> str:
        name = m.group(1)
        if name not in _ALLOWED_TEMPLATE_VARS:
            return m.group(0)
        return values.get(name, "")

    return _TEMPLATE_VAR_RE.sub(_sub, message)
