"""Naver 검색 수집 운영 점검 CLI.

기능 (모두 read-only):
- sqlite DB 존재/연결 가능 여부
- 테이블 존재 및 row count
- 최근 collected_at
- query 별 최근 수집 시각 상위 N (기본 5)
- state 파일 존재 여부 + 주요 query 키
- DB latest_collected_at 과 state last_collected_at 의 명백한 불일치 감지

출력 맨 끝줄에 "RESULT: PASS|WARN|FAIL" 를 찍어 CI/쉘에서 grep 가능.

중요:
- DB / state 수정 금지.
- 비밀 정보 출력 금지 — 경로는 basename 만 노출.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 패키지 import — 스크립트 단독 실행을 위한 path 보정.
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ai_orchestrator.connectors import (  # noqa: E402
    naver_search_queries as q,
    naver_search_state as state_mod,
)
from ai_orchestrator.connectors.naver_search_run_log import (  # noqa: E402
    load_recent_runs,
)


def _line(label: str, value: object) -> str:
    return f"  {label:<24} {value}"


def _human_path(p: Path) -> str:
    """basename 만 노출해 민감 경로 누출 회피."""
    return p.name


def audit(*, top_n: int = 5, run_log_path=None) -> int:
    """한 번 점검하고 사람이 읽을 요약을 stdout 에 찍는다. 종료코드를 돌려준다.

    exit code:
        0 = PASS, 2 = WARN, 3 = FAIL (예: 점검 자체가 예외로 실패)
    """
    status = q.get_search_status(top_n=top_n, run_log_path=run_log_path)
    lines: list = []
    lines.append("=== Naver Search Collection — Operational Audit ===")
    lines.append(_line("status",               status.status))
    lines.append(_line("db_enabled",           status.db_enabled))
    lines.append(_line("db_exists",            status.db_exists))
    lines.append(_line("db_path_basename",     status.db_path_basename))
    lines.append(_line("state_exists",         status.state_exists))
    lines.append(_line("state_path_basename",  status.state_path_basename))

    if status.row_counts:
        lines.append("  row_counts")
        for k, v in status.row_counts.items():
            lines.append(_line(f"  {k}", v))
    else:
        lines.append(_line("row_counts", "(none)"))

    lines.append("  latest_collected_at")
    lines.append(_line("  blog",     status.latest_collected_at.get("blog") or "-"))
    lines.append(_line("  shopping", status.latest_collected_at.get("shopping") or "-"))

    def _fmt_qlist(header: str, items: list) -> list:
        out = [f"  {header} (top {top_n})"]
        if not items:
            out.append("    (none)")
        else:
            for it in items:
                out.append(
                    f"    - {it.get('query','')[:40]:<40}  "
                    f"{it.get('last_collected_at','') or '-'}"
                )
        return out

    lines.extend(_fmt_qlist("last_blog_queries", status.last_blog_queries))
    lines.extend(_fmt_qlist("last_shop_queries", status.last_shop_queries))

    # state vs DB 불일치 간단 판정:
    # state 에 query 가 기록돼 있는데 DB 에 해당 query row 가 아예 없는 경우만 검출.
    # (반대 케이스는 정상 — DB 는 있고 state 는 insert=0 이어서 안 찍혔을 수 있음.)
    extra_warnings: list = []
    try:
        state = state_mod.load_state()
        for src, table in (
            (state_mod.SOURCE_BLOG, "naver_blog_posts"),
            (state_mod.SOURCE_SHOP, "naver_shopping_items"),
        ):
            queries_in_state = list((state.get(src) or {}).keys())
            for qn in queries_in_state:
                if src == state_mod.SOURCE_BLOG:
                    p = q.search_blog_posts(query=qn, limit=1)
                else:
                    p = q.search_shopping_items(query=qn, limit=1)
                if p.total == 0:
                    extra_warnings.append(f"STATE_HAS_QUERY_BUT_DB_EMPTY:{src}:{qn}")
    except Exception as e:  # noqa: BLE001
        extra_warnings.append(f"STATE_DB_CROSSCHECK_FAILED:{type(e).__name__}")

    # ── 5단계: 실행 기록 기반 판정 ──────────────────────────────────
    try:
        runs = load_recent_runs(10, path=run_log_path)
    except Exception as e:  # noqa: BLE001
        runs = []
        extra_warnings.append(f"RUN_LOG_READ_FAILED:{type(e).__name__}")

    lines.append("  recent_runs")
    if not runs:
        lines.append("    (none)")
        extra_warnings.append("NO_RECENT_RUNS")
    else:
        lines.append(_line("  last_success_at", status.last_success_at or "-"))
        lines.append(_line("  last_warn_at",    status.last_warn_at or "-"))
        lines.append(_line("  last_fail_at",    status.last_fail_at or "-"))
        for r in runs[:5]:
            job = r.get("job_type", "?")
            st = r.get("status", "?")
            ts = (r.get("finished_at") or r.get("started_at") or "")[:19]
            ins = r.get("inserted_count", "-")
            lines.append(f"    [{st}] {job:<10} inserted={ins}  {ts}")

        all_statuses = [r.get("status") for r in runs]
        non_skip = [s for s in all_statuses if s != "skipped"]
        if non_skip and all(s == "fail" for s in non_skip):
            extra_warnings.append("RECENT_RUNS_ALL_FAIL")
        if status.state_exists and not runs:
            extra_warnings.append("STATE_EXISTS_BUT_NO_RUNS")
        if (status.row_counts is not None
                and all(v == 0 for v in status.row_counts.values())
                and runs):
            extra_warnings.append("RUNS_EXIST_BUT_DB_EMPTY")

    all_warnings = list(status.warnings) + extra_warnings
    if all_warnings:
        lines.append("  warnings")
        for w in all_warnings:
            lines.append(f"    - {w}")
    else:
        lines.append(_line("warnings", "(none)"))

    final = "PASS" if not all_warnings else "WARN"
    lines.append(f"RESULT: {final}")
    print("\n".join(lines))
    return 0 if final == "PASS" else 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="네이버 검색 수집 운영 점검 (read-only)",
    )
    parser.add_argument("--top", type=int, default=5,
                        help="query 최상위 N (기본 5)")
    parser.add_argument("--json", action="store_true",
                        help="SearchStatus 원본을 JSON 으로 출력")
    args = parser.parse_args()

    try:
        if args.json:
            status = q.get_search_status(top_n=args.top)
            print(json.dumps(status.to_dict(), ensure_ascii=False, indent=2))
            return 0 if status.status == "PASS" else 2
        return audit(top_n=args.top)
    except Exception as e:  # noqa: BLE001
        print(f"RESULT: FAIL ({type(e).__name__})", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
