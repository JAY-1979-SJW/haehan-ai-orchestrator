"""F-4S-8c localhost 녹화 smoke 스크립트.

동작:
  1. 127.0.0.1:8765 에 stdlib HTTP 서버 시작
  2. web_recording_queue 생성 (target_url=http://127.0.0.1:8765/)
  3. execute_recording_plan 호출 (실제 브라우저 녹화)
  4. metadata JSON / video artifact 확인
  5. 서버 종료
  6. 결과 요약 출력

금지:
  - 외부 URL 사용 금지
  - click / fill / type / press 단계 금지
  - page.evaluate 금지
  - 로그인 / 입력 요소 금지
  - cookie / session / storage 접근 금지
  - OAuth / upload / LTX API 호출 금지

사용 예:
  python scripts/smoke_web_recording_localhost.py
  python scripts/smoke_web_recording_localhost.py --json
  python scripts/smoke_web_recording_localhost.py --screenshot --json
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ai_orchestrator.video_production import recording_worker as rw

SMOKE_HOST = "127.0.0.1"
SMOKE_PORT = 8765
SMOKE_DEMO_DIR = str(_REPO_ROOT / "samples" / "web_recording_demo")
SMOKE_TARGET_URL = f"http://{SMOKE_HOST}:{SMOKE_PORT}/"
SMOKE_OUT_DIR = _REPO_ROOT / "runs" / "video" / "smoke"


def _make_recording_queue() -> Dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return {
        "queue_id": f"smoke_{ts}",
        "source": "smoke_web_recording_localhost",
        "queue": [
            {
                "recording_id": f"smoke_localhost_{ts}",
                "source_queue_id": f"smoke_{ts}",
                "title": "localhost demo 화면 smoke 녹화",
                "target_url": SMOKE_TARGET_URL,
                "viewport": {"name": "desktop", "width": 1440, "height": 900},
                "duration_seconds": 5,
                "recording_steps": [
                    {"step_no": 1, "type": "open_url", "url": SMOKE_TARGET_URL},
                    {"step_no": 2, "type": "wait", "wait_seconds": 1},
                    {"step_no": 3, "type": "capture_scene", "duration_seconds": 3},
                ],
            }
        ],
    }


def _start_server(port: int, directory: str) -> http.server.HTTPServer:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=directory,
    )
    handler.log_message = lambda *args: None
    server = http.server.HTTPServer((SMOKE_HOST, port), handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def _wait_for_server(port: int, timeout: float = 5.0) -> bool:
    import socket
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((SMOKE_HOST, port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="localhost web recording smoke")
    parser.add_argument("--json", action="store_true", help="stdout JSON 출력")
    parser.add_argument("--screenshot", action="store_true", help="capture_scene 마다 screenshot 저장")
    parser.add_argument("--out-dir", default=str(SMOKE_OUT_DIR))
    parser.add_argument("--max-record-seconds", type=int, default=30)
    return parser.parse_args(argv)


def run_smoke(
    *,
    out_dir: Optional[Path] = None,
    take_screenshot: bool = False,
    max_record_seconds: int = 30,
) -> Dict[str, Any]:
    out_dir = Path(out_dir) if out_dir else SMOKE_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if not os.path.isdir(SMOKE_DEMO_DIR):
        return {
            "success": False,
            "error": f"demo directory not found: {SMOKE_DEMO_DIR}",
        }

    server = _start_server(SMOKE_PORT, SMOKE_DEMO_DIR)
    if not _wait_for_server(SMOKE_PORT):
        server.shutdown()
        return {
            "success": False,
            "error": f"server did not start on {SMOKE_HOST}:{SMOKE_PORT}",
        }

    queue = _make_recording_queue()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    queue_path = out_dir / f"smoke_queue_{ts}.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        plan = rw.execute_recording_plan(
            queue,
            output_dir=out_dir,
            allow_hosts=[SMOKE_HOST, "localhost"],
            headless=True,
            max_record_seconds=max_record_seconds,
            take_screenshot=take_screenshot,
            max_items=1,
        )
    finally:
        server.shutdown()
        server.server_close()

    items = plan.get("items") or []
    item = items[0] if items else {}

    video_path: Optional[str] = item.get("video_path")
    video_dir: Optional[str] = item.get("video_dir")
    video_file_size: Optional[int] = None
    if video_path and Path(video_path).exists():
        video_file_size = Path(video_path).stat().st_size
    elif video_dir:
        # Playwright 가 context.close() 후 파일명을 확정하는 경우
        vdir = Path(video_dir)
        if vdir.is_dir():
            candidates = sorted(vdir.glob("*.webm")) + sorted(vdir.glob("*.mp4"))
            if candidates:
                best = candidates[0]
                video_path = str(best)
                video_file_size = best.stat().st_size

    result: Dict[str, Any] = {
        "target_url": SMOKE_TARGET_URL,
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
        "plan_notes": plan.get("notes") or [],
        "queue_path": str(queue_path),
        "out_dir": str(out_dir),
        "external_url_used": False,
        "login_form_used": False,
        "click_fill_used": False,
    }
    return result


def main(argv=None) -> int:
    args = parse_args(argv)
    result = run_smoke(
        out_dir=Path(args.out_dir),
        take_screenshot=args.screenshot,
        max_record_seconds=args.max_record_seconds,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("success") else 1

    print(f"target_url:             {result.get('target_url')}")
    print(f"recording_items_count:  {result.get('recording_items_count')}")
    print(f"metadata_json:          {result.get('metadata_json')}")
    print(f"video_path:             {result.get('video_path')}")
    print(f"video_dir:              {result.get('video_dir')}")
    print(f"video_file_size:        {result.get('video_file_size')}")
    print(f"screenshot_paths:       {result.get('screenshot_paths')}")
    print(f"success:                {result.get('success')}")
    print(f"status:                 {result.get('status')}")
    print(f"warnings:               {result.get('warnings')}")
    print(f"steps_executed:         {result.get('steps_executed')}")
    print(f"external_url_used:      {result.get('external_url_used')}")
    print(f"login_form_used:        {result.get('login_form_used')}")
    print(f"click_fill_used:        {result.get('click_fill_used')}")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
