"""F-4S-12 렌더 계획 생성 CLI.

사용 예:
  python scripts/build_render_plan.py \\
    --edit-queue runs/video/edits/video_edit_queue_*.json \\
    --json

금지: 실제 ffmpeg 실행 / 영상 합성 / subprocess / shell=True / OAuth / 브라우저 / 업로드
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ai_orchestrator.video_production import render_plan as rp

DEFAULT_OUT_DIR = _REPO_ROOT / "runs" / "video" / "render"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="렌더 계획 생성 CLI (F-4S-12)")
    parser.add_argument("--edit-queue", metavar="PATH", required=True, help="F-4S-11 edit_queue JSON")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--require-assets", action="store_true", help="자산 누락 시 blocked 처리")
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    out_dir = Path(args.out_dir)
    edit_queue = rp.load_json(args.edit_queue)

    plan = rp.build_render_plan(
        edit_queue,
        out_dir=out_dir,
        require_assets=args.require_assets,
        max_items=args.max_items,
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    files = rp.write_render_plan_files(plan, out_dir, timestamp=ts)

    summary: Dict[str, Any] = {
        "total_items": plan["total_items"],
        "planned_count": plan["planned_count"],
        "blocked_count": plan["blocked_count"],
        "ffmpeg_available": plan["ffmpeg_available"],
        "result_json": str(files["json"]),
        "result_md": str(files["md"]),
        "sample_renders": [
            {
                "render_id": it["render_id"],
                "source_edit_id": it["source_edit_id"],
                "title": it["title"],
                "status": it["status"],
                "ffmpeg_available": it["ffmpeg_available"],
                "assets": it["assets"],
                "command_display": it["command_plan"]["display"],
                "warnings": it["warnings"],
            }
            for it in plan["render_items"][:3]
        ],
        "notes": plan["notes"],
    }
    return {"plan": plan, "files": files, "summary": summary}


def main(argv=None) -> int:
    args = parse_args(argv)
    result = run(args)
    sp = result["summary"]

    if args.json:
        print(json.dumps(sp, ensure_ascii=False, indent=2))
        return 0

    print(f"total_items:     {sp['total_items']}")
    print(f"planned_count:   {sp['planned_count']}")
    print(f"blocked_count:   {sp['blocked_count']}")
    print(f"ffmpeg_available:{sp['ffmpeg_available']}")
    print(f"result_json:     {sp['result_json']}")
    print(f"result_md:       {sp['result_md']}")
    for r in sp["sample_renders"]:
        print(f"  [{r['render_id']}] {r['title'] or '(제목 없음)'} — {r['status']}")
        print(f"    cmd: {r['command_display']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
