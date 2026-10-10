#!/usr/bin/env python
"""
G2B 공개 공고 Read-Only Live Suite 실행 스크립트

fixture의 허용 케이스 전체를 순차 live 실행하고
차단 케이스는 gate BLOCK만 확인한다.

실행 환경: 사용자 PC (local-agent 환경) 전용
서버에서 실행 금지.

결과:
- data/reports/g2b/g2b_public_notice_live_execution_YYYYMMDD_HHMMSS.json
- docs/reports/g2b_public_notice_live_execution_YYYYMMDD.md

주의:
- cookie/session/token/password/otp 저장 금지
- body_text_sample 최대 1000자
- 차단 케이스 브라우저 실행 금지
- 서버 환경 실행 금지
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# repo root를 sys.path에 추가
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import argparse  # noqa: E402

from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (  # noqa: E402
    _check_playwright_available,
    run_g2b_public_notice_fixture_live_suite,
)

_FIXTURE_DEFAULT = _repo_root / "tests" / "fixtures" / "g2b_public_notice_workflow_fixture_20260507.json"

_REPORT_JSON_DIR = _repo_root / "data" / "reports" / "g2b"
_REPORT_MD_DIR = _repo_root / "docs" / "reports"


def _build_markdown_report(suite_result: dict, run_ts: str) -> str:
    lines = [
        "# G2B 공개 공고 Read-Only Live Execution 보고서",
        "",
        f"- 실행일시: {run_ts}",
        f"- fixture: {suite_result.get('fixture_path', '')}",
        "",
        "## 요약",
        "",
        "| 항목 | 수 |",
        "|------|-----|",
        f"| 총 케이스 | {suite_result.get('total_cases', 0)} |",
        f"| 허용 케이스 | {suite_result.get('allowed_cases', 0)} |",
        f"| live 실행 완료 | {suite_result.get('live_executed', 0)} |",
        f"| 차단 케이스 | {suite_result.get('blocked_cases', 0)} |",
        f"| gate BLOCK 확인 | {suite_result.get('gate_blocked_confirmed', 0)} |",
        f"| 검증 필요 케이스 | {suite_result.get('needs_verification_cases', 0)} |",
        "",
        "## 정책 준수",
        "",
        "- local_agent_required: True",
        "- server_browser_used: False",
        "- download_auto_allowed: False",
        "- click/type/fill/submit 실행 없음",
        "- cookie/session/token/password/otp 저장 없음",
        "",
        "## 케이스별 결과",
        "",
    ]

    for r in suite_result.get("results", []):
        verdict = r.get("case_verdict", "")
        live = r.get("live_result", {})
        title = live.get("title", "")
        final_url = live.get("final_url", "")
        error = live.get("error", "")

        line = (
            f"- **{r.get('id')}** `{r.get('label')}` "
            f"op={r.get('operation')} expected={r.get('expected_verdict')} "
            f"→ **{verdict}**"
        )
        if title:
            line += f" | title: {title[:80]}"
        if final_url:
            line += f" | final_url: {final_url[:80]}"
        if error:
            line += f" | error: {error[:80]}"
        lines.append(line)

    lines += [
        "",
        "---",
        "보고서 자동 생성. 민감정보 포함 금지.",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="G2B 공개 공고 Read-Only Live Suite")
    parser.add_argument("fixture", nargs="?", default=str(_FIXTURE_DEFAULT))
    parser.add_argument("--mode", choices=["default", "actual-live"], default="default")
    parser.add_argument("--forbid-mock", action="store_true", default=False)
    parser.add_argument("--require-local-agent", action="store_true", default=False)
    parser.add_argument("--fail-on-live-warn", action="store_true", default=False)
    args = parser.parse_args()

    fixture_path = args.fixture
    actual_live = args.mode == "actual-live" or args.require_local_agent
    forbid_mock = args.forbid_mock or args.fail_on_live_warn or actual_live

    # playwright/chromium 상태 확인
    pw_check = _check_playwright_available()
    print(
        f"[G2B Live Suite] playwright: {pw_check['playwright_available']}, chromium: {pw_check['chromium_available']}"
    )
    if actual_live and not pw_check["playwright_available"]:
        print("[G2B Live Suite] FAIL: actual-live 모드인데 playwright 미설치")
        sys.exit(1)
    if actual_live and not pw_check["chromium_available"]:
        print("[G2B Live Suite] FAIL: actual-live 모드인데 chromium 미설치")
        sys.exit(1)

    now = datetime.now(UTC)
    ts_file = now.strftime("%Y%m%d_%H%M%S")
    ts_date = now.strftime("%Y%m%d")
    run_ts = now.isoformat()

    mode_label = "actual-live" if actual_live else "default"
    print(f"[G2B Live Suite] mode={mode_label} forbid_mock={forbid_mock}")
    print(f"[G2B Live Suite] fixture: {fixture_path}")
    print(f"[G2B Live Suite] 실행 시작: {run_ts}")

    suite_result = run_g2b_public_notice_fixture_live_suite(
        fixture_path,
        forbid_mock=forbid_mock,
        actual_live_required=actual_live,
    )

    print(f"[G2B Live Suite] 완료: {suite_result.get('summary', '')}")

    # JSON 저장
    _REPORT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "actual_live" if actual_live else "live"
    json_path = _REPORT_JSON_DIR / f"g2b_public_notice_{suffix}_execution_{ts_file}.json"
    safe_result = {k: v for k, v in suite_result.items()}
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(safe_result, f, ensure_ascii=False, indent=2)
    print(f"[G2B Live Suite] JSON 저장: {json_path}")

    # Markdown 저장
    _REPORT_MD_DIR.mkdir(parents=True, exist_ok=True)
    md_path = _REPORT_MD_DIR / f"g2b_public_notice_{suffix}_execution_{ts_date}.md"
    md_content = _build_markdown_report(suite_result, run_ts)
    with md_path.open("w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[G2B Live Suite] Markdown 저장: {md_path}")


if __name__ == "__main__":
    main()
