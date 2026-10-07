"""live_inputs 커버리지 리포트 (leaf).

어댑터/모드 기반 prefill 성숙도 커버리지 집계·저장·출력. config(공유 leaf)+
workflows 의존. [docs/module_separation_standard.md]
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts.google.common.report_io import save_json_with_latest

from scripts.google.common import workflows
from scripts.google.common.live_inputs_config import LIVE_INPUT_ADAPTERS, DOMAIN_SPECIFIC_PREFILL_MODES, GENERIC_HANDOFF_MODES, PARTIAL_HANDOFF_MODES, LIVE_INPUT_COVERAGE_DIR, LATEST_LIVE_INPUT_COVERAGE, FINAL_CONTROL_LABELS

def build_live_input_coverage() -> dict:
    """Build live-fill support coverage against the Google work catalog."""
    actions = [item for item in workflows.build_action_catalog()["actions"] if item["requires_approval"]]
    supported: list[dict] = []
    unsupported: list[dict] = []
    domain_specific_prefill: list[dict] = []
    generic_handoff: list[dict] = []
    partial_handoff: list[dict] = []
    for action in actions:
        item = {
            "action_key": action["key"],
            "surface_key": action["surface_key"],
            "operation": action["operation"],
            "required_inputs": action["required_inputs"],
            "approval_required": action["requires_approval"],
        }
        mode = LIVE_INPUT_ADAPTERS.get(action["key"])
        if mode:
            item["live_input_mode"] = mode
            item["final_state_policy"] = "no_final_submit_only"
            supported.append(item)
            if mode in DOMAIN_SPECIFIC_PREFILL_MODES:
                item["prefill_maturity"] = "domain_specific_final_approval_ready"
                domain_specific_prefill.append(item)
            elif mode in GENERIC_HANDOFF_MODES:
                item["prefill_maturity"] = "generic_handoff_needs_domain_prefill"
                generic_handoff.append(item)
            elif mode in PARTIAL_HANDOFF_MODES:
                item["prefill_maturity"] = "partial_handoff_needs_domain_prefill"
                partial_handoff.append(item)
            else:
                item["prefill_maturity"] = "unknown_handoff_needs_review"
                partial_handoff.append(item)
        else:
            item["live_input_mode"] = "open_only_or_prepare_only"
            item["final_state_policy"] = "approval_handoff_required"
            item["prefill_maturity"] = "unsupported"
            unsupported.append(item)
    strict_prefill_gaps = generic_handoff + partial_handoff + unsupported
    coverage = {
        "site_id": "google",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "default": "prepare_all_actions_but_live_fill_only_supported_adapters",
            "strict_completion": "domain_specific_prefill_only_counts_as_final_approval_ready",
            "final_controls": list(FINAL_CONTROL_LABELS),
            "manifest_template": "configs/google_live_input_manifest_template.json",
        },
        "counts": {
            "approval_actions": len(actions),
            "live_input_supported": len(supported),
            "prepare_or_open_only": len(unsupported),
            "domain_specific_prefill": len(domain_specific_prefill),
            "generic_handoff": len(generic_handoff),
            "partial_handoff": len(partial_handoff),
            "strict_prefill_gaps": len(strict_prefill_gaps),
        },
        "supported": supported,
        "prepare_or_open_only": unsupported,
        "domain_specific_prefill": domain_specific_prefill,
        "generic_handoff": generic_handoff,
        "partial_handoff": partial_handoff,
        "strict_prefill_gaps": strict_prefill_gaps,
    }
    return coverage


def save_live_input_coverage(coverage: dict | None = None, path: Path | None = None) -> Path:
    coverage = coverage or build_live_input_coverage()
    return save_json_with_latest(coverage, LIVE_INPUT_COVERAGE_DIR, LATEST_LIVE_INPUT_COVERAGE, "google_live_input_coverage", path)


def print_live_input_coverage(coverage: dict, path: Path) -> None:
    print("=" * 60)
    print("Google live input coverage")
    print("=" * 60)
    print(f"saved: {path}")
    print(f"latest: {LATEST_LIVE_INPUT_COVERAGE}")
    print(f"approval_actions: {coverage['counts']['approval_actions']}")
    print(f"live_input_supported: {coverage['counts']['live_input_supported']}")
    print(f"prepare_or_open_only: {coverage['counts']['prepare_or_open_only']}")
    print(f"domain_specific_prefill: {coverage['counts']['domain_specific_prefill']}")
    print(f"generic_handoff: {coverage['counts']['generic_handoff']}")
    print(f"partial_handoff: {coverage['counts']['partial_handoff']}")
    print(f"strict_prefill_gaps: {coverage['counts']['strict_prefill_gaps']}")
    print("supported:")
    for item in coverage["supported"]:
        print(f"- {item['action_key']}: {item['live_input_mode']}")
