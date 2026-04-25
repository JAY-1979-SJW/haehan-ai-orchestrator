"""LTX 영상 제작 큐 PoC CLI (F-4S-6).

read-only 큐 생성기. 실제 LTX API 호출 / 영상 생성 / 업로드는 절대 수행하지 않는다.

사용 예:
  python scripts/build_video_queue.py \
      --fixture samples/content_research_fixture.json \
      --max-items 5 --duration short --json

  python scripts/build_video_queue.py \
      --content-report runs/content/content_research_20260420_120000.json \
      --max-items 3
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


DEFAULT_OUT_DIR = "runs/video"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LTX 영상 제작 큐 PoC — read-only, 실제 LTX 호출 없음",
    )
    parser.add_argument(
        "--content-report",
        type=str,
        default=None,
        help="F-4S-5 콘텐츠 조사 리포트 JSON 경로 (ltx_video_briefs 키 포함)",
    )
    parser.add_argument(
        "--fixture",
        type=str,
        default=None,
        help="content research fixture JSON (예: samples/content_research_fixture.json)",
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
        default=qb.DEFAULT_MAX_ITEMS,
        help=f"큐 최대 item 수 (default: {qb.DEFAULT_MAX_ITEMS})",
    )
    parser.add_argument(
        "--duration",
        type=str,
        choices=list(qb.VALID_DURATION_TYPES),
        default=qb.DEFAULT_DURATION_TYPE,
        help="기본 duration_type (target_platform 으로 추론 안 될 때 사용)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="요약을 stdout JSON 으로 출력",
    )
    return parser.parse_args(argv)


def _briefs_from_fixture(path: Path) -> List[Dict[str, Any]]:
    items, fixture_keywords, _ = rb.load_fixture_items(path)
    if not items:
        return []
    keywords = fixture_keywords
    if not keywords:
        item_kws = [str(it.get("keyword") or "") for it in items if it.get("keyword")]
        keywords = rb.normalize_keywords(item_kws)
    briefs = rb.build_ltx_video_briefs(items, keywords, max_count=20)
    return briefs


def _briefs_from_content_report(path: Path) -> List[Dict[str, Any]]:
    report = qb.load_content_report(path)
    return qb.extract_ltx_briefs(report)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    if not args.content_report and not args.fixture:
        raise SystemExit("either --content-report or --fixture is required")
    if args.content_report and args.fixture:
        raise SystemExit("--content-report and --fixture are mutually exclusive")

    if args.content_report:
        path = Path(args.content_report)
        if not path.exists():
            raise SystemExit(f"content report not found: {path}")
        briefs = _briefs_from_content_report(path)
        source_label = f"content_report:{path.name}"
    else:
        path = Path(args.fixture)
        if not path.exists():
            raise SystemExit(f"fixture not found: {path}")
        briefs = _briefs_from_fixture(path)
        source_label = f"fixture:{path.name}"

    queue = qb.build_video_queue(
        briefs,
        default_duration_type=args.duration,
        max_items=args.max_items,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    files = qb.write_video_queue_files(queue, Path(args.out_dir), timestamp=timestamp)

    summary_payload = {
        "source": source_label,
        "queue_items_count": len(queue),
        "max_items": args.max_items,
        "default_duration_type": args.duration,
        "review_required_count": sum(1 for q in queue if q.get("review_required")),
        "sample_titles": [q.get("title") for q in queue[:5]],
        "files": {k: str(v) for k, v in files.items()},
        "notes": [
            "실제 LTX 호출 없음",
            "영상 생성/업로드/댓글/가입/글쓰기 미수행",
        ],
    }
    return {
        "queue": queue,
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
        print(f"queue_items_count: {summary_payload['queue_items_count']}")
        print(f"max_items: {summary_payload['max_items']}")
        print(f"default_duration_type: {summary_payload['default_duration_type']}")
        print(f"review_required_count: {summary_payload['review_required_count']}")
        for t in summary_payload["sample_titles"]:
            print(f"  - {t}")
        print(f"json: {summary_payload['files'].get('json')}")
        print(f"md:   {summary_payload['files'].get('md')}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
