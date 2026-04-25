"""Naver + YouTube 통합 콘텐츠 조사 리포트 CLI (F-4S-4).

read-only PoC. 키 미설정 시 mock_or_disabled 결과로 리포트 구조만 생성.
브라우저 자동화 / OAuth / write 작업 미수행.

사용 예:
  python scripts/research_content.py --keyword "소방공사" \
      --naver-types blog,news,cafearticle \
      --youtube-with-details

  python scripts/research_content.py --keywords-file kw.txt --live --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# 패키지 임포트가 가능하도록 repo root 를 sys.path 에 보장
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ai_orchestrator.connectors import naver_search_api_config as naver_cfg_mod
from ai_orchestrator.connectors import youtube_data_api_config as yt_cfg_mod
from ai_orchestrator.content_research import report_builder as rb


DEFAULT_NAVER_TYPES = "blog,news,cafearticle"
DEFAULT_OUT_DIR = "runs/content"


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _read_keywords_file(path: Path) -> List[str]:
    text = path.read_text(encoding="utf-8")
    out: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(stripped)
    return out


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Naver + YouTube 통합 콘텐츠 조사 리포트 (read-only PoC)",
    )
    parser.add_argument("--keyword", action="append", default=[], help="조사 키워드 (반복 가능)")
    parser.add_argument("--keywords-file", type=str, default=None, help="키워드 목록 파일 (한 줄에 하나)")
    parser.add_argument(
        "--naver-types",
        type=str,
        default=DEFAULT_NAVER_TYPES,
        help=f"네이버 검색 종류 콤마 분리 (default: {DEFAULT_NAVER_TYPES})",
    )
    parser.add_argument("--naver-display", type=int, default=rb.DEFAULT_NAVER_DISPLAY)
    parser.add_argument("--youtube-max-results", type=int, default=rb.DEFAULT_YOUTUBE_MAX)
    parser.add_argument("--youtube-with-details", action="store_true", default=False)
    parser.add_argument("--live", action="store_true", default=False)
    parser.add_argument("--json", action="store_true", default=False, help="요약을 stdout JSON 으로 출력")
    parser.add_argument("--out-dir", type=str, default=DEFAULT_OUT_DIR)
    return parser.parse_args(argv)


def _gather_keywords(args: argparse.Namespace) -> List[str]:
    raw: List[str] = []
    raw.extend(args.keyword or [])
    if args.keywords_file:
        path = Path(args.keywords_file)
        if not path.exists():
            raise SystemExit(f"keywords-file not found: {path}")
        raw.extend(_read_keywords_file(path))
    return rb.normalize_keywords(raw)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    keywords = _gather_keywords(args)
    if not keywords:
        raise SystemExit("at least one keyword is required (--keyword or --keywords-file)")

    naver_cfg = naver_cfg_mod.load_naver_search_api_config()
    yt_cfg = yt_cfg_mod.load_youtube_data_api_config()

    platforms_attempted = ["naver", "youtube"]
    platforms_live: List[str] = []
    if args.live and naver_cfg.live_enabled:
        platforms_live.append("naver")
    if args.live and yt_cfg.live_enabled:
        platforms_live.append("youtube")

    naver_types = _split_csv(args.naver_types) or list(rb.DEFAULT_NAVER_TYPES)

    extra_warnings: List[str] = []
    if args.live and not naver_cfg.live_enabled:
        extra_warnings.append("naver:live=True but NAVER_CLIENT_ID/SECRET missing — mock_or_disabled")
    if args.live and not yt_cfg.live_enabled:
        extra_warnings.append("youtube:live=True but YOUTUBE_DATA_API_KEY missing — mock_or_disabled")
    if not args.live:
        extra_warnings.append("global:live=False — all calls returned mock_or_disabled (no API)")

    naver_blocks: List[Dict[str, Any]] = []
    youtube_blocks: List[Dict[str, Any]] = []

    for kw in keywords:
        naver_blocks.append(
            rb.collect_naver_results(
                keyword=kw,
                search_types=naver_types,
                display=args.naver_display,
                live=args.live,
                config=naver_cfg,
            )
        )
        youtube_blocks.append(
            rb.collect_youtube_results(
                keyword=kw,
                max_results=args.youtube_max_results,
                with_details=bool(args.youtube_with_details),
                live=args.live,
                config=yt_cfg,
            )
        )

    mode = "live" if args.live else "dry_run"
    report = rb.build_report(
        keywords=keywords,
        naver_blocks=naver_blocks,
        youtube_blocks=youtube_blocks,
        mode=mode,
        platforms_attempted=platforms_attempted,
        platforms_live=platforms_live,
        extra_warnings=extra_warnings,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_paths = rb.write_report_files(report, Path(args.out_dir), timestamp=timestamp)

    summary_payload = {
        "summary": report["summary"],
        "warnings_count": len(report.get("warnings") or []),
        "files": {k: str(v) for k, v in out_paths.items()},
        "mode": mode,
    }
    return {
        "report": report,
        "files": out_paths,
        "summary_payload": summary_payload,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = run(args)
    summary_payload = result["summary_payload"]

    if args.json:
        print(json.dumps(summary_payload, ensure_ascii=False, indent=2))
    else:
        files = summary_payload["files"]
        summary = summary_payload["summary"]
        print(f"mode: {summary_payload['mode']}")
        print(f"keywords_count: {summary.get('keywords_count')}")
        print(f"total_items: {summary.get('total_items')}")
        print(f"naver_items: {summary.get('naver_items')}")
        print(f"youtube_items: {summary.get('youtube_items')}")
        print(f"warnings_count: {summary_payload['warnings_count']}")
        print(f"json: {files.get('json')}")
        print(f"csv:  {files.get('csv')}")
        print(f"md:   {files.get('md')}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
