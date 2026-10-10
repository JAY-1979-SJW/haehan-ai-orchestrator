"""dry-run 결과 + preflight 결과를 종합하여 Markdown 리포트 생성.

Usage:
    python scripts/generate_policy_smoke_report.py \
        --site-id g2b \
        --preflight tmp/preflight_g2b.json \
        --smoke-result tmp/smoke_result_g2b.json \
        --output tmp/report_g2b.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent_runtime.runtime.site_profile.browser_allowlist_expansion_preflight import (
    VERDICT_ALLOW,
    VERDICT_BLOCKED,
    VERDICT_REVIEW,
)

_VERDICT_LABEL = {
    VERDICT_ALLOW: "✅ ALLOW_REGISTER",
    VERDICT_REVIEW: "⚠️  REVIEW_REQUIRED",
    VERDICT_BLOCKED: "❌ BLOCKED",
}


def generate_report(site_id: str, preflight: dict, smoke: dict) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    pf_summary = preflight.get("summary", {})
    sm_summary = smoke.get("summary", {})
    constraints = smoke.get("constraints", {})

    lines = [
        f"# Site Policy Smoke Report — {site_id}",
        "",
        f"**생성일시**: {now}",
        "**실행 모드**: DRY_RUN (실제 브라우저 접속 없음)",
        "",
        "---",
        "",
        "## 1. 제약 조건",
        "",
        "| 항목 | 값 |",
        "|---|---|",
    ]
    for k, v in constraints.items():
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "---",
        "",
        "## 2. Preflight 결과",
        "",
        "| 항목 | 건수 |",
        "|---|---|",
        f"| 총 후보 | {pf_summary.get('total', 0)} |",
        f"| ALLOW_REGISTER | {pf_summary.get('allow', 0)} |",
        f"| REVIEW_REQUIRED | {pf_summary.get('review', 0)} |",
        f"| BLOCKED | {pf_summary.get('blocked', 0)} |",
        f"| 자동 승인 가능 | {pf_summary.get('auto_approve', 0)} |",
        "",
        "### 후보 상세",
        "",
        "| # | Verdict | 타입 | 라벨 | 자동승인 |",
        "|---|---|---|---|---|",
    ]
    for i, r in enumerate(preflight.get("results", []), 1):
        verdict = r.get("verdict", "?")
        vl = _VERDICT_LABEL.get(verdict, verdict)
        ctype = r.get("candidate_type", "?")
        label = r.get("label", "?")
        auto = "O" if r.get("auto_approve") else "-"
        lines.append(f"| {i} | {vl} | {ctype} | {label} | {auto} |")

    lines += [
        "",
        "---",
        "",
        "## 3. Dry-run Smoke 결과",
        "",
        "| 항목 | 건수 |",
        "|---|---|",
        f"| 총 단계 | {sm_summary.get('total', 0)} |",
        f"| 통과 | {sm_summary.get('passed', 0)} |",
        f"| 실패 | {sm_summary.get('failed', 0)} |",
        "",
        "### 단계 상세",
        "",
        "| # | 결과 | 액션 | 라벨 |",
        "|---|---|---|---|",
    ]
    for r in smoke.get("step_results", []):
        icon = "✅" if r["passed"] else "❌"
        lines.append(f"| {r['step']} | {icon} {r['result']} | {r['action']} | {r['label']} |")

    passed = sm_summary.get("passed", 0)
    total = sm_summary.get("total", 0)
    overall = "✅ PASS" if passed == total and total > 0 else "❌ FAIL"

    lines += [
        "",
        "---",
        "",
        "## 4. 종합 판정",
        "",
        f"**{overall}** — {passed}/{total} 단계 통과",
        "",
        "---",
        "",
        "*이 리포트는 자동 생성되었습니다. 실제 사이트 접속 없이 dry-run 시뮬레이션 결과입니다.*",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="policy smoke 리포트 생성")
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--smoke-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    with args.preflight.open(encoding="utf-8") as f:
        preflight = json.load(f)
    with args.smoke_result.open(encoding="utf-8") as f:
        smoke = json.load(f)

    report = generate_report(args.site_id, preflight, smoke)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"✅ 리포트 저장: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
