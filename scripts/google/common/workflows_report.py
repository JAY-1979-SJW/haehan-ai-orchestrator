"""Print summary helpers for Google work catalogs and reports."""
from __future__ import annotations

from pathlib import Path

from scripts.google.common.workflows_common import LATEST_ACTION_CATALOG, LATEST_ADAPTER_CATALOG, LATEST_UNDEVELOPED_REPORT


def print_action_summary(catalog: dict, path: Path) -> None:
    print("=" * 60)
    print("Google work action catalog")
    print("=" * 60)
    print(f"saved: {path}")
    print(f"latest: {LATEST_ACTION_CATALOG}")
    print(f"actions: {catalog['counts']['actions']}")
    print(f"read_actions: {catalog['counts']['read_actions']}")
    print(f"approval_actions: {catalog['counts']['approval_actions']}")
    print(f"adapter_profiles: {catalog['counts']['adapter_profiles']}")
    for item in catalog["actions"]:
        gate = "approval" if item["requires_approval"] else "read"
        print(f"- {item['key']}: {item['surface_key']} [{gate}] {item['status']}")


def print_adapter_summary(catalog: dict, path: Path) -> None:
    print("=" * 60)
    print("Google execution adapter catalog")
    print("=" * 60)
    print(f"saved: {path}")
    print(f"latest: {LATEST_ADAPTER_CATALOG}")
    print(f"adapter_profiles: {catalog['counts']['adapter_profiles']}")
    print(f"live_browser_capable: {catalog['counts']['live_browser_capable']}")
    print(f"approval_handoff: {catalog['counts']['approval_handoff']}")
    for item in catalog["adapters"]:
        print(
            f"- {item['action_key']}: {item['adapter_key']} "
            f"[{item['implementation_status']}]"
        )


def print_undeveloped_summary(report: dict, path: Path) -> None:
    print("=" * 60)
    print("Google undeveloped work report")
    print("=" * 60)
    print(f"saved: {path}")
    print(f"latest: {LATEST_UNDEVELOPED_REPORT}")
    print(f"actions: {report['counts']['actions']}")
    print(f"readonly_complete: {report['counts']['readonly_complete']}")
    print(f"approval_actions: {report['counts']['approval_actions']}")
    print(f"live_input_supported: {report['counts']['live_input_supported']}")
    print(f"prepare_or_open_only: {report['counts']['prepare_or_open_only']}")
    print(f"production_final_blocked: {report['counts']['production_final_blocked']}")
    print(f"missing_adapter_profiles: {report['counts']['missing_adapter_profiles']}")
    print("prepare_or_open_only:")
    for item in report["prepare_or_open_only"]:
        print(f"- {item['action_key']}: {item['surface_key']} {item['operation']}")
