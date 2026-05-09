"""사용자 브라우저 세션 열기 CLI.

사용 예
======
    # hancom_dev 프로필로 한컴 개발자 센터 열기 (90초 대기)
    python scripts/local_agent/open_user_browser_session.py \
        --profile hancom_dev \
        --url https://developer.hancom.com/ \
        --wait 90

    # 페이지 내용 추출까지
    python scripts/local_agent/open_user_browser_session.py \
        --profile hancom_dev \
        --url https://developer.hancom.com/ \
        --wait 30 \
        --extract body \
        --screenshot tmp/hancom_session.png

    # 저장된 프로필 목록
    python scripts/local_agent/open_user_browser_session.py --list
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_orchestrator.local_agent.user_browser_session import (
    open_user_session, list_profiles, get_session_dir,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="사용자 세션 브라우저 열기")
    parser.add_argument("--profile", default="default",
                        help="세션 프로필 이름 (사이트별 분리 권장)")
    parser.add_argument("--url", default=None, help="초기 이동 URL")
    parser.add_argument("--wait", type=int, default=60,
                        help="브라우저 유지 시간 (초). 사용자 로그인/탐색 시간 확보")
    parser.add_argument("--extract", choices=["body", "title", "none"], default="none",
                        help="대기 후 추출할 정보")
    parser.add_argument("--screenshot", default=None, help="스크린샷 저장 경로")
    parser.add_argument("--headless", action="store_true",
                        help="headless 실행 (기본: 사용자 가시 모드)")
    parser.add_argument("--channel", default="chrome", help="브라우저 채널 (chrome/chromium/msedge)")
    parser.add_argument("--list", action="store_true", help="저장된 프로필 목록만 출력")
    parser.add_argument("--output", type=Path, default=None, help="결과 JSON 저장 경로")
    args = parser.parse_args()

    if args.list:
        profiles = list_profiles()
        if not profiles:
            print("저장된 프로필 없음")
        else:
            for p in profiles:
                d = get_session_dir(p)
                print(f"  {p}  ({d})")
        return 0

    print(f"[세션 열기] profile={args.profile}  url={args.url}  wait={args.wait}s")
    print(f"  세션 디렉터리: {get_session_dir(args.profile)}")
    print(f"  처음이면 브라우저에서 직접 로그인 → 다음부터 자동 로그인")

    result: dict = {
        "profile": args.profile,
        "start_url": args.url,
        "wait_seconds": args.wait,
    }

    with open_user_session(
        profile_name=args.profile,
        headless=args.headless,
        channel=args.channel,
        start_url=args.url,
    ) as context:
        page = context.pages[0] if context.pages else context.new_page()
        if args.url and not page.url.startswith(args.url):
            try:
                page.goto(args.url, timeout=60000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"  [warn] goto 실패: {e}")

        if args.wait > 0:
            print(f"  {args.wait}초 동안 브라우저 유지 중... (사용자 로그인/조작 가능)")
            time.sleep(args.wait)

        # 정보 추출
        try:
            result["final_url"] = page.url
            result["title"] = page.title()
        except Exception as e:
            result["error_post"] = str(e)[:200]

        if args.extract == "body":
            try:
                result["body_text"] = page.inner_text("body")[:5000]
            except Exception as e:
                result["body_error"] = str(e)[:200]
        elif args.extract == "title":
            pass  # title은 위에서 이미 수집

        if args.screenshot:
            try:
                Path(args.screenshot).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=args.screenshot, full_page=True)
                result["screenshot"] = args.screenshot
                print(f"  스크린샷 저장: {args.screenshot}")
            except Exception as e:
                result["screenshot_error"] = str(e)[:200]

    # 결과 출력
    print()
    print("=" * 60)
    print(f"final_url : {result.get('final_url', '?')}")
    print(f"title     : {result.get('title', '?')}")
    if "body_text" in result:
        print(f"body[:500]: {result['body_text'][:500]}")
    print("=" * 60)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  결과 JSON 저장: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
