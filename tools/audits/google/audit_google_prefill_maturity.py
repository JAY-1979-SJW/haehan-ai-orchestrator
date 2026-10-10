"""Audit Google approval actions against the strict prefill completion bar.

The regular Google live-input coverage proves that every approval action has a
safe no-final-submit path. This stricter audit separates that from the user's
target operating model: domain-specific prefill with only the final approval
left to the user.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT = ROOT / "data" / "google_prefill_maturity_latest.json"


def build_report() -> dict[str, Any]:
    from scripts.google.common import live_inputs

    coverage = live_inputs.build_live_input_coverage()
    counts = coverage["counts"]
    status = "strict_prefill_complete" if counts["strict_prefill_gaps"] == 0 else "strict_prefill_gaps_detected"
    return {
        "schema_version": 1,
        "status": status,
        "ok": counts["strict_prefill_gaps"] == 0,
        "policy": {
            "live_input_supported_is_not_enough": True,
            "completion_bar": "domain_specific_prefill_final_approval_only",
            "generic_handoff_counts_as_gap": True,
            "partial_create_or_release_handoff_counts_as_gap": True,
            "raw_secret_output_allowed": False,
        },
        "counts": {
            "approval_actions": counts["approval_actions"],
            "live_input_supported": counts["live_input_supported"],
            "domain_specific_prefill": counts["domain_specific_prefill"],
            "generic_handoff": counts["generic_handoff"],
            "partial_handoff": counts["partial_handoff"],
            "prepare_or_open_only": counts["prepare_or_open_only"],
            "strict_prefill_gaps": counts["strict_prefill_gaps"],
        },
        "priority_gaps": [
            item
            for item in coverage["strict_prefill_gaps"]
            if item["action_key"] in {"cloud_create_api_credential", "ai_studio_create_api_key"}
        ],
        "priority_ready": [
            item
            for item in coverage["domain_specific_prefill"]
            if item["action_key"] in {"cloud_create_api_credential", "ai_studio_create_api_key"}
        ],
        "strict_prefill_gaps": coverage["strict_prefill_gaps"],
        "domain_specific_prefill": coverage["domain_specific_prefill"],
        "secret_values_output": False,
        "next_step": (
            "Build domain-specific prefill adapters for priority key issuance, then replace generic handoffs per domain."
            if counts["strict_prefill_gaps"]
            else "Strict Google prefill bar is complete."
        ),
    }


def save_report(report: dict[str, Any] | None = None) -> Path:
    payload = report or build_report()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return REPORT


def render_text(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        "Google prefill maturity audit",
        f"status: {report['status']}",
        f"approval_actions: {counts['approval_actions']}",
        f"live_input_supported: {counts['live_input_supported']}",
        f"domain_specific_prefill: {counts['domain_specific_prefill']}",
        f"generic_handoff: {counts['generic_handoff']}",
        f"partial_handoff: {counts['partial_handoff']}",
        f"strict_prefill_gaps: {counts['strict_prefill_gaps']}",
    ]
    if report["priority_gaps"]:
        lines.append("")
        lines.append("priority_gaps:")
        lines.extend(f"- {item['action_key']}: {item['live_input_mode']}" for item in report["priority_gaps"])
    if report.get("priority_ready"):
        lines.append("")
        lines.append("priority_ready:")
        lines.extend(f"- {item['action_key']}: {item['live_input_mode']}" for item in report["priority_ready"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit strict Google prefill maturity.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-gaps", action="store_true")
    args = parser.parse_args(argv)

    report = build_report()
    save_report(report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 1 if args.fail_on_gaps and not report["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
