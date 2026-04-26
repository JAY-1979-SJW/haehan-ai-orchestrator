"""CLI: F-4S-13 restricted render worker 실행.

Usage:
  python scripts/run_render_worker.py --render-plan <path> [--out-dir <dir>] [--execute] [--max-items N] [--json]

기본 동작: dry-run (실제 ffmpeg 미실행)
--execute 명시 시: validate 통과 항목만 실제 ffmpeg 실행
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# project root on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_orchestrator.video_production.render_worker import (
    execute_render_plan,
    load_render_plan,
    render_render_worker_markdown,
    write_render_worker_result_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="F-4S-13 restricted render worker")
    parser.add_argument("--render-plan", required=True, help="render plan JSON path")
    parser.add_argument(
        "--out-dir",
        default="runs/video/render/worker",
        help="output directory (default: runs/video/render/worker)",
    )
    parser.add_argument("--execute", action="store_true", help="실제 ffmpeg 실행 (기본: dry-run)")
    parser.add_argument("--max-items", type=int, default=None, help="처리할 최대 항목 수")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON 출력")
    args = parser.parse_args()

    plan_path = Path(args.render_plan)
    if not plan_path.exists():
        print(f"[ERROR] render plan not found: {plan_path}", file=sys.stderr)
        return 1

    plan = load_render_plan(plan_path)
    dry_run = not args.execute

    result = execute_render_plan(
        plan,
        dry_run=dry_run,
        max_items=args.max_items,
    )

    out_dir = Path(args.out_dir)
    paths = write_render_worker_result_files(result, out_dir)

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_render_worker_markdown(result))

    print(f"\n[결과 파일]", file=sys.stderr)
    print(f"  JSON: {paths['json']}", file=sys.stderr)
    print(f"  MD:   {paths['md']}", file=sys.stderr)

    if not dry_run and result.get("error_count", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
