"""YouTube video search 공개 API — 책임별 leaf 모듈 aggregator.

search/analyze/score/transcript 기능이 각 leaf 에 구현돼 있다.
[docs/module_separation_standard.md]
"""
from __future__ import annotations
import json  # noqa: F401 — tests access search.json
import urllib  # noqa: F401 — tests access search.urllib.*
import urllib.error  # noqa: F401
import urllib.parse  # noqa: F401
import urllib.request  # noqa: F401

from .search_common import (  # noqa: F401
    build_public_signal_model, build_search_url,
    _api_key, _get_json, _oauth_access_token, _now, _stamp, _write_report,
    _urlopen_with_dead_proxy_fallback,
    ROOT, REPORT_DIR, LATEST_SEARCH, LATEST_ANALYSIS,
    LATEST_TOPIC_ANALYSIS, LATEST_MARKET_RESEARCH, MARKET_RESEARCH_REPORT_DIR,
    YOUTUBE_SEARCH_URL,
)
from scripts.browser.cdp.cdp_console import connect  # noqa: F401 — tests monkeypatch search.connect
from .search_search import (  # noqa: F401
    search_videos, search_videos_official, search_videos_browser,
    extract_browser_search_results,
    _sanitize_browser_snapshot, _load_search_payload,
)
from .search_analyze import (  # noqa: F401
    analyze_ranked_videos, analyze_keyword_topic_market,
    expand_topic_keywords, run_market_research, collect_public_comment_summary,
)
from .search_transcript import (  # noqa: F401
    collect_visible_transcript_summary, summarize_transcript_segments,
)
from .search_score import (  # noqa: F401
    _score_video, _strategy_summary, _why_it_matters,
)
