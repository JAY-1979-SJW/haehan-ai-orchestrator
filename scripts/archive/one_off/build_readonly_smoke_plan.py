"""ALLOW_REGISTER 후보 기반 readonly smoke plan JSON 생성.

Usage:
    python scripts/build_readonly_smoke_plan.py \
        --site-id g2b \
        --preflight tmp/preflight_g2b.json \
        --output tmp/smoke_plan_g2b.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_orchestrator.local_agent.browser_allowlist_expansion_preflight import VERDICT_ALLOW


_SMOKE_ACTION_MAP = {
    "menu_candidate": "navigate_and_check_label",
    "page_title_candidate": "verify_page_title",
    "table_header_candidate": "verify_table_column",
    "download_link_candidate": "verify_link_visible",
    "field_candidate": "verify_field_visible",
    "button_candidate": "verify_button_visible",
    "submit_button_candidate": "verify_button_visible_no_click",
    "destructive_button_candidate": "verify_button_visible_no_click",
    "file_input_candidate": "verify_input_visible",
}


def build_step(index: int, item: dict) -> dict:
    ctype = item.get("candidate_type", "unknown")
    label = item.get("label", "?")
    action = _SMOKE_ACTION_MAP.get(ctype, "verify_element_visible")
    return {
        "step": index,
        "action": action,
        "candidate_type": ctype,
        "label": label,
        "selector_fingerprint": item.get("selector_fingerprint", ""),
        "risk_level": item.get("risk_level", "LOW"),
        "auto_approve": item.get("auto_approve", False),
        "expected": "visible",
        "no_click": action.endswith("no_click"),
        "no_input": True,
        "execution_mode": "DRY_RUN",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="readonly smoke plan 생성")
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    with open(args.preflight, encoding="utf-8") as f:
        data = json.load(f)

    allowed = [r for r in data.get("results", []) if r.get("verdict") == VERDICT_ALLOW]
    if not allowed:
        print(f"[WARN] ALLOW_REGISTER 후보 없음 — smoke plan 생성 불가")
        sys.exit(1)

    steps = [build_step(i + 1, item) for i, item in enumerate(allowed)]

    plan = {
        "plan_id": f"smoke_plan_{args.site_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "site_id": args.site_id,
        "execution_mode": "DRY_RUN",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_steps": len(steps),
        "constraints": {
            "no_login": True,
            "no_credential_input": True,
            "no_screenshot": True,
            "no_har_capture": True,
            "no_click_submit": True,
            "no_actual_playwright": True,
            "readonly_only": True,
        },
        "steps": steps,
    }

    print(f"[Smoke Plan] site_id={args.site_id}  단계 수={len(steps)}")
    for s in steps:
        icon = "✅" if s["auto_approve"] else "⚠️ "
        print(f"  [{s['step']:02d}] {icon} {s['action']:<35} {s['label']!r}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 저장 완료: {args.output}")
    else:
        print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
