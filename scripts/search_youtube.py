"""CLI: YouTube Data API v3 read-only PoC (F-4S-3).

사용법 예:
    # dry-run (실제 호출 없음, 검증만)
    python scripts/search_youtube.py --query "소방공사" --max-results 3

    # 실제 호출 (YOUTUBE_DATA_API_KEY 필요)
    python scripts/search_youtube.py --query "소방공사" --max-results 3 --with-details --live --json

원칙:
- 브라우저 자동화 절대 금지.
- YouTube Studio / 로그인 자동화 절대 금지.
- 업로드 / 수정 / 삭제 / 댓글 작성 흐름 없음.
- API key 출력 금지 — redacted 형식만 노출.
- OAuth 미사용. server API key only.
"""
from __future__ import annotations

import argparse
import json as _json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# repo root import
_THIS = Path(__file__).resolve()
_ROOT = _THIS.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_orchestrator.connectors import youtube_data_api_client as client_mod  # noqa: E402
from ai_orchestrator.connectors import youtube_data_api_config as config_mod  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="search_youtube.py",
        description="YouTube Data API v3 read-only PoC CLI (search.list + videos.list).",
    )
    p.add_argument("--query", required=True, help="검색어 (필수)")
    p.add_argument(
        "--max-results",
        type=int,
        default=5,
        help=f"검색 결과 개수 ({client_mod.MAX_RESULTS_MIN}..{client_mod.MAX_RESULTS_MAX})",
    )
    p.add_argument(
        "--order",
        default="relevance",
        choices=list(client_mod.SEARCH_ORDERS),
        help="정렬",
    )
    p.add_argument(
        "--published-after",
        default=None,
        help="이후 게시 영상만 (RFC3339 또는 YYYY-MM-DD)",
    )
    p.add_argument(
        "--with-details",
        action="store_true",
        help="search 결과 videoId 로 videos.list 호출 (quota +1/영상)",
    )
    p.add_argument("--live", action="store_true", help="실제 API 호출 활성화")
    p.add_argument("--json", action="store_true", help="콘솔에 결과 JSON 출력")
    p.add_argument(
        "--out-dir",
        default="runs/youtube",
        help="결과 저장 폴더 (기본: runs/youtube)",
    )
    return p


def _format_md(
    search_result: Dict[str, Any],
    details_result: Dict[str, Any] | None,
    cfg_summary: Dict[str, Any],
    quota_cost_total: int,
) -> str:
    lines: List[str] = []
    lines.append("# YouTube Data API v3 PoC")
    lines.append("")
    lines.append(f"- mode: `{search_result.get('mode')}`")
    lines.append(f"- query: `{search_result.get('query')}`")
    lines.append(f"- order: {search_result.get('order')}")
    lines.append(f"- max_results: {search_result.get('max_results')}")
    lines.append(f"- published_after: {search_result.get('published_after')}")
    lines.append(f"- search_items_count: {len(search_result.get('items') or [])}")
    if details_result is not None:
        lines.append(f"- details_items_count: {len(details_result.get('items') or [])}")
    lines.append(f"- quota_cost_total: {quota_cost_total}")
    warns: List[str] = list(search_result.get("warnings") or [])
    if details_result is not None:
        warns.extend(details_result.get("warnings") or [])
    if warns:
        lines.append("")
        lines.append("## warnings")
        for w in warns:
            lines.append(f"- {w}")
    err = search_result.get("error")
    if err:
        lines.append("")
        lines.append(f"## search error: {err}")
    if details_result is not None and details_result.get("error"):
        lines.append("")
        lines.append(f"## details error: {details_result.get('error')}")
    lines.append("")
    lines.append("## config (redacted)")
    for k, v in cfg_summary.items():
        lines.append(f"- {k}: {v}")
    items = search_result.get("items") or []
    if items:
        lines.append("")
        lines.append("## search items")
        for idx, item in enumerate(items, start=1):
            title = item.get("title") or ""
            video_id = item.get("videoId") or ""
            channel = item.get("channelTitle") or ""
            published = item.get("publishedAt") or ""
            lines.append(f"{idx}. {title}")
            if video_id:
                lines.append(f"   - videoId: {video_id}")
            if channel:
                lines.append(f"   - channel: {channel}")
            if published:
                lines.append(f"   - publishedAt: {published}")
    if details_result is not None:
        d_items = details_result.get("items") or []
        if d_items:
            lines.append("")
            lines.append("## video details")
            for idx, item in enumerate(d_items, start=1):
                title = item.get("title") or ""
                video_id = item.get("videoId") or ""
                view_count = item.get("viewCount") or ""
                like_count = item.get("likeCount") or ""
                comment_count = item.get("commentCount") or ""
                duration = item.get("duration") or ""
                lines.append(f"{idx}. {title}")
                if video_id:
                    lines.append(f"   - videoId: {video_id}")
                if view_count:
                    lines.append(f"   - viewCount: {view_count}")
                if like_count:
                    lines.append(f"   - likeCount: {like_count}")
                if comment_count:
                    lines.append(f"   - commentCount: {comment_count}")
                if duration:
                    lines.append(f"   - duration: {duration}")
    return "\n".join(lines) + "\n"


