"""Google module check facade.

The locked contracts and index builder live in smaller modules. This file keeps
the public CLI/import surface stable for router, tests, and ops audits.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.google import work_records
from scripts.google.module_index_builder import build_google_module_index

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "data" / "google_module_checks"
LATEST_REPORT = ROOT / "data" / "google_module_check_latest.json"


def save_google_module_index(payload: dict[str, Any] | None = None, path: Path | None = None) -> Path:
    payload = payload or build_google_module_index()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if path is None:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        path = REPORT_DIR / f"google_module_check_{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    LATEST_REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_google_module_summary(payload: dict[str, Any], path: Path | None = None) -> None:
    print("=" * 60)
    print("Google module check")
    print("=" * 60)
    print(f"ok: {payload['ok']}")
    print(f"top_module: {payload['top_module']['key']}")
    print(f"submodules: {payload['submodule_count']}")
    print(f"domain_modules: {payload['domain_module_count']}")
    print(f"page_tab_modules: {payload['page_tab_module_count']}")
    print(f"work_action_modules: {payload['work_action_module_count']}")
    print(f"input_field_modules: {payload['input_field_module_count']}")
    print(f"final_control_modules: {payload['final_control_module_count']}")
    print(f"evidence_modules: {payload['evidence_module_count']}")
    print(f"surfaces: {payload['surface_count']}")
    for item in payload["submodules"]:
        print(
            f"- {item['group']}: surfaces={item['surface_count']} "
            f"approval={item['approval_surface_count']} status={item['status']}"
        )
    if path:
        print(f"saved: {path}")
    print("=" * 60)


def record_google_module_check(payload: dict[str, Any], path: Path | str | None = None) -> dict[str, Any]:
    report = str(path or LATEST_REPORT)
    status = "PASS" if payload.get("ok") else "FAIL"
    return work_records.checkpoint(
        step=(
            "google module boundary checkpoint: "
            f"status={status}, submodules={payload.get('submodule_count')}, "
            f"domain_modules={payload.get('domain_module_count')}, "
            f"page_tabs={payload.get('page_tab_module_count')}, "
            f"actions={payload.get('work_action_module_count')}"
        ),
        command="python scripts/entry/cdp_cli.py google check",
        verification=f"google_module_check ok={payload.get('ok')}",
        report=report,
        touched=[
            "scripts/google/module_contracts.py",
            "scripts/google/module_index_builder.py",
            "scripts/google/module_check.py",
            "scripts/google/router.py",
            "scripts/google/work_records.py",
        ],
        next_step="review google lane history before changing google module boundaries",
    )


def main() -> int:
    payload = build_google_module_index()
    path = save_google_module_index(payload)
    record_google_module_check(payload, path)
    print_google_module_summary(payload, path)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
