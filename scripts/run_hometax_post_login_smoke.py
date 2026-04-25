#!/usr/bin/env python3
"""F-4G-3B — 홈택스 post-login smoke runner.

목적:
  - 대표님이 직접 홈택스에 로그인 + 인증서 + 보안프로그램 설치 + 메뉴 이동을
    모두 끝낸 *후* 화면을 read-only 로 한 번 캡처하고, controlled action plan
    을 표준 JSON / MD 파일로 저장하는 전용 smoke 실행기.
  - 대표님이 긴 ``python -c '...'`` 한 줄을 직접 복붙하지 않아도, 본 스크립트
    하나만 실행하면 동일한 흐름이 재현되도록 한다.

본 스크립트가 절대 수행하지 않는 것 (모듈 ``browser_manual_handoff`` 와 동일 정책):
  - ``page.click`` / ``page.fill`` / ``page.type`` / ``page.press``
  - ``page.keyboard.*`` / ``page.mouse.*``
  - ``page.set_input_files`` / ``page.select_option``
  - 폼 ``submit`` / 파일 다운로드 / 보안프로그램 자동 설치
  - ID / PW / 인증서 비밀번호 / OTP / 보안값 입력
  - ``cookies`` / ``storage_state`` / ``localStorage`` / ``sessionStorage`` 접근
  - input value / textarea value 수집
  - 실제 controlled action 실행 (오직 plan 만 만든다)

흐름:
  1) visible Playwright 브라우저로 ``--url`` 접속.
  2) 콘솔에 "대표님이 직접 로그인하세요" 안내 출력.
  3) ``observe_after_user_ready(...)`` 로 ``--user-ready-seconds`` 만큼 대기 후
     화면을 한 번만 read-only 로 캡처.
  4) ``build_hometax_controlled_action_plan(observer_result)`` 로 controlled
     action plan 빌드.
  5) ``runs/local_agent/hometax_post_login_smoke_YYYYMMDD_HHMMSS.{json,md}``
     로 결과 저장. ``--print-json`` 이 있으면 JSON 도 콘솔로 출력.

판정 보조 (parse 단계의 약식 PASS/WARN/FAIL):
  - observer.success=True + plan.safe_read/download 후보 1개 이상 → PASS
  - 후보가 모두 비어있지만 observer.success=True 이고 page_state 가
    authenticated/unknown → WARN (사용자가 더 깊은 메뉴로 이동 필요)
  - observer 자체가 실패 / forbidden_env / google_open_only 등 → FAIL
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any


DEFAULT_URL = "https://www.hometax.go.kr/"
DEFAULT_WAIT_UNTIL = "networkidle"
DEFAULT_USER_READY_SECONDS = 120
DEFAULT_DWELL_AFTER_CAPTURE_SECONDS = 10
DEFAULT_MAX_TEXT_CHARS = 10_000
DEFAULT_OUT_DIR = os.path.join("runs", "local_agent")

# F-4G-3E — fresh hometax 첫 접속 시 발생 가능한 ERR_CONNECTION_RESET
# 대응. wait_until 변경이 아니라 warmup + retry 로 흡수한다.
DEFAULT_WARMUP_URL = "https://example.com/"
DEFAULT_GOTO_RETRIES = 2
DEFAULT_GOTO_RETRY_DELAY_SECONDS = 1.5
DEFAULT_GOTO_TIMEOUT_MS = 90_000

_TOP_CANDIDATE_LIMIT = 10


# ─── argparse ────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "홈택스 post-login smoke runner — 대표님이 직접 로그인한 화면을 "
            "read-only 로 한 번 관찰하고 controlled action plan 을 저장한다."
        ),
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="대상 URL")
    parser.add_argument(
        "--user-ready-seconds",
        type=int,
        default=DEFAULT_USER_READY_SECONDS,
        help="대표님 수동 로그인/인증/보안설치 대기 시간 (0~180)",
    )
    parser.add_argument(
        "--dwell-after-capture-seconds",
        type=int,
        default=DEFAULT_DWELL_AFTER_CAPTURE_SECONDS,
        help="캡처 후 브라우저 close 까지 화면 유지 시간 (0~30)",
    )
    parser.add_argument(
        "--max-text-chars",
        type=int,
        default=DEFAULT_MAX_TEXT_CHARS,
        help="text_excerpt 길이 상한 (200~50000)",
    )
    parser.add_argument(
        "--out-dir",
        default=DEFAULT_OUT_DIR,
        help="결과 JSON/MD 저장 폴더 (기본 runs/local_agent)",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="결과 JSON 을 콘솔로도 출력",
    )
    # F-4G-3E warmup / retry 옵션.
    parser.add_argument(
        "--warmup-url",
        default=DEFAULT_WARMUP_URL,
        help=(
            "본 target URL 접속 전에 1회 navigate 할 warmup URL "
            "(기본 https://example.com/). 비활성화는 --no-warmup."
        ),
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="warmup URL navigate 를 하지 않는다.",
    )
    parser.add_argument(
        "--goto-retries",
        type=int,
        default=DEFAULT_GOTO_RETRIES,
        help="target URL goto 최대 시도 횟수 (1~5).",
    )
    parser.add_argument(
        "--goto-retry-delay-seconds",
        type=float,
        default=DEFAULT_GOTO_RETRY_DELAY_SECONDS,
        help="goto 재시도 사이 대기 (0~10 초).",
    )
    parser.add_argument(
        "--goto-timeout-ms",
        type=int,
        default=DEFAULT_GOTO_TIMEOUT_MS,
        help="page.goto timeout (1000~60000, 90000은 자동 클립 가능).",
    )
    return parser


# ─── summary / file writers ──────────────────────────────────────────────

def _safe_int_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def build_summary(
    *,
    target_url: str,
    observer: dict[str, Any],
    plan: dict[str, Any],
    cli_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """observer/plan 결과로부터 PASS/WARN/FAIL 판정에 쓰일 요약 카운트.

    F-4G-3E: warmup/retry 메타도 함께 기록한다."""
    obs = observer if isinstance(observer, dict) else {}
    pln = plan if isinstance(plan, dict) else {}
    cli = cli_options if isinstance(cli_options, dict) else {}
    warnings = list(obs.get("warnings") or []) + list(pln.get("warnings") or [])
    return {
        "success": bool(obs.get("success")),
        "title": str(obs.get("title") or "")[:300],
        "final_url_host_path": str(obs.get("final_url_host_path") or ""),
        "page_state": str(obs.get("page_state") or pln.get("page_state") or ""),
        "text_length": _safe_int_count(obs.get("text_length")),
        "links_count": _safe_int_count(obs.get("links_count")),
        "buttons_count": _safe_int_count(obs.get("buttons_count")),
        "forms_count": _safe_int_count(obs.get("forms_count")),
        "inputs_count": _safe_int_count(obs.get("inputs_count")),
        "manual_action_required": bool(pln.get("manual_action_required")),
        "safe_read_candidates_count": _safe_int_count(
            pln.get("safe_read_candidates"),
        ),
        "download_candidates_count": _safe_int_count(
            pln.get("download_candidates"),
        ),
        "blocked_candidates_count": _safe_int_count(
            pln.get("blocked_candidates"),
        ),
        "warnings_count": len(warnings),
        "warmup_attempted": bool(obs.get("warmup_attempted")),
        "warmup_success": bool(obs.get("warmup_success")),
        "warmup_url": str(obs.get("warmup_url") or ""),
        "goto_attempts_used": _safe_int_count(obs.get("goto_attempts_used")),
        "goto_retries": _safe_int_count(cli.get("goto_retries")),
        "goto_retry_delay_seconds": _safe_float(
            cli.get("goto_retry_delay_seconds"),
        ),
        "goto_timeout_ms": _safe_int_count(cli.get("goto_timeout_ms")),
    }


def _safe_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def classify_verdict(summary: dict[str, Any]) -> str:
    """약식 PASS/WARN/FAIL 판정."""
    if not isinstance(summary, dict):
        return "FAIL"
    if not summary.get("success"):
        return "FAIL"
    safe_n = _safe_int_count(summary.get("safe_read_candidates_count"))
    dl_n = _safe_int_count(summary.get("download_candidates_count"))
    if safe_n + dl_n >= 1:
        return "PASS"
    return "WARN"


def build_result_payload(
    *,
    target_url: str,
    observer: dict[str, Any],
    plan: dict[str, Any],
    cli_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = build_summary(
        target_url=target_url,
        observer=observer,
        plan=plan,
        cli_options=cli_options,
    )
    return {
        "target_url": target_url,
        "observer": observer,
        "plan": plan,
        "summary": summary,
    }


def _format_top_candidates(
    items: Any, *, fields: tuple[str, ...], limit: int = _TOP_CANDIDATE_LIMIT,
) -> list[str]:
    out: list[str] = []
    if not isinstance(items, list):
        return out
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        parts: list[str] = []
        for fld in fields:
            val = item.get(fld)
            if val is None or val == "":
                continue
            if isinstance(val, list):
                val = ",".join(str(v) for v in val)
            parts.append(f"{fld}={val}")
        if parts:
            out.append("  - " + " | ".join(parts))
    return out


def render_markdown(
    *,
    target_url: str,
    observer: dict[str, Any],
    plan: dict[str, Any],
    summary: dict[str, Any],
    verdict: str,
    timestamp: str,
) -> str:
    obs = observer if isinstance(observer, dict) else {}
    pln = plan if isinstance(plan, dict) else {}
    sec = pln.get("security_program_signals") or {}
    login_cands = pln.get("login_candidates") or {}

    lines: list[str] = []
    lines.append("# 홈택스 post-login smoke 결과")
    lines.append("")
    lines.append("## 실행 정보")
    lines.append(f"- timestamp: {timestamp}")
    lines.append(f"- target_url: {target_url}")
    lines.append(
        f"- handoff: {obs.get('handoff') or {}}",
    )
    lines.append("")

    lines.append("## observer 요약")
    lines.append(f"- success: {summary.get('success')}")
    lines.append(f"- title: {summary.get('title')!r}")
    lines.append(
        f"- final_url_host_path: {summary.get('final_url_host_path')!r}",
    )
    lines.append(f"- page_state: {summary.get('page_state')!r}")
    lines.append(f"- text_length: {summary.get('text_length')}")
    lines.append(f"- links_count: {summary.get('links_count')}")
    lines.append(f"- buttons_count: {summary.get('buttons_count')}")
    lines.append(f"- forms_count: {summary.get('forms_count')}")
    lines.append(f"- inputs_count: {summary.get('inputs_count')}")
    lines.append("")

    lines.append("## warmup / goto retry (F-4G-3E)")
    lines.append(f"- warmup_attempted: {summary.get('warmup_attempted')}")
    lines.append(f"- warmup_success: {summary.get('warmup_success')}")
    lines.append(f"- warmup_url: {summary.get('warmup_url')!r}")
    lines.append(f"- goto_attempts_used: {summary.get('goto_attempts_used')}")
    lines.append(f"- goto_retries: {summary.get('goto_retries')}")
    lines.append(
        f"- goto_retry_delay_seconds: "
        f"{summary.get('goto_retry_delay_seconds')}",
    )
    lines.append(f"- goto_timeout_ms: {summary.get('goto_timeout_ms')}")
    lines.append("")

    lines.append("## controlled plan 요약")
    lines.append(
        f"- manual_action_required: {summary.get('manual_action_required')}",
    )
    lines.append(
        f"- safe_read_candidates_count: "
        f"{summary.get('safe_read_candidates_count')}",
    )
    lines.append(
        f"- download_candidates_count: "
        f"{summary.get('download_candidates_count')}",
    )
    lines.append(
        f"- blocked_candidates_count: "
        f"{summary.get('blocked_candidates_count')}",
    )
    if isinstance(sec, dict) and sec:
        lines.append(f"- security_program_signals: {sec}")
    if isinstance(login_cands, dict) and login_cands:
        lines.append(
            f"- login_candidates.candidate_count: "
            f"{login_cands.get('candidate_count')}",
        )
        lines.append(
            f"- login_candidates.auth_signals: "
            f"{login_cands.get('auth_signals')}",
        )
    lines.append("")

    lines.append("## safe_read 후보 (최대 10)")
    safe_lines = _format_top_candidates(
        pln.get("safe_read_candidates"),
        fields=("kind", "text", "href", "matched_tokens"),
    )
    lines.extend(safe_lines or ["  (없음)"])
    lines.append("")

    lines.append("## download 후보 (최대 10)")
    dl_lines = _format_top_candidates(
        pln.get("download_candidates"),
        fields=("kind", "text", "href", "matched_tokens"),
    )
    lines.extend(dl_lines or ["  (없음)"])
    lines.append("")

    lines.append("## blocked 후보 (최대 10)")
    bl_lines = _format_top_candidates(
        pln.get("blocked_candidates"),
        fields=("kind", "text", "href", "matched_tokens"),
    )
    lines.extend(bl_lines or ["  (없음)"])
    lines.append("")

    lines.append("## warnings")
    obs_warns = list(obs.get("warnings") or [])
    pln_warns = list(pln.get("warnings") or [])
    if not obs_warns and not pln_warns:
        lines.append("  (없음)")
    else:
        for w in obs_warns:
            lines.append(f"  - observer: {w}")
        for w in pln_warns:
            lines.append(f"  - plan: {w}")
    lines.append("")

    lines.append("## 약식 판정")
    lines.append(f"- verdict: {verdict}")
    lines.append("")
    return "\n".join(lines)


def _ensure_out_dir(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def write_results(
    *,
    out_dir: str,
    target_url: str,
    observer: dict[str, Any],
    plan: dict[str, Any],
    timestamp: str | None = None,
    cli_options: dict[str, Any] | None = None,
) -> dict[str, str]:
    """JSON / MD 결과 파일을 저장하고 두 경로를 반환."""
    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    _ensure_out_dir(out_dir)

    payload = build_result_payload(
        target_url=target_url,
        observer=observer,
        plan=plan,
        cli_options=cli_options,
    )
    summary = payload["summary"]
    verdict = classify_verdict(summary)

    base = f"hometax_post_login_smoke_{ts}"
    json_path = os.path.join(out_dir, base + ".json")
    md_path = os.path.join(out_dir, base + ".md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    md_text = render_markdown(
        target_url=target_url,
        observer=payload["observer"],
        plan=payload["plan"],
        summary=summary,
        verdict=verdict,
        timestamp=ts,
    )
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)

    return {"json_path": json_path, "md_path": md_path, "verdict": verdict}


# ─── main ────────────────────────────────────────────────────────────────

_NOTICE_LINES = (
    "[hometax-post-login-smoke] 브라우저가 열리면 대표님이 직접 홈택스 "
    "로그인/인증을 완료하십시오.",
    "  - AI 는 비밀번호/인증서 비밀번호/OTP/보안값을 입력하지 않습니다.",
    "  - AI 는 어떤 클릭/제출/다운로드도 수행하지 않습니다.",
    "  - 로그인 완료 후 홈 화면 또는 조회하려는 메뉴 화면에서 멈춰두십시오.",
)


def _print_notice() -> None:
    for line in _NOTICE_LINES:
        print(line, flush=True)


def _resolve_repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    # 실행 시점 import — pytest 가 단순히 import 만 해도 외부 접속이
    # 발생하지 않도록 한다.
    sys.path.insert(0, _resolve_repo_root())
    from local_agent.browser_manual_handoff import observe_after_user_ready
    from local_agent.site_adapters.hometax import (
        build_hometax_controlled_action_plan,
    )

    _print_notice()

    warmup_url = None if args.no_warmup else (args.warmup_url or None)
    cli_options = {
        "warmup_url": warmup_url or "",
        "goto_retries": args.goto_retries,
        "goto_retry_delay_seconds": args.goto_retry_delay_seconds,
        "goto_timeout_ms": args.goto_timeout_ms,
    }

    observer = observe_after_user_ready(
        url=args.url,
        wait_until=DEFAULT_WAIT_UNTIL,
        user_ready_seconds=args.user_ready_seconds,
        max_text_chars=args.max_text_chars,
        dwell_after_capture_seconds=args.dwell_after_capture_seconds,
        warmup_url=warmup_url,
        goto_retries=args.goto_retries,
        goto_retry_delay_seconds=args.goto_retry_delay_seconds,
        goto_timeout_ms=args.goto_timeout_ms,
    )
    plan = build_hometax_controlled_action_plan(observer)

    paths = write_results(
        out_dir=args.out_dir,
        target_url=args.url,
        observer=observer,
        plan=plan,
        cli_options=cli_options,
    )

    print(f"[hometax-post-login-smoke] verdict: {paths['verdict']}", flush=True)
    print(f"[hometax-post-login-smoke] json: {paths['json_path']}", flush=True)
    print(f"[hometax-post-login-smoke] md:   {paths['md_path']}", flush=True)

    if args.print_json:
        payload = build_result_payload(
            target_url=args.url,
            observer=observer,
            plan=plan,
            cli_options=cli_options,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0 if paths["verdict"] in ("PASS", "WARN") else 1


if __name__ == "__main__":
    sys.exit(main())
