"""smoke plan dry-run 실행기. 실제 브라우저/Playwright 호출 없음.

Usage:
    python scripts/run_readonly_smoke_dryrun.py \
        --plan tmp/smoke_plan_g2b.json \
        --output tmp/smoke_result_g2b.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_DRYRUN_PASS_ACTIONS = frozenset({
    "navigate_and_check_label",
    "verify_page_title",
    "verify_table_column",
    "verify_link_visible",
    "verify_field_visible",
    "verify_button_visible",
    "verify_button_visible_no_click",
    "verify_input_visible",
    "verify_element_visible",
})

_DRYRUN_BLOCKED_ACTIONS = frozenset({
    "click",
    "submit",
    "type",
    "fill",
    "download",
    "upload",
    "screenshot",
    "har_capture",
    "login",
    "authenticate",
})


def simulate_step(step: dict) -> dict:
    action = step.get("action", "")
    label = step.get("label", "?")
    no_click = step.get("no_click", False)
    no_input = step.get("no_input", True)
    execution_mode = step.get("execution_mode", "DRY_RUN")

    if execution_mode != "DRY_RUN":
        return {
            "step": step["step"],
            "action": action,
            "label": label,
            "result": "BLOCKED",
            "reason": f"execution_mode={execution_mode}는 dry-run에서 허용 안 됨",
            "passed": False,
        }

    if action in _DRYRUN_BLOCKED_ACTIONS:
        return {
            "step": step["step"],
            "action": action,
            "label": label,
            "result": "BLOCKED",
            "reason": f"dry-run에서 금지된 액션: {action}",
            "passed": False,
        }

    if action not in _DRYRUN_PASS_ACTIONS:
        return {
            "step": step["step"],
            "action": action,
            "label": label,
            "result": "SKIPPED",
            "reason": f"알 수 없는 액션 — dry-run 스킵: {action}",
            "passed": False,
        }

    return {
        "step": step["step"],
        "action": action,
        "label": label,
        "result": "DRY_RUN_PASS",
        "reason": "dry-run 시뮬레이션 통과 (실제 브라우저 접속 없음)",
        "passed": True,
        "no_click": no_click,
        "no_input": no_input,
        "selector_fingerprint": step.get("selector_fingerprint", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="smoke plan dry-run 실행")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)

    site_id = plan.get("site_id", "?")
    plan_id = plan.get("plan_id", "?")
    steps = plan.get("steps", [])
    constraints = plan.get("constraints", {})

    print(f"\n[Dry-run] site_id={site_id}  plan_id={plan_id}")
    print(f"  총 {len(steps)}단계  (실제 브라우저 접속 없음)")
    print()

    step_results = [simulate_step(s) for s in steps]

    passed = sum(1 for r in step_results if r["passed"])
    failed = len(step_results) - passed

    for r in step_results:
        icon = "✅" if r["passed"] else ("❌" if r["result"] == "BLOCKED" else "⚠️ ")
        print(f"  [{r['step']:02d}] {icon} {r['action']:<35} {r['label']!r}  → {r['result']}")

    print(f"\n결과: {passed}/{len(step_results)} 통과")

    output_data = {
        "plan_id": plan_id,
        "site_id": site_id,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "execution_mode": "DRY_RUN",
        "constraints": constraints,
        "summary": {
            "total": len(step_results),
            "passed": passed,
            "failed": failed,
        },
        "step_results": step_results,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"✅ 저장 완료: {args.output}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
