"""YouTube research 공개 API — 책임별 leaf 모듈 aggregator.

search/video/comments/analysis/captions/ops 기능이 각 leaf 에 구현돼 있다.
[docs/module_separation_standard.md]
"""
from __future__ import annotations

from scripts.common.youtube_api_common import (  # noqa: F401
    parse_kv_args, parse_youtube_video_id,
    _api_key, _get_json, _get_json_oauth, _get_text_oauth,
    _now, _stamp, _write_report, _resolve_repo_path, _oauth_token,
    _int, _bounded,
    ROOT, REPORT_DIR, LATEST_SEARCH, LATEST_TRANSCRIPT_PLAN,
    LATEST_ANALYSIS, LATEST_CAPTION_LIST, LATEST_CAPTION_DOWNLOAD,
    LATEST_SCRIPT_COLLECT,
)
from .research_search import (  # noqa: F401
    search_videos, collect_video_info, collect_comments,
    classify_comments, _comment_row,
)
from .research_analysis import (  # noqa: F401
    analyze_video_context, build_video_strategy_scorecard, analyze_transcript,
)
from .research_captions import (  # noqa: F401
    build_transcript_collection_plan, list_captions, download_caption,
    store_full_transcript_file, collect_script_from_url,
)
from .research_ops import (  # noqa: F401
    prepare_comment_plan, build_channel_ops_plan, collect_video_summary_from_url,
    COMMENT_ACTION_POLICY,
)
