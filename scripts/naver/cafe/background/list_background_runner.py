"""Attach-only background runner for Naver Cafe list collection."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.common.app_paths import repo_root

ROOT = repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.browser.session.browser_cdp_selection_gate import (  # noqa: E402
    create_isolated_target,
    evaluate_sessions,  # noqa: F401 - tests/naver_cafe/test_naver_cafe_list_collector.py 가 runner.evaluate_sessions 로 접근
    select_naver_session,
)
from scripts.naver.cafe import (  # noqa: E402
    join_request,
    list_collector,
    main_page,
    member_collect,
    topic_search,
)
from scripts.naver.mail.read import cdp  # noqa: E402

CAFE_WORK_START_URLS = {
    "list": "https://section.cafe.naver.com/ca-fe/home",
    "main": "https://section.cafe.naver.com/ca-fe/home",
    "topic-search": "https://search.naver.com/search.naver?where=article&query=naver%20cafe",
}


@dataclass
class CafeListBackgroundReport:
    ok: bool
    code: str
    port: int | None = None
    target_id: str = ""
    url: str = ""
    title: str = ""
    joined_total: int = 0
    favorite_total: int = 0
    manage_total: int = 0
    cafes: list[dict[str, Any]] = field(default_factory=list)
    favorites: list[dict[str, Any]] = field(default_factory=list)
    manages: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CafeMainBackgroundReport:
    ok: bool
    code: str
    port: int | None = None
    target_id: str = ""
    url: str = ""
    title: str = ""
    user: dict[str, Any] = field(default_factory=dict)
    endpoint_statuses: dict[str, dict[str, Any]] = field(default_factory=dict)
    sections: dict[str, Any] = field(default_factory=dict)
    features: list[dict[str, Any]] = field(default_factory=list)
    action_plans: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CafeTopicSearchBackgroundReport:
    ok: bool
    code: str
    port: int | None = None
    target_id: str = ""
    url: str = ""
    title: str = ""
    keywords: list[str] = field(default_factory=list)
    total_items: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)
    keyword_counts: dict[str, int] = field(default_factory=dict)
    top_cafes: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JoinedCafeBackgroundReport:
    ok: bool
    code: str
    port: int | None = None
    target_id: str = ""
    url: str = ""
    title: str = ""
    cafe_url: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def find_cafe_target_id(*, port: int) -> tuple[str, dict[str, Any]]:
    pages = cdp.list_pages(port=port)
    for page in pages:
        url = str(page.get("url") or "")
        if "section.cafe.naver.com" in url:
            return str(page.get("id") or ""), page
    for page in pages:
        url = str(page.get("url") or "")
        if "naver.com" in url and "nid.naver.com" not in url:
            return str(page.get("id") or ""), page
    for page in pages:
        url = str(page.get("url") or "")
        if "naver.com" in url:
            return str(page.get("id") or ""), page
    return "", {}


def create_isolated_cafe_target(*, port: int, work: str, cafe_url: str = "") -> tuple[str, dict[str, Any]]:
    """Create a dedicated tab for one Naver Cafe workflow.

    The CDP browser process is shared, but the target tab is not. This prevents
    concurrent cafe commands from navigating the same tab and contaminating each
    other's DOM extraction.
    """
    safe_cafe = member_collect.normalize_cafe_url(cafe_url) if cafe_url else ""
    if safe_cafe:
        start_url = f"https://cafe.naver.com/{safe_cafe}"
    else:
        start_url = CAFE_WORK_START_URLS.get(work, "https://section.cafe.naver.com/ca-fe/home")
    report = create_isolated_target(task="naver", work=f"cafe:{work}", port=port, start_url=start_url)
    if not report.ok or not report.target_id:
        return "", {}
    return report.target_id, report.page


def collect_background(
    *,
    allow_mixed_readonly: bool = False,
    per_page: int = 100,
) -> CafeListBackgroundReport:
    session, selection = select_naver_session(allow_mixed_readonly=allow_mixed_readonly)
    if session is None:
        return CafeListBackgroundReport(
            ok=False,
            code=selection.code,
            messages=list(selection.messages),
            selection=selection.to_dict(),
        )

    target_id, page = create_isolated_cafe_target(port=session.port, work="list")
    if not target_id:
        return CafeListBackgroundReport(
            ok=False,
            code="no_naver_target",
            port=session.port,
            messages=["Could not create an isolated Naver Cafe CDP target tab."],
            selection=selection.to_dict(),
        )

    report = list_collector.collect_cafe_list_from_target(target_id, port=session.port, per_page=per_page)
    current = next((p for p in cdp.list_pages(session.port) if p.get("id") == target_id), page)
    return CafeListBackgroundReport(
        ok=report.ok,
        code=report.code,
        port=session.port,
        target_id=target_id,
        url=str((current or {}).get("url") or ""),
        title=str((current or {}).get("title") or ""),
        joined_total=report.joined_total,
        favorite_total=report.favorite_total,
        manage_total=report.manage_total,
        cafes=[item.to_dict() for item in report.joined],
        favorites=[item.to_dict() for item in report.favorites],
        manages=[item.to_dict() for item in report.manages],
        messages=[
            "Created an isolated tab in the existing Naver CDP session; no browser launch, restart, close, write, or publish action.",
            *report.messages,
        ],
        selection=selection.to_dict(),
    )


def collect_main_background(
    *,
    allow_mixed_readonly: bool = False,
) -> CafeMainBackgroundReport:
    session, selection = select_naver_session(allow_mixed_readonly=allow_mixed_readonly)
    if session is None:
        return CafeMainBackgroundReport(
            ok=False,
            code=selection.code,
            messages=list(selection.messages),
            selection=selection.to_dict(),
        )

    target_id, page = create_isolated_cafe_target(port=session.port, work="main")
    if not target_id:
        return CafeMainBackgroundReport(
            ok=False,
            code="no_naver_target",
            port=session.port,
            messages=["Could not create an isolated Naver Cafe CDP target tab."],
            selection=selection.to_dict(),
        )

    report = main_page.collect_main_from_target(target_id, port=session.port)
    current = next((p for p in cdp.list_pages(session.port) if p.get("id") == target_id), page)
    return CafeMainBackgroundReport(
        ok=report.ok,
        code=report.code,
        port=session.port,
        target_id=target_id,
        url=str((current or {}).get("url") or report.href),
        title=str((current or {}).get("title") or report.title),
        user=report.user,
        endpoint_statuses=report.endpoint_statuses,
        sections=report.sections,
        features=[feature.to_dict() for feature in report.features],
        action_plans=[plan.to_dict() for plan in report.action_plans],
        messages=[
            "Created an isolated tab in the existing Naver CDP session; no browser launch, restart, close, write, or publish action.",
            *report.messages,
        ],
        selection=selection.to_dict(),
    )


def collect_topic_search_background(
    *,
    allow_mixed_readonly: bool = False,
    keywords: str | list[str] | tuple[str, ...] | None = None,
    limit_per_keyword: int = 10,
) -> CafeTopicSearchBackgroundReport:
    session, selection = select_naver_session(allow_mixed_readonly=allow_mixed_readonly)
    if session is None:
        return CafeTopicSearchBackgroundReport(
            ok=False,
            code=selection.code,
            messages=list(selection.messages),
            selection=selection.to_dict(),
        )

    target_id, page = create_isolated_cafe_target(port=session.port, work="topic-search")
    if not target_id:
        return CafeTopicSearchBackgroundReport(
            ok=False,
            code="no_naver_target",
            port=session.port,
            messages=["Could not create an isolated Naver Cafe CDP target tab."],
            selection=selection.to_dict(),
        )

    report = topic_search.collect_topic_search_from_target(
        target_id,
        port=session.port,
        keywords=keywords,
        limit_per_keyword=limit_per_keyword,
    )
    current = next((p for p in cdp.list_pages(session.port) if p.get("id") == target_id), page)
    return CafeTopicSearchBackgroundReport(
        ok=report.ok,
        code=report.code,
        port=session.port,
        target_id=target_id,
        url=str((current or {}).get("url") or ""),
        title=str((current or {}).get("title") or ""),
        keywords=report.keywords,
        total_items=report.total_items,
        items=[item.to_dict() for item in report.items],
        keyword_counts=report.keyword_counts,
        top_cafes=report.top_cafes,
        messages=[
            "Created an isolated tab in the existing Naver CDP session; no browser launch, restart, close, write, or publish action.",
            *report.messages,
        ],
        selection=selection.to_dict(),
    )


def collect_joined_cafe_background(
    *,
    cafe_url: str,
    mode: str = "home",
    allow_mixed_readonly: bool = False,
    nickname: str = "",
    purpose: str = "",
    answers: dict[str, str] | None = None,
) -> JoinedCafeBackgroundReport:
    session, selection = select_naver_session(allow_mixed_readonly=allow_mixed_readonly)
    if session is None:
        return JoinedCafeBackgroundReport(
            ok=False,
            code=selection.code,
            cafe_url=cafe_url,
            messages=list(selection.messages),
            selection=selection.to_dict(),
        )

    target_id, page = create_isolated_cafe_target(port=session.port, work=mode, cafe_url=cafe_url)
    if not target_id:
        return JoinedCafeBackgroundReport(
            ok=False,
            code="no_naver_target",
            port=session.port,
            cafe_url=cafe_url,
            messages=["Could not create an isolated Naver Cafe CDP target tab."],
            selection=selection.to_dict(),
        )

    report: Any
    if mode == "boards":
        report = member_collect.collect_boards_from_target(target_id, port=session.port, cafe_url=cafe_url)
    elif mode == "join-request":
        report = join_request.inspect_join_request_from_target(
            target_id,
            port=session.port,
            cafe_url=cafe_url,
            nickname=nickname,
            purpose=purpose,
            answers=answers,
        )
    else:
        report = member_collect.collect_home_from_target(target_id, port=session.port, cafe_url=cafe_url)
    current = next((p for p in cdp.list_pages(session.port) if p.get("id") == target_id), page)
    return JoinedCafeBackgroundReport(
        ok=report.ok,
        code=report.code,
        port=session.port,
        target_id=target_id,
        url=str((current or {}).get("url") or ""),
        title=str((current or {}).get("title") or ""),
        cafe_url=cafe_url,
        payload=report.to_dict(),
        messages=[
            "Created an isolated tab in the existing Naver CDP session; no browser launch, restart, close, write, comment, or publish action.",
            *report.messages,
        ],
        selection=selection.to_dict(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run attach-only Naver Cafe collection.")
    parser.add_argument("--allow-mixed-readonly", action="store_true")
    parser.add_argument("--per-page", type=int, default=100)
    parser.add_argument("--mode", choices=("list", "main", "topic-search"), default="list")
    parser.add_argument("--query", "--keywords", dest="keywords", default="")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)

    report: Any
    if args.mode == "main":
        report = collect_main_background(allow_mixed_readonly=args.allow_mixed_readonly)
    elif args.mode == "topic-search":
        report = collect_topic_search_background(
            allow_mixed_readonly=args.allow_mixed_readonly,
            keywords=args.keywords,
            limit_per_keyword=args.limit,
        )
    else:
        report = collect_background(
            allow_mixed_readonly=args.allow_mixed_readonly,
            per_page=args.per_page,
        )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
