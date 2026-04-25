"""F-4S-10 TTS 큐 생성 CLI.

사용 예:
  # fixture 기반
  python scripts/build_tts_queue.py \\
    --fixture samples/content_research_fixture.json \\
    --voice-profile ko_male_neutral --max-items 3 --json

  # subtitle queue 기반
  python scripts/build_tts_queue.py \\
    --subtitle-queue runs/video/subtitles/subtitle_queue_YYYYMMDD_HHMMSS.json \\
    --voice-profile ko_female_neutral --json

  # SRT 단독
  python scripts/build_tts_queue.py \\
    --srt runs/video/subtitles/subtitle_001.srt --json

금지: 실제 TTS/STT/LTX API 호출 / 실제 음성 파일 생성 / OAuth / 브라우저 / 업로드
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

from ai_orchestrator.video_production import tts_queue as tq
from ai_orchestrator.video_production import subtitle_queue as sq
from ai_orchestrator.video_production import queue_builder as qb

DEFAULT_OUT_DIR = _REPO_ROOT / "runs" / "video" / "tts"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="TTS 큐 생성 CLI (F-4S-10)")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--subtitle-queue", metavar="PATH", help="F-4S-9 subtitle_queue JSON")
    src.add_argument("--srt", metavar="PATH", help="SRT 파일 단독 입력")
    src.add_argument("--vtt", metavar="PATH", help="VTT 파일 단독 입력")
    src.add_argument("--fixture", metavar="PATH", help="content_research_fixture JSON")
    parser.add_argument("--video-queue", metavar="PATH", help="F-4S-6 video_queue JSON (보조)")
    parser.add_argument(
        "--voice-profile",
        default=tq.DEFAULT_VOICE_PROFILE,
        choices=list(tq.VALID_VOICE_PROFILES),
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--max-items", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _subtitle_items_from_fixture(fixture_path: str, max_items: int) -> List[Dict[str, Any]]:
    """fixture → subtitle queue items."""
    try:
        briefs = qb.extract_ltx_briefs(qb.load_content_report(Path(fixture_path)))
        if briefs:
            vq = qb.build_video_queue(briefs, max_items=max_items)
            video_items = sq.extract_video_queue_items(vq)
            sub_q = sq.build_subtitle_queue(video_items, max_items=max_items)
            return sub_q.get("subtitle_items") or []
    except Exception:
        pass

    # fallback: fixture raw items
    fixture = sq.load_json(fixture_path)
    raw_items = fixture.get("items") or []
    video_items = []
    for i, it in enumerate(raw_items[:max_items], start=1):
        title = it.get("title", f"item_{i}")
        summary = (it.get("summary") or "")[:80]
        video_items.append({
            "queue_id": f"fixture_{i:03d}",
            "title": title,
            "hook": summary[:50] or title,
            "duration_type": "short",
            "scene_plan": [
                {"scene_no": 1, "purpose": "문제 제기", "caption": title[:30], "narration": summary[:50] or title},
                {"scene_no": 2, "purpose": "핵심 정보", "caption": (it.get("keyword") or title)[:20], "narration": summary[50:] or summary},
                {"scene_no": 3, "purpose": "마무리", "caption": "더 자세한 내용은 영상을 확인하세요", "narration": "구독과 좋아요 부탁드립니다"},
            ],
            "subtitle_points": [title],
            "risk_notes": ["read-only 분석 결과 기반"],
            "review_required": True,
        })
    sub_q = sq.build_subtitle_queue(video_items, max_items=max_items)
    return sub_q.get("subtitle_items") or []


def _subtitle_items_from_srt(srt_path: str) -> List[Dict[str, Any]]:
    segs = tq.parse_srt(srt_path)
    return [{
        "subtitle_id": "subtitle_001",
        "source_queue_id": "srt_input",
        "title": Path(srt_path).stem,
        "language": "ko",
        "duration_seconds": int(segs[-1]["end_seconds"]) if segs else 30,
        "segments": segs,
        "review_required": False,
        "warnings": [],
    }]


def _subtitle_items_from_vtt(vtt_path: str) -> List[Dict[str, Any]]:
    segs = tq.parse_vtt(vtt_path)
    return [{
        "subtitle_id": "subtitle_001",
        "source_queue_id": "vtt_input",
        "title": Path(vtt_path).stem,
        "language": "ko",
        "duration_seconds": int(segs[-1]["end_seconds"]) if segs else 30,
        "segments": segs,
        "review_required": False,
        "warnings": [],
    }]


def run(args: argparse.Namespace) -> Dict[str, Any]:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.subtitle_queue:
        data = tq.load_json(args.subtitle_queue)
        subtitle_items = data.get("subtitle_items") or []
    elif args.srt:
        subtitle_items = _subtitle_items_from_srt(args.srt)
    elif args.vtt:
        subtitle_items = _subtitle_items_from_vtt(args.vtt)
    else:
        subtitle_items = _subtitle_items_from_fixture(args.fixture, args.max_items)

    queue = tq.build_tts_queue(
        subtitle_items,
        voice_profile=args.voice_profile,
        output_dir=out_dir,
        max_items=args.max_items,
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    files = tq.write_tts_queue_files(queue, out_dir, timestamp=ts)

    summary: Dict[str, Any] = {
        "tts_items_count": queue["total_items"],
        "voice_profile": queue["voice_profile"],
        "result_json": str(files["json"]),
        "result_md": str(files["md"]),
        "sample_texts": [
            {
                "tts_id": it["tts_id"],
                "title": it["title"],
                "segments_count": it["segments_count"],
                "expected_audio_path": it["expected_audio_path"],
                "first_text": it["segments"][0]["text"] if it["segments"] else "",
            }
            for it in queue["tts_items"][:3]
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

    print(f"tts_items_count:  {sp['tts_items_count']}")
    print(f"voice_profile:    {sp['voice_profile']}")
    print(f"result_json:      {sp['result_json']}")
    print(f"result_md:        {sp['result_md']}")
    for s in sp["sample_texts"]:
        print(f"  [{s['tts_id']}] {s['title']} — {s['segments_count']} segs")
        print(f"    audio: {s['expected_audio_path']}")
        print(f"    first: {s['first_text'][:50]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
