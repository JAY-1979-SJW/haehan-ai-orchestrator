"""웹 자동녹화 worker dry-run CLI (F-4S-8a).

실제 브라우저 실행 / 녹화 / 업로드 일체 수행하지 않는다.
F-4S-7 web_recording_queue JSON 을 입력으로 받아 실행계획만 생성한다.

사용 예:
  python scripts/run_web_recording_worker.py \
      --recording-queue runs/video/web_recording_queue_20260425_162846.json \
      --dry-run --json

  python scripts/run_web_recording_worker.py \
      --recording-queue runs/video/web_recording_queue_20260425_162846.json \
      --out-dir runs/video/worker --max-items 3
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ai_orchestrator.video_production import recording_worker as rw


DEFAULT_OUT_DIR = "runs/video/worker"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "웹 자동녹화 worker dry-run — 실제 브라우저 실행/녹화 없음 "
            "(F-4S-7 큐 검증 + 실행계획 생성 전용)"
        ),
    )
    parser.add_argument(
        "--recording-queue",
        type=str,
        required=True,
        help="F-4S-7 web_recording_queue JSON 경로",
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
        default=None,
        help="실행계획 생성 시 처리할 최대 item 수 (default: 전체)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="dry-run 모드 (default: True). 본 단계에서는 무조건 dry-run 만 허용",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="요약을 stdout JSON 으로 출력",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    queue_path = Path(args.recording_queue)
    if not queue_path.exists():
        raise SystemExit(f"recording queue not found: {queue_path}")

    queue = rw.load_recording_queue(queue_path)
    out_dir = Path(args.out_dir)
    plan = rw.build_execution_plan(
        queue,
        output_dir=out_dir,
        dry_run=True,
        max_items=args.max_items,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    files = rw.write_worker_result_files(plan, out_dir, timestamp=timestamp)

    summary_payload = {
        "input_queue": str(queue_path),
        "out_dir": str(out_dir),
        "dry_run": True,
        "total_items": plan["total_items"],
        "validated_count": plan["validated_count"],
        "blocked_count": plan["blocked_count"],
        "warning_count": plan["warning_count"],
        "queue_errors": plan["queue_errors"],
        "sample_titles": [it.get("title") for it in plan["items"][:5]],
        "files": {k: str(v) for k, v in files.items()},
        "notes": [
            "실제 브라우저 실행 없음",
            "실제 mp4/녹화 파일 생성 없음",
            "click/fill/type/press 등 자동 입력 step 은 본 worker 에서 차단",
            "실제 녹화는 F-4S-8b 에서 별도 승인 후 진행",
        ],
    }
    return {"plan": plan, "files": files, "summary_payload": summary_payload}


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = run(args)
    summary_payload = result["summary_payload"]
    if args.json:
        print(json.dumps(summary_payload, ensure_ascii=False, indent=2))
    else:
        print(f"input_queue: {summary_payload['input_queue']}")
        print(f"out_dir: {summary_payload['out_dir']}")
        print(f"dry_run: {summary_payload['dry_run']}")
        print(f"total_items: {summary_payload['total_items']}")
        print(f"validated_count: {summary_payload['validated_count']}")
        print(f"blocked_count: {summary_payload['blocked_count']}")
        print(f"warning_count: {summary_payload['warning_count']}")
        for t in summary_payload["sample_titles"]:
            print(f"  - {t}")
        print(f"json: {summary_payload['files'].get('json')}")
        print(f"md:   {summary_payload['files'].get('md')}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
