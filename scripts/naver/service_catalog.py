"""Naver service capability catalog for CLI routing and worktree indexing."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path("data")
LATEST_PATH = DATA_DIR / "naver_service_action_catalog_latest.json"


FEATURE_CATALOG: dict[str, dict[str, Any]] = {
    "session": {
        "commands": ["session-check", "login"],
        "read": ["session-check"],
        "prepare": [],
        "submit": [],
    },
    "mail": {
        "commands": ["mail inbox", "mail compose", "mail send"],
        "read": ["inbox"],
        "prepare": ["compose"],
        "submit": ["send"],
    },
    "blog-assets": {
        "commands": [
            "blog-assets plan",
            "blog-assets inventory",
            "blog-assets analyze",
            "blog-assets pixel-analyze",
            "blog-assets manifest",
        ],
        "read": ["plan", "inventory", "analyze", "pixel-analyze"],
        "prepare": ["manifest"],
        "submit": [],
        "policy": "inventory only by default; shopping reuse manifest requires explicit operator rights confirmation",
    },
    "content": {
        "commands": ["content explore", "content actions"],
        "read": ["explore", "actions"],
        "prepare": [],
        "submit": [],
    },
    "seo": {
        "commands": [
            "seo entrypoints",
            "seo plan",
            "seo assets",
            "seo ownership",
            "seo exposure",
            "seo submit-plan",
            "seo monitor",
            "seo full",
            "seo diagnose",
            "seo submit",
        ],
        "read": ["entrypoints", "plan", "assets", "exposure", "monitor", "diagnose", "full"],
        "prepare": ["ownership", "submit-plan", "searchadvisor prepare"],
        "submit": ["searchadvisor submit"],
    },
    "developers": {
        "commands": ["developers entrypoints", "developers plan"],
        "read": ["entrypoints", "plan"],
        "prepare": ["app registration prepare"],
        "submit": ["app register"],
    },
    "shopping": {
        "commands": ["shopping entrypoints", "shopping competitors"],
        "read": ["entrypoints", "competitors"],
        "prepare": [],
        "submit": [],
    },
    "keyword-tools": {
        "commands": [
            "keyword-tools catalog",
            "keyword-tools plan",
            "keyword-tools datalab",
            "keyword-tools shopping",
            "keyword-tools searchad-plan",
            "keyword-tools paid-blocks",
        ],
        "read": ["catalog", "plan", "datalab", "shopping", "searchad-plan", "paid-blocks"],
        "prepare": [],
        "submit": [],
        "policy": "free-only; paid Naver API, ad campaign, budget, payment, and publish actions are blocked",
    },
    "excel": {
        "commands": ["excel report"],
        "read": ["report"],
        "prepare": ["report"],
        "submit": [],
    },
    "cafe": {
        "commands": [
            "cafe list",
            "cafe home",
            "cafe topic-search",
            "cafe join-request",
            "cafe join-submit",
            "cafe collect",
            "cafe boards",
            "cafe posts",
            "cafe read",
            "cafe write",
            "cafe publish",
        ],
        "read": ["list", "home", "topic-search", "collect", "boards", "posts", "read"],
        "prepare": ["join-request", "write"],
        "submit": ["join-submit", "publish"],
        "api_endpoints": {
            "POST /naver-cafe/collect": "카페 게시글 수집 — params: cafe_url, days(기본90), max_detail(기본300), keyword(검색어, 빈값=전수수집)",
            "POST /naver-cafe/collect-my-cafes": "내 가입 카페 목록 수집",
            "POST /naver-cafe/ai-analyze": "수집글 AI 분석 — params: category, days, max_posts",
            "GET /naver-cafe/articles": "수집 게시글 조회 — params: limit, offset, category",
            "GET /naver-cafe/summary": "수집 현황 요약",
            "GET /naver-cafe/kb": "구조화 지식베이스",
            "GET /naver-cafe/report": "분류 보고서 텍스트",
        },
        "python_entry": "from scripts.naver.cafe import collect_articles, get_my_cafes, run_pipeline, organize, analyze_posts",
        "data_files": "data/cafe/raw_articles_*.json → classified_*.json → organized_kb_*.json",
        "policy": "collect supports keyword filter; topic-search uses Naver search API; join-request is prepare-only; join-submit and publish are approval-gated",
    },
    "calendar": {
        "commands": ["calendar list", "calendar add"],
        "read": ["list"],
        "prepare": ["add"],
        "submit": ["add --save"],
    },
    "mybox": {
        "commands": ["mybox list", "mybox search", "mybox upload"],
        "read": ["list", "search"],
        "prepare": ["upload --dry-run"],
        "submit": ["upload --execute"],
    },
    "pay": {
        "commands": ["pay orders", "pay points"],
        "read": ["orders", "points"],
        "prepare": [],
        "submit": [],
    },
    "talk": {
        "commands": ["talk list", "talk send"],
        "read": ["list"],
        "prepare": ["send"],
        "submit": ["send --execute"],
        "policy": "AI may draft/fill TalkTalk messages, but final send requires explicit approval and NAVER_APPROVED_SEND confirmation",
    },
    "place": {
        "commands": ["place list", "place reviews"],
        "read": ["list", "reviews"],
        "prepare": [],
        "submit": [],
    },
    "smartstore": {
        "commands": ["smartstore actions", "smartstore product list", "smartstore submit"],
        "read": ["actions", "product list", "review list", "inquiry list"],
        "prepare": ["prepare product", "customer reply draft"],
        "submit": ["submit product", "review reply send", "inquiry reply send", "talk message send"],
        "policy": "Product save and customer-visible replies/messages are approval-gated; AI drafting and classification are prepare-only",
    },
}


def build_catalog() -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "site": "naver",
        "approval_policy": {
            "read": "allowed after session and live-safety checks",
            "prepare": "may type or fill only; no external submit without approval",
            "submit": "requires explicit approval flags and confirmation text",
        },
        "features": FEATURE_CATALOG,
    }


def save_catalog(catalog: dict[str, Any] | None = None, output: str | Path | None = None) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(output) if output else LATEST_PATH
    path.write_text(json.dumps(catalog or build_catalog(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_catalog_summary(catalog: dict[str, Any], path: Path) -> None:
    print("Naver service action catalog")
    for name, feature in catalog["features"].items():
        read_count = len(feature.get("read", []))
        prepare_count = len(feature.get("prepare", []))
        submit_count = len(feature.get("submit", []))
        print(f"  {name}: read={read_count} prepare={prepare_count} submit={submit_count}")
    print(f"saved: {path}")
