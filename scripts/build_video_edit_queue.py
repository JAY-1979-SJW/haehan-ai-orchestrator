"""F-4S-11 영상 편집 큐 생성 CLI.

사용 예:
  # fixture 기반 (전체 파이프라인 내부 생성)
  python scripts/build_video_edit_queue.py \\
    --fixture samples/content_research_fixture.json \\
    --max-items 3 --json

  # 각 큐 직접 입력
  python scripts/build_video_edit_queue.py \\
    --subtitle-queue runs/video/subtitles/subtitle_queue_*.json \\
    --tts-queue runs/video/tts/tts_queue_*.json \\
    --metadata runs/video/smoke/recordings/.../metadata.json \\
    --json

금지: 실제 ffmpeg 실행 / 영상·음성 합성 / OAuth / 브라우저 / 업로드
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

from ai_orchestrator.video_production import edit_queue as eq
from ai_orchestrator.video_production import subtitle_queue as sq
from ai_orchestrator.video_production import tts_queue as tq
from ai_orchestrator.video_production import queue_builder as qb

DEFAULT_OUT_DIR = _REPO_ROOT / "runs" / "video" / "edits"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="영상 편집 큐 생성 CLI (F-4S-11)")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--fixture", metavar="PATH", help="content_research_fixture JSON")
    src.add_argument("--subtitle-queue", metavar="PATH", help="F-4S-9 subtitle_queue JSON")
    parser.add_argument("--worker-result", metavar="PATH", help="F-4S-8 worker result JSON")
    parser.add_argument("--metadata", metavar="PATH", help="F-4S-8 recording metadata JSON")
    parser.add_argument("--tts-queue", metavar="PATH", help="F-4S-10 tts_queue JSON")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--max-items", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _build_from_fixture(fixture_path: str, max_items: int) -> tuple:
    """fixture → subtitle queue → tts queue → assets."""
    try:
        briefs = qb.extract_ltx_briefs(qb.load_content_report(Path(fixture_path)))
        if briefs:
            vq = qb.build_video_queue(briefs, max_items=max_items)
            video_items = sq.extract_video_queue_items(vq)
            sub_q = sq.build_subtitle_queue(video_items, max_items=max_items)
            tts_q = tq.build_tts_queue(
                sub_q.get("subtitle_items") or [],
                max_items=max_items,
            )
            return sub_q, tts_q
    except Exception:
        pass

    # fallback
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
                {"scene_no": 2, "purpose": "핵심 정보", "caption": title[:20], "narration": summary[50:] or summary},
                {"scene_no": 3, "purpose": "마무리", "caption": "더 자세한 내용은 영상을 확인하세요", "narration": "구독과 좋아요 부탁드립니다"},
            ],
            "subtitle_points": [title],
            "risk_notes": ["read-only 분석 결과 기반"],
            "review_required": True,
        })
    sub_q = sq.build_subtitle_queue(video_items, max_items=max_items)
    tts_q = tq.build_tts_queue(sub_q.get("subtitle_items") or [], max_items=max_items)
    return sub_q, tts_q


def run(args: argparse.Namespace) -> Dict[str, Any]:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # recording assets
    rec_assets: List[Dict[str, Any]] = []
    if args.worker_result:
        rec_assets = eq.extract_recording_assets(eq.load_json(args.worker_result))
    elif getattr(args, "metadata", None):
        rec_assets = eq.extract_recording_assets(eq.load_json(args.metadata))

    # subtitle / tts assets
    if args.fixture:
        sub_q, tts_q = _build_from_fixture(args.fixture, args.max_items)
        sub_assets = eq.extract_subtitle_assets(sub_q)
        tts_assets = eq.extract_tts_assets(tts_q)
    else:
        sub_q_data = eq.load_json(args.subtitle_queue)
        sub_assets = eq.extract_subtitle_assets(sub_q_data)
        tts_q_data = eq.load_json(args.tts_queue) if getattr(args, "tts_queue", None) else {}
        tts_assets = eq.extract_tts_assets(tts_q_data)

    queue = eq.build_edit_queue(
        rec_assets,
        sub_assets,
        tts_assets,
        output_dir=out_dir,
        max_items=args.max_items,
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    files = eq.write_edit_queue_files(queue, out_dir, timestamp=ts)

    summary: Dict[str, Any] = {
        "edit_items_count": queue["total_items"],
        "result_json": str(files["json"]),
        "result_md": str(files["md"]),
        "sample_titles": [
            {
                "edit_id": it["edit_id"],
                "title": it["title"],
                "timeline_layers": [l["layer"] for l in it["timeline"]],
                "output_video_path": it["output_video_path"],
                "review_required": it["review_required"],
            }
            for it in queue["edit_items"][:3]
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

    print(f"edit_items_count: {sp['edit_items_count']}")
    print(f"result_json:      {sp['result_json']}")
    print(f"result_md:        {sp['result_md']}")
    for s in sp["sample_titles"]:
        print(f"  [{s['edit_id']}] {s['title']}")
        print(f"    layers: {s['timeline_layers']}")
        print(f"    output: {s['output_video_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
