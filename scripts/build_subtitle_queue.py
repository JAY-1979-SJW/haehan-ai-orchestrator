"""F-4S-9 자막 큐 생성 CLI.

사용 예:
  # fixture 기반
  python scripts/build_subtitle_queue.py \\
    --fixture samples/content_research_fixture.json \\
    --max-items 3 --language ko --json

  # video queue 기반
  python scripts/build_subtitle_queue.py \\
    --video-queue runs/video/video_queue_YYYYMMDD_HHMMSS.json \\
    --worker-result runs/video/worker/web_recording_worker_YYYYMMDD_HHMMSS.json \\
    --max-items 5 --json

금지:
  - STT/TTS API 호출 금지
  - LTX API 호출 금지
  - OAuth / 브라우저 / 영상 파일 읽기 금지
  - YouTube/Naver 업로드 금지
  - .env 커밋 금지
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ai_orchestrator.video_production import subtitle_queue as sq
from ai_orchestrator.video_production import queue_builder as qb

DEFAULT_OUT_DIR = _REPO_ROOT / "runs" / "video" / "subtitles"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="subtitle queue 생성 CLI (F-4S-9)")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--video-queue", metavar="PATH", help="F-4S-6 video_queue JSON")
    src.add_argument("--fixture", metavar="PATH", help="content_research_fixture JSON → 내부에서 video queue 생성")
    parser.add_argument("--recording-queue", metavar="PATH", help="F-4S-7 web_recording_queue JSON (보조)")
    parser.add_argument("--worker-result", metavar="PATH", help="F-4S-8 worker result JSON")
    parser.add_argument("--metadata", metavar="PATH", help="F-4S-8 recording metadata JSON")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--max-items", type=int, default=5)
    parser.add_argument("--language", default="ko")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _load_video_items_from_fixture(fixture_path: str, max_items: int) -> List[Dict[str, Any]]:
    """fixture → queue_builder.build_video_queue → video queue items."""
    try:
        briefs = qb.extract_ltx_briefs(qb.load_content_report(Path(fixture_path)))
        if briefs:
            vq = qb.build_video_queue(briefs, max_items=max_items)
            return sq.extract_video_queue_items(vq)
    except Exception:
        pass

    # fallback: fixture raw items → minimal video item 형태
    fixture = sq.load_json(fixture_path)
    raw_items = fixture.get("items") or []
    video_items = []
    for i, it in enumerate(raw_items[:max_items], start=1):
        title = it.get("title", f"item_{i}")
        summary = it.get("summary", "")[:80] if it.get("summary") else ""
        keyword = it.get("keyword", "")
        video_items.append({
            "queue_id": f"fixture_{i:03d}",
            "title": title,
            "hook": summary[:50] or title,
            "duration_type": "short",
            "scene_plan": [
                {
                    "scene_no": 1,
                    "purpose": "문제 제기",
                    "caption": title[:30],
                    "narration": summary[:50] or title,
                },
                {
                    "scene_no": 2,
                    "purpose": "핵심 정보",
                    "caption": keyword[:20] if keyword else title[:20],
                    "narration": summary[50:100] if len(summary) > 50 else summary,
                },
                {
                    "scene_no": 3,
                    "purpose": "마무리",
                    "caption": "더 자세한 내용은 영상을 확인하세요",
                    "narration": "구독과 좋아요 부탁드립니다",
                },
            ],
            "subtitle_points": [title] if title else [],
            "risk_notes": ["read-only 분석 결과 기반 — 업로드 자동 실행 금지"],
            "review_required": True,
        })
    return video_items


def _load_recording_metadata(args: argparse.Namespace) -> Dict[str, Dict[str, Any]]:
    if args.worker_result:
        data = sq.load_json(args.worker_result)
        return sq.extract_recording_metadata(data)
    if args.metadata:
        data = sq.load_json(args.metadata)
        return sq.extract_recording_metadata(data)
    return {}


def run(args: argparse.Namespace) -> Dict[str, Any]:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.video_queue:
        vq = sq.load_json(args.video_queue)
        video_items = sq.extract_video_queue_items(vq)
    else:
        video_items = _load_video_items_from_fixture(args.fixture, args.max_items)

    rec_meta = _load_recording_metadata(args)

    queue = sq.build_subtitle_queue(
        video_items,
        recording_metadata=rec_meta,
        max_items=args.max_items,
        language=args.language,
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    files = sq.write_subtitle_queue_files(queue, out_dir, timestamp=ts)

    summary: Dict[str, Any] = {
        "subtitle_items_count": queue["total_items"],
        "language": queue["language"],
        "srt_files": files["srt_files"],
        "vtt_files": files["vtt_files"],
        "result_json": str(files["json"]),
        "result_md": str(files["md"]),
        "sample_segments": [
            {
                "subtitle_id": it["subtitle_id"],
                "title": it["title"],
                "segments_count": it["segments_count"],
                "first_segment": it["segments"][0] if it["segments"] else None,
            }
            for it in queue["subtitle_items"][:3]
        ],
        "notes": queue["notes"],
    }
    return {"queue": queue, "files": files, "summary": summary}


def main(argv=None) -> int:
    args = parse_args(argv)
    result = run(args)
    sp = result["summary"]

    if args.json:
        print(json.dumps(sp, ensure_ascii=False, indent=2))
        return 0

    print(f"subtitle_items_count: {sp['subtitle_items_count']}")
    print(f"language:             {sp['language']}")
    print(f"result_json:          {sp['result_json']}")
    print(f"result_md:            {sp['result_md']}")
    for f in sp["srt_files"]:
        print(f"srt: {f}")
    for f in sp["vtt_files"]:
        print(f"vtt: {f}")
    for s in sp["sample_segments"]:
        print(f"  [{s['subtitle_id']}] {s['title']} — {s['segments_count']} segments")
        seg = s.get("first_segment")
        if seg:
            print(f"    {seg['start_seconds']}s → {seg['end_seconds']}s  {seg['text']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
