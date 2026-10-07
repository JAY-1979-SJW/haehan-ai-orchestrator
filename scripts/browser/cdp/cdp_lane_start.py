"""CDP 칸(lane) 단위 시작·상태·종료 CLI.

기준서: docs/specs/2026-10-02_app_agent_dispatch.md §9-2
  python scripts/browser/cdp/cdp_lane_start.py list                      — 칸 목록과 켜짐 여부
  python scripts/browser/cdp/cdp_lane_start.py start --lane naver [url]  — 그 칸의 Chrome 시작(동시 칸 상한 확인)
  python scripts/browser/cdp/cdp_lane_start.py status --lane naver
  python scripts/browser/cdp/cdp_lane_start.py stop --lane naver

`general` 칸은 기존 `cdp_force_start.py` 와 완전히 같은 동작(포트 9222, 기존 프로필·PID 파일).
`cdp_force_start.py` 자체는 수정하지 않는다(다른 모듈 6곳이 import) — 이 CLI 는 별도 프로세스에서 그 모듈의
전역값(포트·프로필·PID 파일)만 칸 값으로 바꿔 같은 시작 로직을 재사용한다.
로그인 세션 보존 원칙: 쿠키 삭제·로그아웃 없음, 종료는 해당 칸의 Chrome 프로세스만.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.browser.cdp import cdp_force_start as base  # noqa: E402
from scripts.browser.cdp import cdp_lanes  # noqa: E402


def apply_lane(lane: cdp_lanes.Lane) -> None:
    """`cdp_force_start` 의 전역값을 이 칸의 포트·프로필·PID 파일로 바꾼다(이 프로세스 안에서만)."""
    base.CDP_PORT = lane.port
    base.PROFILE_DIR = lane.profile_dir
    base.PID_FILE = lane.pid_file


def cmd_list() -> int:
    for lane in cdp_lanes.LANES.values():
        state = "켜짐" if cdp_lanes.is_alive(lane) else "꺼짐"
        sites = ", ".join(lane.sites) or "(기본·그 외 전부)"
        print(f"{lane.name:<10} 포트 {lane.port}  {state:<3}  프로필 {lane.profile_dir}  사이트: {sites}")
    problems = cdp_lanes.validate_registry()
    for p in problems:
        print(f"[등록표 오류] {p}")
    return 1 if problems else 0


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="CDP 칸 시작·상태·종료")
    parser.add_argument("command", choices=["list", "start", "status", "stop"])
    parser.add_argument("url", nargs="?", default="")
    parser.add_argument("--lane", default=cdp_lanes.GENERAL)
    args = parser.parse_args(argv)
    if args.command == "list":
        return cmd_list()
    try:
        lane = cdp_lanes.get_lane(args.lane)
    except cdp_lanes.UnknownLane as e:
        print(e)
        return 2
    if args.command == "start":
        ok, why = cdp_lanes.can_start(lane.name)
        if not ok:
            print(f"✗ '{lane.name}' 칸을 켜지 않습니다: {why}")
            return 3
    apply_lane(lane)
    if args.command == "start":
        return base.cmd_start(args.url)
    if args.command == "status":
        base.cmd_status()
        return 0
    base.cmd_stop()
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
