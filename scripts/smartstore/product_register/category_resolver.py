"""Resolve product data to SmartStore category candidates."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.smartstore.product_register.category_taxonomy import load_taxonomy

AUTO_SELECT_THRESHOLD = 70
MANUAL_REVIEW_THRESHOLD = 45


@dataclass(frozen=True)
class CategoryCandidate:
    category_id: str
    name: str
    whole_category_name: str
    score: int
    matched_keywords: list[str] = field(default_factory=list)
    last_level: bool = True
    catalog_followup_required: bool = False
    kc_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _tokens(value: Any) -> list[str]:
    if isinstance(value, list):
        text = " ".join(str(item) for item in value)
    else:
        text = str(value or "")
    parts = re.split(r"[\s,/|>_\-()]+", text.lower())
    compact = text.lower().replace(" ", "")
    out = [part for part in parts if part]
    if compact:
        out.append(compact)
    return out


def _product_text(data: dict[str, Any]) -> str:
    return " ".join(
        str(data.get(key) or "")
        for key in ("name", "category", "description", "keywords", "model_name", "brand", "manufacturer")
    )


def _score_node(node: dict[str, Any], product_tokens: set[str], product_text: str) -> tuple[int, list[str]]:
    matched: list[str] = []
    score = 0
    for keyword in node.get("keywords") or []:
        key = str(keyword).lower()
        compact = key.replace(" ", "")
        if key in product_tokens or compact in product_tokens or key in product_text or compact in product_text:
            matched.append(str(keyword))
            score += 18 if len(key) <= 3 else 24
    name = str(node.get("name") or "").lower()
    whole = str(node.get("whole_category_name") or node.get("wholeCategoryName") or "").lower()
    if name and name in product_text:
        score += 20
        matched.append(str(node.get("name") or ""))
    if whole and any(part in product_text for part in whole.split(">")):
        score += 8
    if bool(node.get("last_level", node.get("lastLevel", True))):
        score += 8
    return min(score, 100), sorted(set(matched))


def resolve_category_candidates(
    data: dict[str, Any],
    *,
    taxonomy: dict[str, Any] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    taxonomy = taxonomy or load_taxonomy()
    product_text = _product_text(data).lower()
    product_tokens = set(_tokens(product_text))
    candidates: list[CategoryCandidate] = []
    for node in taxonomy.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        score, matched = _score_node(node, product_tokens, product_text)
        if score <= 0:
            continue
        candidates.append(
            CategoryCandidate(
                category_id=str(node.get("category_id") or node.get("id") or ""),
                name=str(node.get("name") or ""),
                whole_category_name=str(node.get("whole_category_name") or node.get("wholeCategoryName") or ""),
                score=score,
                matched_keywords=matched,
                last_level=bool(node.get("last_level", node.get("lastLevel", True))),
                catalog_followup_required=bool(node.get("catalog_followup_required")),
                kc_required=bool(node.get("kc_required")),
            )
        )
    ranked = sorted(candidates, key=lambda item: (item.score, item.last_level), reverse=True)[:limit]
    top = ranked[0] if ranked else None
    if not top:
        decision = "manual_review_required"
    elif top.score >= AUTO_SELECT_THRESHOLD and top.last_level:
        decision = "auto_select_allowed"
    elif top.score >= MANUAL_REVIEW_THRESHOLD:
        decision = "manual_review_recommended"
    else:
        decision = "manual_review_required"
    return {
        "ok": bool(top),
        "decision": decision,
        "auto_select_allowed": decision == "auto_select_allowed",
        "manual_review_required": decision != "auto_select_allowed",
        "top": top.to_dict() if top else {},
        "candidates": [candidate.to_dict() for candidate in ranked],
        "catalog_followup_required": bool(top and top.catalog_followup_required),
        "kc_required": bool(top and top.kc_required),
    }
