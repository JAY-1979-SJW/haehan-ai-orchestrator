"""Naver keyword tool catalog and free-only execution policy."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.common.gate import check as gate_check
from scripts.common.json_report import save_json_report

DATA_DIR = Path("data")
LATEST_PATH = DATA_DIR / "naver_keyword_tools_latest.json"

FREE_ONLY_POLICY = {
    "naver_paid_usage": "blocked",
    "paid_api_key_issue": "blocked",
    "paid_api_call": "blocked",
    "ad_campaign_create": "blocked",
    "ad_budget_update": "blocked",
    "payment_method_register": "blocked",
    "ad_publish": "blocked",
    "allowed_scope": "free read-only trend/keyword planning only",
}


@dataclass(frozen=True)
class KeywordTool:
    key: str
    label: str
    url: str
    command: str
    mode: str
    allowed: bool
    paid_blocked: bool = True
    login_required: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PaidBlockPlan:
    action: str
    gate: str
    blocked: bool = True
    reason: str = "User policy: do not use Naver paid services."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_tool_catalog() -> dict[str, Any]:
    tools = [
        KeywordTool(
            key="datalab",
            label="네이버 데이터랩 검색어 트렌드",
            url="https://datalab.naver.com/keyword/trendSearch.naver",
            command="keyword-tools datalab --query=...",
            mode="free_readonly",
            allowed=True,
            login_required=False,
            notes=["Search trend index only; no paid API use."],
        ),
        KeywordTool(
            key="shopping-insight",
            label="네이버 데이터랩 쇼핑인사이트",
            url="https://datalab.naver.com/shoppingInsight/sCategory.naver",
            command="keyword-tools shopping --query=...",
            mode="free_readonly",
            allowed=True,
            login_required=False,
            notes=["Use for shopping/category demand checks only."],
        ),
        KeywordTool(
            key="searchad-keyword",
            label="네이버 검색광고 키워드 도구",
            url="https://searchad.naver.com/",
            command="keyword-tools searchad-plan --query=...",
            mode="free_plan_only",
            allowed=True,
            login_required=True,
            notes=[
                "Keyword volume planning only.",
                "Campaigns, budgets, payment methods, ad publish, and paid API keys are blocked.",
            ],
        ),
    ]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "naver_keyword_tools_catalog",
        "free_only_policy": FREE_ONLY_POLICY,
        "tools": [tool.to_dict() for tool in tools],
        "paid_block_plans": build_paid_block_plans(),
    }


def build_keyword_plan(query: str, *, topic: str = "") -> dict[str, Any]:
    query = query.strip()
    if not query:
        query = "인테리어,AI,업무 자동화,조명 인테리어"
    keywords = [item.strip() for item in query.split(",") if item.strip()]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "naver_keyword_research_plan",
        "topic": topic or "interior_ai_popular_topics",
        "keywords": keywords,
        "free_only_policy": FREE_ONLY_POLICY,
        "steps": [
            "Check Naver DataLab trend indices read-only.",
            "Check Shopping Insight for shopping/category demand read-only.",
            "Use SearchAd keyword tool for free keyword planning only if login is available.",
            "Do not issue paid keys, register payment methods, create campaigns, set budgets, publish ads, or call paid APIs.",
            "Use resulting keywords as inputs for Naver Cafe read-only searches.",
        ],
        "tool_commands": [
            f"python scripts/entry/cdp_cli.py naver keyword-tools datalab --query={','.join(keywords)}",
            f"python scripts/entry/cdp_cli.py naver keyword-tools shopping --query={','.join(keywords)}",
            f"python scripts/entry/cdp_cli.py naver keyword-tools searchad-plan --query={','.join(keywords)}",
        ],
        "paid_actions_blocked": build_paid_block_plans(),
    }


def build_paid_block_plans() -> list[dict[str, Any]]:
    return [
        PaidBlockPlan("paid_api_key_issue", "naver_paid_api_key_issue").to_dict(),
        PaidBlockPlan("paid_api_use", "naver_paid_api_use").to_dict(),
        PaidBlockPlan("searchad_campaign_create", "naver_searchad_campaign_create").to_dict(),
        PaidBlockPlan("searchad_budget_update", "naver_searchad_budget_update").to_dict(),
        PaidBlockPlan("payment_method_register", "naver_payment_method_register").to_dict(),
        PaidBlockPlan("ad_publish", "naver_ad_publish").to_dict(),
    ]


def assert_paid_actions_blocked() -> dict[str, Any]:
    blocked: list[str] = []
    for item in build_paid_block_plans():
        try:
            gate_check(str(item["gate"]))
        except Exception:  # noqa: BLE001 - 네이버 무료정책(FREE_ONLY_POLICY) 자가진단 함수 assert_paid_actions_blocked — 실제 결제/광고 차단은 scripts.common.gate.check가 수행하며, 여기선 그 호출이 예외를 던졌는지(=차단됨)만 집계하는 읽기전용 감사 카운터. 쓰기/승인 로직 없음.
            blocked.append(str(item["gate"]))
    return {
        "ok": len(blocked) == len(build_paid_block_plans()),
        "blocked_gates": blocked,
        "policy": FREE_ONLY_POLICY,
    }


def save_payload(payload: dict[str, Any], output: str | Path | None = None) -> Path:
    return save_json_report(payload, DATA_DIR, LATEST_PATH, output)


def print_summary(payload: dict[str, Any], path: Path) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved: {path}")
