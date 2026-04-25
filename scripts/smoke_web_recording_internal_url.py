"""F-4S-8d 내부 URL 녹화 smoke 스크립트.

동작:
  1. preflight: 대상 URL이 allowlist 내부 host인지 + 로그인 화면인지 확인
  2. recording queue 1 item 생성 (open_url → wait → capture_scene)
  3. execute_recording_plan 호출 (실제 브라우저 녹화)
  4. metadata JSON / video artifact 확인
  5. 결과 요약 출력

금지:
  - 외부 URL 사용 금지
  - click / fill / type / press 단계 금지
  - cookie / session / storage_state 접근 금지
  - OAuth / upload / LTX API 호출 금지
  - 로그인 화면 녹화 금지

사용 예:
  python scripts/smoke_web_recording_internal_url.py \\
    --url http://127.0.0.1:3000 \\
    --allow-host 127.0.0.1 --allow-host localhost \\
    --headless --json
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

from ai_orchestrator.video_production import recording_worker as rw
from scripts.preflight_internal_recording_target import run_preflight

DEFAULT_OUT_DIR = _REPO_ROOT / "runs" / "video" / "internal_smoke"


def _make_recording_queue(url: str) -> Dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    rec_id = f"internal_smoke_{ts}"
    return {
        "queue_id": f"internal_smoke_{ts}",
        "source": "smoke_web_recording_internal_url",
        "queue": [
            {
                "recording_id": rec_id,
                "source_queue_id": f"internal_smoke_{ts}",
                "title": f"내부 URL smoke 녹화: {url}",
                "target_url": url,
                "viewport": {"name": "desktop", "width": 1440, "height": 900},
                "duration_seconds": 5,
                "recording_steps": [
                    {"step_no": 1, "type": "open_url", "url": url},
                    {"step_no": 2, "type": "wait", "wait_seconds": 1},
                    {"step_no": 3, "type": "capture_scene", "duration_seconds": 3},
                ],
            }
        ],
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="내부 URL 실제 녹화 smoke (F-4S-8d)")
    parser.add_argument("--url", required=True, help="녹화 대상 내부 URL")
    parser.add_argument("--allow-host", action="append", dest="allow_hosts", metavar="HOST", default=None)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--screenshot", action="store_true", default=False)
    parser.add_argument("--max-record-seconds", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def run_smoke(
    url: str,
    *,
    allow_hosts: Optional[List[str]] = None,
    out_dir: Optional[Path] = None,
    headless: bool = True,
    take_screenshot: bool = False,
    max_record_seconds: int = 30,
) -> Dict[str, Any]:
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # preflight
    preflight = run_preflight([url], allow_hosts=allow_hosts)
    candidate = preflight["candidates"][0] if preflight["candidates"] else {}

    if not candidate.get("internal_host"):
        return {
            "success": False,
            "skip": True,
            "skip_reason": "external_host_blocked",
            "target_url": url,
            "preflight": preflight,
        }
    if not candidate.get("reachable"):
        return {
            "success": False,
            "skip": True,
            "skip_reason": candidate.get("skip_reason") or "not_reachable",
            "target_url": url,
            "preflight": preflight,
        }
    if candidate.get("login_required"):
        return {
            "success": False,
            "skip": True,
            "skip_reason": "login_required",
            "target_url": url,
            "preflight": preflight,
        }

    queue = _make_recording_queue(url)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    queue_path = out_dir / f"internal_smoke_queue_{ts}.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

    plan = rw.execute_recording_plan(
        queue,
        output_dir=out_dir,
        allow_hosts=allow_hosts,
        headless=headless,
        max_record_seconds=max_record_seconds,
        take_screenshot=take_screenshot,
        max_items=1,
    )

    items = plan.get("items") or []
    item = items[0] if items else {}

    video_path: Optional[str] = item.get("video_path")
    video_dir: Optional[str] = item.get("video_dir")
    video_file_size: Optional[int] = None
    if video_path and Path(video_path).exists():
        video_file_size = Path(video_path).stat().st_size
    elif video_dir:
        vdir = Path(video_dir)
        if vdir.is_dir():
            candidates = sorted(vdir.glob("*.webm")) + sorted(vdir.glob("*.mp4"))
            if candidates:
                best = candidates[0]
                video_path = str(best)
                video_file_size = best.stat().st_size

    return {
        "target_url": url,
        "recording_items_count": len(items),
        "metadata_json": item.get("output_metadata_path"),
        "video_path": video_path,
        "video_dir": video_dir,
        "video_file_size": video_file_size,
        "screenshot_paths": item.get("screenshot_paths") or [],
        "success": item.get("success", False),
        "status": item.get("status"),
        "warnings": item.get("warnings") or [],
        "steps_executed": item.get("steps_executed") or [],
        "queue_path": str(queue_path),
        "out_dir": str(out_dir),
        "preflight": preflight,
        "skip": False,
        "external_url_used": False,
        "login_form_used": False,
        "click_fill_used": False,
    }


def main(argv=None) -> int:
    args = parse_args(argv)
    result = run_smoke(
        args.url,
        allow_hosts=args.allow_hosts,
        out_dir=Path(args.out_dir),
        headless=args.headless,
        take_screenshot=args.screenshot,
        max_record_seconds=args.max_record_seconds,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("success") else (2 if result.get("skip") else 1)

    skip = result.get("skip")
    if skip:
        print(f"SKIP: {result.get('skip_reason')}  url={result.get('target_url')}")
        return 2

    print(f"target_url:             {result.get('target_url')}")
    print(f"recording_items_count:  {result.get('recording_items_count')}")
    print(f"metadata_json:          {result.get('metadata_json')}")
    print(f"video_path:             {result.get('video_path')}")
    print(f"video_file_size:        {result.get('video_file_size')}")
    print(f"screenshot_paths:       {result.get('screenshot_paths')}")
    print(f"success:                {result.get('success')}")
    print(f"status:                 {result.get('status')}")
    print(f"warnings:               {result.get('warnings')}")
    print(f"external_url_used:      {result.get('external_url_used')}")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
