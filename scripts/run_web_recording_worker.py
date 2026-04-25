"""웹 자동녹화 worker CLI (F-4S-8a dry-run + F-4S-8b local execute).

기본값은 dry-run.  --execute 명시 시에만 실제 브라우저 녹화를 수행한다.
실제 녹화는 localhost / 127.0.0.1 등 내부 URL 전용이다.

사용 예 (dry-run):
  python scripts/run_web_recording_worker.py \
      --recording-queue runs/video/web_recording_queue_YYYYMMDD_HHMMSS.json \
      --dry-run --json

사용 예 (execute — 내부 URL 전용):
  python scripts/run_web_recording_worker.py \
      --recording-queue runs/video/web_recording_queue_YYYYMMDD_HHMMSS.json \
      --execute --allow-host localhost --headless \
      --max-record-seconds 30 --json
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

from ai_orchestrator.video_production import recording_worker as rw


DEFAULT_OUT_DIR = "runs/video/worker"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "웹 자동녹화 worker — dry-run (기본) 또는 내부 URL execute 모드. "
            "외부 사이트 / 로그인 화면 / click·fill·type·press 금지."
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
        help="처리할 최대 item 수 (default: 전체)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="dry-run 모드 (default: True). --execute 없으면 항상 dry-run",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="실제 브라우저 녹화 실행 (내부 URL 전용). --execute 없으면 dry-run",
    )
    parser.add_argument(
        "--allow-host",
        action="append",
        dest="allow_hosts",
        metavar="HOST",
        default=None,
        help="추가 허용 host (예: --allow-host localhost --allow-host 192.168.1.10). "
             "기본: localhost / 127.0.0.1 / ::1",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="헤드리스 모드 (default: True)",
    )
    parser.add_argument(
        "--screenshot",
        action="store_true",
        default=False,
        help="capture_scene 마다 screenshot 저장 (execute 모드 전용)",
    )
    parser.add_argument(
        "--max-record-seconds",
        type=int,
        default=rw.DEFAULT_MAX_RECORD_SECONDS,
        help=f"item 별 최대 녹화 시간(초) (default: {rw.DEFAULT_MAX_RECORD_SECONDS})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="요약을 stdout JSON 으로 출력",
    )
    return parser.parse_args(argv)


def _run_dry_run(args: argparse.Namespace, queue: Any, out_dir: Path) -> Dict[str, Any]:
    plan = rw.build_execution_plan(
        queue,
        output_dir=out_dir,
        dry_run=True,
        max_items=args.max_items,
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    files = rw.write_worker_result_files(plan, out_dir, timestamp=timestamp)
    summary_payload: Dict[str, Any] = {
        "mode": "dry_run",
        "input_queue": str(args.recording_queue),
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
            "실제 녹화는 --execute + 내부 URL 에서만 허용",
        ],
    }
    return {"plan": plan, "files": files, "summary_payload": summary_payload}


def _run_execute(args: argparse.Namespace, queue: Any, out_dir: Path) -> Dict[str, Any]:
    allow_hosts: Optional[List[str]] = args.allow_hosts  # None 또는 list

    # pre-flight validation
    pre = rw.validate_execute_allowed(queue, allow_hosts=allow_hosts)
    if not pre["can_execute"]:
        blocked_reasons = [
            f"{b['recording_id']}: {b['reasons']}" for b in pre["blocked_items"]
        ]
        summary_payload: Dict[str, Any] = {
            "mode": "execute",
            "input_queue": str(args.recording_queue),
            "status": "blocked",
            "can_execute": False,
            "blocked_items": pre["blocked_items"],
            "errors": pre["errors"],
            "blocked_reasons": blocked_reasons,
            "notes": ["execute 차단 — blocked item 해결 후 재시도"],
        }
        return {"plan": None, "files": {}, "summary_payload": summary_payload}

    plan = rw.execute_recording_plan(
        queue,
        output_dir=out_dir,
        allow_hosts=allow_hosts,
        headless=args.headless,
        max_record_seconds=args.max_record_seconds,
        take_screenshot=args.screenshot,
        max_items=args.max_items,
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    files = rw.write_worker_result_files(plan, out_dir, timestamp=timestamp)
    summary_payload = {
        "mode": "execute",
        "input_queue": str(args.recording_queue),
        "out_dir": str(out_dir),
        "dry_run": False,
        "total_items": plan.get("total_items", 0),
        "executed_count": plan.get("executed_count", 0),
        "failed_count": plan.get("failed_count", 0),
        "blocked_count": plan.get("blocked_count", 0),
        "sample_titles": [it.get("title") for it in plan.get("items", [])[:5]],
        "files": {k: str(v) for k, v in files.items()},
        "notes": plan.get("notes", []),
    }
    return {"plan": plan, "files": files, "summary_payload": summary_payload}


def run(args: argparse.Namespace) -> Dict[str, Any]:
    queue_path = Path(args.recording_queue)
    if not queue_path.exists():
        raise SystemExit(f"recording queue not found: {queue_path}")

    queue = rw.load_recording_queue(queue_path)
    out_dir = Path(args.out_dir)

    if args.execute:
        return _run_execute(args, queue, out_dir)
    return _run_dry_run(args, queue, out_dir)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = run(args)
    sp = result["summary_payload"]
    if args.json:
        print(json.dumps(sp, ensure_ascii=False, indent=2))
    else:
        mode = sp.get("mode", "dry_run")
        print(f"mode: {mode}")
        print(f"input_queue: {sp.get('input_queue')}")
        print(f"out_dir: {sp.get('out_dir', '-')}")
        if mode == "execute":
            print(f"status: {sp.get('status', 'ok')}")
            print(f"executed_count: {sp.get('executed_count', '-')}")
            print(f"failed_count: {sp.get('failed_count', '-')}")
            print(f"blocked_count: {sp.get('blocked_count', '-')}")
        else:
            print(f"dry_run: {sp.get('dry_run')}")
            print(f"total_items: {sp.get('total_items')}")
            print(f"validated_count: {sp.get('validated_count')}")
            print(f"blocked_count: {sp.get('blocked_count')}")
            print(f"warning_count: {sp.get('warning_count')}")
        for t in sp.get("sample_titles") or []:
            print(f"  - {t}")
        files = sp.get("files") or {}
        if files:
            print(f"json: {files.get('json')}")
            print(f"md:   {files.get('md')}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
