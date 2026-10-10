#!/usr/bin/env python3
"""네이버 수동 로그인 확인 smoke 스크립트.

실행 예:
  python scripts/naver/smoke_naver_manual_login_probe.py --url https://www.naver.com/ --wait-seconds 120

동작:
  - 접속 허용 호스트는 기본으로 www.naver.com / nid.naver.com 만.
  - 브라우저를 headless=False 로 띄우고 사용자가 직접 로그인.
  - 프로그램은 ID/PW 를 입력하지 않고, 쿠키/세션/token 을 수집하지 않는다.
  - 로그인 전/후 구조 요약만 표준 출력으로 보낸다 (HTML 원문 출력 금지).

주의:
  - 이 스크립트는 pytest 로 자동 실행하지 않는다. 사용자가 수동 실행용.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_URL = "https://www.naver.com/"
DEFAULT_ALLOWED_HOSTS = ("www.naver.com", "nid.naver.com")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="네이버 수동 로그인 확인 smoke (read-only probe)",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--wait-seconds", type=int, default=120)
    parser.add_argument("--poll-interval-seconds", type=int, default=3)
    parser.add_argument(
        "--success-url-contains",
        action="append",
        default=None,
        help="current_url 에 포함되면 로그인 완료로 간주할 토큰 (여러 개 가능)",
    )
    parser.add_argument(
        "--success-text-hints",
        action="append",
        default=None,
        help="visible text 에 포함되면 로그인 완료로 간주할 토큰 (여러 개 가능)",
    )
    parser.add_argument(
        "--allow-additional-host",
        action="append",
        default=None,
        help="추가 허용 호스트 (기본 네이버 도메인 외). 주의: 확신한 경우에만.",
    )
    return parser


def _redact_for_print(result: dict) -> dict:
    """요약 출력 안전 필드만 남긴다. HTML/쿠키/세션/password 값은 절대 출력 금지."""
    if not isinstance(result, dict):
        return {"ok": False, "error_code": "INVALID_RESULT"}

    out: dict = {
        "ok": bool(result.get("ok")),
        "mode": result.get("mode"),
        "url": result.get("url"),
        "summary": result.get("summary"),
        "warnings": list(result.get("warnings") or []),
    }
    if "error_code" in result:
        out["error_code"] = result["error_code"]

    for key in ("initial", "after", "last_observation"):
        obs = result.get(key)
        if not isinstance(obs, dict):
            continue
        compact: dict = {
            "title": obs.get("title", ""),
            "current_url": obs.get("current_url", ""),
            "login_required_hint": obs.get("login_required_hint"),
            "login_reason": list(obs.get("login_reason") or []),
        }
        if "login_completed_hint" in obs:
            compact["login_completed_hint"] = obs["login_completed_hint"]
        if "login_completion_reason" in obs:
            compact["login_completion_reason"] = list(obs.get("login_completion_reason") or [])
        struct = obs.get("page_structure")
        if isinstance(struct, dict):
            counts = struct.get("counts") or {}
            compact["structure_counts"] = {
                "links": int(counts.get("links") or 0),
                "buttons": int(counts.get("buttons") or 0),
                "forms": int(counts.get("forms") or 0),
                "inputs": int(counts.get("inputs") or 0),
                "tables": int(counts.get("tables") or 0),
                "headings": int(counts.get("headings") or 0),
            }
        out[key] = compact
    return out


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # import 는 실행 시점에만 — pytest 가 실수로 import 만 해도 외부 접속이
    # 발생하지 않도록 한다.
    _root = str(Path(__file__).resolve().parents[2])  # 저장소 루트 — local_agent import 용 sys.path 부트스트랩
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    allowed_hosts = list(DEFAULT_ALLOWED_HOSTS)
    for h in args.allow_additional_host or []:
        if h and h not in allowed_hosts:
            allowed_hosts.append(h)

    print(
        "[manual-login-probe] 사용자가 직접 네이버에 로그인해야 합니다.\n"
        "  - 프로그램은 ID/PW 를 입력하지 않습니다.\n"
        "  - 프로그램은 쿠키/세션을 수집하지 않습니다.\n"
        "  - 프로그램은 로그인 전/후 화면 구조만 읽습니다.",
        flush=True,
    )

    result = probe_manual_login_flow(
        url=args.url,
        wait_seconds=args.wait_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        success_url_contains=args.success_url_contains,
        success_text_hints=args.success_text_hints,
        allowed_hosts=allowed_hosts,
    )

    safe = _redact_for_print(result)
    print(json.dumps(safe, ensure_ascii=False, indent=2))
    return 0 if safe.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
