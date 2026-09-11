"""댓글 텍스트와 등록된 키워드를 매칭하는 순수 함수 모듈."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KeywordRule:
    keyword: str
    match_type: str  # "exact" | "contains"


def matches(comment_text: str, rule: KeywordRule) -> bool:
    text = comment_text.strip()
    keyword = rule.keyword.strip()
    if not keyword:
        return False

    if rule.match_type == "exact":
        return text.lower() == keyword.lower()
    if rule.match_type == "contains":
        return keyword.lower() in text.lower()
    raise ValueError(f"알 수 없는 매칭 방식: {rule.match_type}")


def find_matching_rule(comment_text: str, rules: list[KeywordRule]) -> KeywordRule | None:
    for rule in rules:
        if matches(comment_text, rule):
            return rule
    return None