def _write_outputs(
    out_dir: Path,
    payload: Dict[str, Any],
    md_text: str,
) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"youtube_search_{ts}.json"
    md_path = out_dir / f"youtube_search_{ts}.md"
    json_path.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


def run(argv: List[str]) -> int:
    args = _build_parser().parse_args(argv)
    cfg = config_mod.load_youtube_data_api_config()
    cfg_summary = cfg.redacted()

    cli_warnings: List[str] = []
    if args.live and not cfg.live_enabled:
        cli_warnings.append(
            "WARN: --live requested but YOUTUBE_DATA_API_KEY missing — falling back to mock_or_disabled"
        )

    try:
        search_result = client_mod.search_videos(
            query=args.query,
            max_results=args.max_results,
            order=args.order,
            published_after=args.published_after,
            live=args.live,
            config=cfg,
        )
    except ValueError as exc:
        search_result = {
            "success": False,
            "mode": "mock_or_disabled",
            "kind": "search",
            "query": args.query,
            "max_results": args.max_results,
            "order": args.order,
            "published_after": args.published_after,
            "quota_cost": 0,
            "items": [],
            "error": f"validation_error: {exc}",
            "warnings": cli_warnings,
        }
        print(f"[search_youtube] validation_error: {exc}", file=sys.stderr)
        for w in cli_warnings:
            print(f"[search_youtube] {w}", file=sys.stderr)
        out_dir = Path(args.out_dir)
        payload = {"config": cfg_summary, "search": search_result, "details": None, "quota_cost_total": 0}
        paths = _write_outputs(out_dir, payload, _format_md(search_result, None, cfg_summary, 0))
        print(f"[search_youtube] json -> {paths['json']}")
        print(f"[search_youtube] md   -> {paths['md']}")
        return 2

    if cli_warnings:
        existing = list(search_result.get("warnings") or [])
        existing.extend(cli_warnings)
        search_result["warnings"] = existing

    details_result: Dict[str, Any] | None = None
    if args.with_details:
        # search 결과에서 videoId 추출 (live 또는 mock 모두 대비). mock 결과는 빈 ids → 검증 에러 → skip
        ids = [
            item.get("videoId")
            for item in (search_result.get("items") or [])
            if isinstance(item, dict) and item.get("videoId")
        ]
        if ids:
            try:
                details_result = client_mod.get_video_details(
                    video_ids=ids,
                    live=args.live,
                    config=cfg,
                )
            except ValueError as exc:
                details_result = {
                    "success": False,
                    "mode": "mock_or_disabled",
                    "kind": "videos",
                    "video_ids": ids,
                    "quota_cost": 0,
                    "items": [],
                    "error": f"validation_error: {exc}",
                    "warnings": [],
                }
                print(f"[search_youtube] details validation_error: {exc}", file=sys.stderr)
        else:
            details_result = {
                "success": True,
                "mode": "mock_or_disabled",
                "kind": "videos",
                "video_ids": [],
                "quota_cost": 0,
                "items": [],
                "warnings": ["--with-details: no videoIds returned (likely dry-run/mock)"],
            }

    quota_cost_total = int(search_result.get("quota_cost") or 0) + int(
        (details_result.get("quota_cost") or 0) if details_result else 0
    )

    out_dir = Path(args.out_dir)
    payload = {
        "config": cfg_summary,
        "search": search_result,
        "details": details_result,
        "quota_cost_total": quota_cost_total,
    }
    md_text = _format_md(search_result, details_result, cfg_summary, quota_cost_total)
    paths = _write_outputs(out_dir, payload, md_text)

    s_items = len(search_result.get("items") or [])
    d_items = len(details_result.get("items") or []) if details_result else 0
    print(
        f"[search_youtube] mode={search_result.get('mode')} "
        f"search_items={s_items} details_items={d_items} "
        f"quota_cost_total={quota_cost_total}"
    )
    for w in (search_result.get("warnings") or []):
        print(f"[search_youtube] WARN: {w}")
    if details_result:
        for w in (details_result.get("warnings") or []):
            print(f"[search_youtube] details WARN: {w}")
    print(f"[search_youtube] json -> {paths['json']}")
    print(f"[search_youtube] md   -> {paths['md']}")

    if args.json:
        print(_json.dumps(payload, ensure_ascii=False, indent=2))

    success = bool(search_result.get("success")) and (
        details_result is None or bool(details_result.get("success"))
    )
    return 0 if success else 1


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
