"""로컬 에이전트 실행 진입점 (B안 3단계 — HTTP 폴링).

예:
    # 환경변수 사용
    set AGENT_API_URL=http://127.0.0.1:8765
    set AGENT_TOKEN=test-token
    python scripts/run_local_agent.py

    # 인자 직접 전달 + 유한 루프 (검증용)
    python scripts/run_local_agent.py ^
        --api-url http://127.0.0.1:8765 ^
        --token test-token ^
        --poll-seconds 0.5 ^
        --max-iterations 3

Ctrl+C 로 중단.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Local agent main loop")
    parser.add_argument(
        "--api-url",
        default=os.environ.get("AGENT_API_URL", ""),
        help="서버 Base URL. 환경변수 AGENT_API_URL 로도 지정 가능.",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("AGENT_TOKEN", ""),
        help="Bearer 토큰. 환경변수 AGENT_TOKEN 로도 지정 가능.",
    )
    parser.add_argument(
        "--poll-seconds", type=float,
        default=float(os.environ.get("AGENT_POLL_SECONDS", "5.0")),
    )
    parser.add_argument(
        "--max-iterations", type=int, default=None,
        help="지정 시 이 횟수만큼 poll 후 종료 (검증용).",
    )
    parser.add_argument("--stop-file", default=None,
                        help="경로가 존재하면 그레이스풀 종료.")
    parser.add_argument(
        "--spool-dir",
        default=os.environ.get("AGENT_SPOOL_DIR", ""),
        help="report 실패 시 결과를 쌓아 두는 spool 디렉터리.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    from agent import local_agent

    if not args.api_url:
        logging.error("AGENT_API_URL (또는 --api-url) 가 필요합니다.")
        return 2

    stop = Path(args.stop_file) if args.stop_file else None
    logging.info(
        "agent loop start — api=%s poll=%ss max=%s",
        args.api_url, args.poll_seconds, args.max_iterations,
    )
    try:
        n = local_agent.run_agent_loop(
            api_url=args.api_url,
            token=args.token,
            poll_seconds=args.poll_seconds,
            max_iterations=args.max_iterations,
            stop_file=stop,
            spool_dir=Path(args.spool_dir) if args.spool_dir else None,
        )
        logging.info("agent loop stopped — processed=%d", n)
        return 0
    except KeyboardInterrupt:
        logging.info("stopped by user (Ctrl+C)")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
