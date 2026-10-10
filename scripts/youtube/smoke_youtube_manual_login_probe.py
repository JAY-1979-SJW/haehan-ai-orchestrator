#!/usr/bin/env python3
"""유튜브/구글 계정 수동 로그인 확인 smoke 스크립트.

실행 예:
  python scripts/youtube/smoke_youtube_manual_login_probe.py \
    --url https://www.youtube.com --wait-seconds 180 \
    --require-visible-confirm --require-user-login-confirm \
    --keep-open --browser-channel chrome

동작:
  - 접속 허용 호스트는 기본으로 youtube.com / www.youtube.com /
    studio.youtube.com / accounts.google.com / myaccount.google.com.
  - 브라우저를 headless=False 로 띄우고 bring_to_front 로 앞으로 끌어
    올린다. 사용자가 직접 로그인한다.
  - 프로그램은 ID/PW 를 입력하지 않고, 쿠키/세션/token 을 수집하지 않는다.
  - 로그인 전/후 구조 요약만 표준 출력으로 보낸다 (HTML 원문 출력 금지).
  - 댓글/구독/좋아요/업로드/설정 변경은 절대 수행하지 않는다.

가시성 / 수동 확인 옵션:
  --require-visible-confirm
      브라우저가 열린 뒤, 사용자가 "실제 창을 봤다" 고 Enter 를 누르기
      전까지 polling 으로 넘어가지 않는다.
  --require-user-login-confirm
      구조 변화가 감지되더라도 프로그램이 login_completed_hint=True 를
      단정하지 않는다. 사용자가 Enter 로 "로그인 완료 화면" 을 확인해야
      True 로 올라간다. 이 경우 reason 에 user_confirmed_login 이 추가된다.
  --keep-open
      판정이 끝난 뒤 브라우저를 바로 닫지 않고 Enter 입력을 기다린다.
  --browser-channel chromium|chrome|msedge
      실제 사용자 브라우저 창을 쓰고 싶을 때 지정 (기본 chromium).

주의:
  - 이 스크립트는 pytest 로 자동 실행하지 않는다. 사용자가 수동 실행용.
  - Google 계정 설정 페이지로 이동하더라도 어떤 변경도 하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_URL = "https://www.youtube.com"

DEFAULT_ALLOWED_HOSTS = (
    "youtube.com",
    "www.youtube.com",
    "studio.youtube.com",
    "accounts.google.com",
    "myaccount.google.com",
)

# URL 에 포함되면 로그인 완료 가능성으로 간주하는 기본 토큰.
# 계정명/이메일/채널명은 포함하지 않는다 (업무별 힌트는 CLI 로만 받음).
DEFAULT_SUCCESS_URL_CONTAINS = (
    "youtube.com",
    "studio.youtube.com",
)

_VALID_BROWSER_CHANNELS = ("chromium", "chrome", "msedge")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="유튜브/구글 수동 로그인 확인 smoke (read-only probe)",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--wait-seconds", type=int, default=180)
    parser.add_argument("--poll-interval-seconds", type=int, default=3)
    parser.add_argument(
        "--success-url-contains",
        action="append",
        default=None,
        help=(
            "current_url 에 포함되면 로그인 완료 후보로 간주할 토큰. "
            "success_url_match 단독으로는 login_completed_hint=True 가 "
            "되지 않는다 — 반드시 url_changed / password_input_disappeared / "
            "login_required_hint_cleared / success_text_match / "
            "user_confirmed_login 중 하나가 함께 있어야 한다."
        ),
    )
    parser.add_argument(
        "--success-text-hints",
        action="append",
        default=None,
        help="visible text 에 포함되면 로그인 완료 후보로 간주할 토큰 (여러 개).",
    )
    parser.add_argument(
        "--allow-additional-host",
        action="append",
        default=None,
        help="추가 허용 호스트 (기본 목록 외). 확신한 경우에만 사용.",
    )
    parser.add_argument(
        "--browser-channel",
        choices=_VALID_BROWSER_CHANNELS,
        default="chromium",
        help=(
            "사용할 Chromium 채널. 실제 사용자 브라우저 창을 쓰고 싶으면 "
            "chrome 또는 msedge 를 지정. 미설치면 명확한 에러를 반환."
        ),
    )
    parser.add_argument(
        "--require-visible-confirm",
        action="store_true",
        help=("브라우저 창이 실제 화면에 보인다고 사용자가 Enter 로 확인하기 전까지 polling 루프로 넘어가지 않음."),
    )
    parser.add_argument(
        "--require-user-login-confirm",
        action="store_true",
        help=(
            "구조적 근거만으로 login_completed_hint=True 를 단정하지 않음. "
            "사용자가 Enter 를 눌러 확인해야만 True 로 승격된다."
        ),
    )
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="판정 종료 뒤 브라우저를 바로 닫지 않고 Enter 입력을 기다림.",
    )
    parser.add_argument(
        "--slow-mo-ms",
        type=int,
        default=0,
        help="각 브라우저 조작 사이에 지연을 추가 (최대 2000ms).",
    )
    parser.add_argument(
        "--viewport",
        default=None,
        help="viewport 크기 (예: 1280x800). 미지정이면 기본값.",
    )
    return parser


def _parse_viewport(value: str | None) -> dict | None:
    if not value:
        return None
    try:
        w_s, h_s = value.lower().split("x", 1)
        w = int(w_s)
        h = int(h_s)
    except Exception:  # noqa: BLE001 - "WIDTHxHEIGHT" 형식 문자열 파싱 실패 시 None을 반환하는 안전한 기본값, 로그인 여부와 무관한 화면 크기 파싱 유틸.
        return None
    if w <= 0 or h <= 0:
        return None
    return {"width": w, "height": h}


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
        "visible_confirmed_by_user": bool(result.get("visible_confirmed_by_user", False)),
        "login_confirmed_by_user": bool(result.get("login_confirmed_by_user", False)),
        "login_state_hint": result.get("login_state_hint"),
        "login_completed_hint": bool(result.get("login_completed_hint", False)),
        "login_completion_reason": list(result.get("login_completion_reason") or []),
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
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # 저장소 루트
    from core.agent_runtime.browser.browser_login_probe import probe_manual_login_flow

    allowed_hosts = list(DEFAULT_ALLOWED_HOSTS)
    for h in args.allow_additional_host or []:
        if h and h not in allowed_hosts:
            allowed_hosts.append(h)

    success_urls = args.success_url_contains
    if success_urls is None:
        success_urls = list(DEFAULT_SUCCESS_URL_CONTAINS)

    viewport = _parse_viewport(args.viewport)

    print(
        "[manual-login-probe] 사용자가 직접 구글/유튜브에 로그인해야 합니다.\n"
        "  - 프로그램은 ID/PW 를 입력하지 않습니다.\n"
        "  - 프로그램은 쿠키/세션/token 을 수집하지 않습니다.\n"
        "  - 프로그램은 로그인 전/후 화면 구조만 읽습니다.\n"
        "  - 댓글/구독/좋아요/업로드/설정 변경은 수행하지 않습니다.\n"
        f"  - browser_channel={args.browser_channel}, "
        f"require_visible_confirm={args.require_visible_confirm}, "
        f"require_user_login_confirm={args.require_user_login_confirm}, "
        f"keep_open={args.keep_open}",
        flush=True,
    )

    result = probe_manual_login_flow(
        url=args.url,
        wait_seconds=args.wait_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        success_url_contains=success_urls,
        success_text_hints=args.success_text_hints,
        allowed_hosts=allowed_hosts,
        browser_channel=args.browser_channel,
        require_visible_confirm=args.require_visible_confirm,
        require_user_login_confirm=args.require_user_login_confirm,
        keep_open=args.keep_open,
        slow_mo_ms=max(0, int(args.slow_mo_ms or 0)),
        viewport=viewport,
    )

    safe = _redact_for_print(result)
    print(json.dumps(safe, ensure_ascii=False, indent=2))
    return 0 if safe.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
