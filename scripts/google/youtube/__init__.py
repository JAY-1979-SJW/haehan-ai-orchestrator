"""Google YouTube sub-tab package."""

from __future__ import annotations

from scripts.google.common.domain_taxonomy import build_google_domain_taxonomy
from scripts.google.common.tab_logic import build_tab_logic_catalog, classify_tab_operation, get_tab_summary
from scripts.google.youtube import search as search_module
from scripts.google.youtube.search import search_videos
from scripts.google.common.youtube_upload import build_youtube_upload_plan

TAB_KEY = "youtube"


def summary() -> dict:
    return get_tab_summary(TAB_KEY)


def catalog() -> dict:
    return build_tab_logic_catalog(TAB_KEY)


def classify_operation(key_or_host: str = "www.youtube.com", operation: str = "read") -> dict:
    return classify_tab_operation(TAB_KEY, key_or_host, operation)


def page_tabs() -> dict:
    taxonomy = build_google_domain_taxonomy()
    surfaces = [item for item in taxonomy["domains"] if item["surface_key"] in {"youtube", "youtube_studio"}]
    return {
        "site_id": "google",
        "tab_key": TAB_KEY,
        "surface_count": len(surfaces),
        "page_tab_count": sum(len(item["page_tabs"]) for item in surfaces),
        "surfaces": surfaces,
    }


def upload_plan(values: dict[str, str]) -> dict:
    return build_youtube_upload_plan(values)


def video_search(
    query: str,
    *,
    max_results: int = 10,
    source: str = "auto",
    wait_seconds: float = 3.0,
) -> tuple[dict, object]:
    return search_videos(query, max_results=max_results, source=source, wait_seconds=wait_seconds)


def rank_analysis(
    *,
    query: str = "",
    search_report_path: str | None = None,
    max_videos: int = 5,
    collect_transcripts: bool = True,
    wait_seconds: float = 3.0,
) -> tuple[dict, object]:
    return search_module.analyze_ranked_videos(
        query=query,
        search_report_path=search_report_path,
        max_videos=max_videos,
        collect_transcripts=collect_transcripts,
        wait_seconds=wait_seconds,
    )


def topic_analysis(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    keywords: list[str],
    *,
    per_keyword_limit: int = 10,
    source: str = "auto",
    collect_transcripts: bool = False,
    max_transcript_videos: int = 5,
    collect_comments: bool = False,
    max_comment_videos: int = 5,
    max_comments: int = 20,
    max_comment_pages: int = 1,
    include_comment_replies: bool = False,
    wait_seconds: float = 3.0,
    order: str = "relevance",
    published_after: str | None = None,
) -> tuple[dict, object]:
    return search_module.analyze_keyword_topic_market(
        keywords,
        per_keyword_limit=per_keyword_limit,
        source=source,
        collect_transcripts=collect_transcripts,
        max_transcript_videos=max_transcript_videos,
        collect_comments=collect_comments,
        max_comment_videos=max_comment_videos,
        max_comments=max_comments,
        max_comment_pages=max_comment_pages,
        include_comment_replies=include_comment_replies,
        wait_seconds=wait_seconds,
        order=order,
        published_after=published_after,
    )


def market_research_run(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    *,
    topic: str = "",
    keywords: list[str] | None = None,
    auto_keywords: bool = True,
    per_keyword_limit: int = 10,
    source: str = "auto",
    collect_transcripts: bool = False,
    max_transcript_videos: int = 5,
    collect_comments: bool = True,
    max_comment_videos: int = 5,
    max_comments: int = 20,
    max_comment_pages: int = 1,
    include_comment_replies: bool = False,
    wait_seconds: float = 3.0,
    order: str = "relevance",
    published_after: str | None = None,
) -> tuple[dict, object, object]:
    return search_module.run_market_research(
        topic=topic,
        keywords=keywords or [],
        auto_keywords=auto_keywords,
        per_keyword_limit=per_keyword_limit,
        source=source,
        collect_transcripts=collect_transcripts,
        max_transcript_videos=max_transcript_videos,
        collect_comments=collect_comments,
        max_comment_videos=max_comment_videos,
        max_comments=max_comments,
        max_comment_pages=max_comment_pages,
        include_comment_replies=include_comment_replies,
        wait_seconds=wait_seconds,
        order=order,
        published_after=published_after,
    )


def expand_topic_keywords(topic: str, *, auto_keywords: bool = True) -> list[str]:
    return search_module.expand_topic_keywords(topic, auto_keywords=auto_keywords)


def public_signal_model() -> dict:
    return search_module.build_public_signal_model()
