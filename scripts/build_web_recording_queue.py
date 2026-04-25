"""웹 자동녹화 큐 PoC CLI (F-4S-7).

read-only. 실제 브라우저 실행 / 녹화 / 업로드 일체 수행하지 않는다.

사용 예:
  python scripts/build_web_recording_queue.py \
      --fixture samples/content_research_fixture.json \
      --base-url http://localhost:3000 \
      --max-items 5 --viewport desktop --json

  python scripts/build_web_recording_queue.py \
      --video-queue runs/video/video_queue_20260420_120000.json \
      --base-url http://localhost:3000 --max-items 3
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ai_orchestrator.content_research import report_builder as rb
from ai_orchestrator.video_production import queue_builder as qb
from ai_orchestrator.video_production import recording_queue as rq


DEFAULT_OUT_DIR = "runs/video"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="웹 자동녹화 큐 PoC — 실제 브라우저 실행/녹화 없음 (지시서 큐 생성 전용)",
    )
    parser.add_argument(
        "--video-queue",
        type=str,
        default=None,
        help="F-4S-6 video_queue JSON 경로",
    )
    parser.add_argument(
        "--content-report",
        type=str,
        default=None,
        help="F-4S-5 content research 리포트 JSON (ltx_video_briefs 키 포함)",
    )
    parser.add_argument(
        "--fixture",
        type=str,
        default=None,
        help="fixture JSON (예: samples/content_research_fixture.json)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="대표님 제작 웹/내부 페이지 기본 URL (item.target_url 미지정 시 사용)",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=DEFAULT_OUT_DIR,
        help=f"결과 파일 출력 디렉토리 (default: {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=rq.DEFAULT_MAX_ITEMS,
        help=f"recording 큐 최대 item 수 (default: {rq.DEFAULT_MAX_ITEMS})",
    )
    parser.add_argument(
        "--viewport",
        type=str,
        choices=list(rq.VALID_VIEWPORTS.keys()),
        default=rq.DEFAULT_VIEWPORT,
        help=f"viewport (default: {rq.DEFAULT_VIEWPORT})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="요약을 stdout JSON 으로 출력",
    )
    return parser.parse_args(argv)


def _video_queue_from_fixture(path: Path) -> List[Dict[str, Any]]:
    items, fixture_keywords, _ = rb.load_fixture_items(path)
    if not items:
        return []
    keywords = fixture_keywords
    if not keywords:
        item_kws = [str(it.get("keyword") or "") for it in items if it.get("keyword")]
        keywords = rb.normalize_keywords(item_kws)
    briefs = rb.build_ltx_video_briefs(items, keywords, max_count=20)
    return qb.build_video_queue(briefs, max_items=20)


def _video_queue_from_content_report(path: Path) -> List[Dict[str, Any]]:
    report = qb.load_content_report(path)
    briefs = qb.extract_ltx_briefs(report)
    return qb.build_video_queue(briefs, max_items=20)


def _video_queue_from_path(path: Path) -> List[Dict[str, Any]]:
    data = rq.load_video_queue(path)
    return rq.extract_recording_candidates(data)


def _resolve_input(args: argparse.Namespace) -> tuple:
    inputs_set = sum(1 for f in (args.video_queue, args.content_report, args.fixture) if f)
    if inputs_set == 0:
        raise SystemExit("one of --video-queue / --content-report / --fixture is required")
    if inputs_set > 1:
        raise SystemExit("--video-queue / --content-report / --fixture are mutually exclusive")

    if args.video_queue:
        path = Path(args.video_queue)
        if not path.exists():
            raise SystemExit(f"video queue not found: {path}")
        return _video_queue_from_path(path), f"video_queue:{path.name}"
    if args.content_report:
        path = Path(args.content_report)
        if not path.exists():
            raise SystemExit(f"content report not found: {path}")
        return _video_queue_from_content_report(path), f"content_report:{path.name}"
    path = Path(args.fixture)
    if not path.exists():
        raise SystemExit(f"fixture not found: {path}")
    return _video_queue_from_fixture(path), f"fixture:{path.name}"


def run(args: argparse.Namespace) -> Dict[str, Any]:
    candidates, source_label = _resolve_input(args)
    recording_queue = rq.build_recording_queue(
        candidates,
        default_base_url=args.base_url,
        viewport=args.viewport,
        max_items=args.max_items,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    files = rq.write_recording_queue_files(
        recording_queue, Path(args.out_dir), timestamp=timestamp
    )

    summary_payload = {
        "source": source_label,
        "recording_items_count": len(recording_queue),
        "max_items": args.max_items,
        "viewport": args.viewport,
        "base_url_provided": bool(args.base_url),
        "review_required_count": sum(
            1 for r in recording_queue if r.get("review_required")
        ),
        "missing_target_url_count": sum(
            1 for r in recording_queue if not r.get("target_url")
        ),
        "sample_titles": [r.get("title") for r in recording_queue[:5]],
        "files": {k: str(v) for k, v in files.items()},
        "notes": [
            "실제 브라우저 실행 없음",
            "실제 녹화/업로드/댓글/가입/글쓰기 미수행",
            "click/fill/type/press 단계 미생성",
        ],
    }
    return {
        "recording_queue": recording_queue,
        "files": files,
        "summary_payload": summary_payload,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = run(args)
    summary_payload = result["summary_payload"]
    if args.json:
        print(json.dumps(summary_payload, ensure_ascii=False, indent=2))
    else:
        print(f"source: {summary_payload['source']}")
        print(f"recording_items_count: {summary_payload['recording_items_count']}")
        print(f"max_items: {summary_payload['max_items']}")
        print(f"viewport: {summary_payload['viewport']}")
        print(f"base_url_provided: {summary_payload['base_url_provided']}")
        print(f"review_required_count: {summary_payload['review_required_count']}")
        print(f"missing_target_url_count: {summary_payload['missing_target_url_count']}")
        for t in summary_payload["sample_titles"]:
            print(f"  - {t}")
        print(f"json: {summary_payload['files'].get('json')}")
        print(f"md:   {summary_payload['files'].get('md')}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
