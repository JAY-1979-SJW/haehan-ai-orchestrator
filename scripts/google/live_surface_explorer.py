"""Direct-CDP read-only explorer for Google surfaces.

This explorer uses the already-running local Chrome debugging profile. It does
not click, type, submit, export cookies, export storage, or read secret values.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.browser.cdp.cdp_console import connect
from scripts.google.common import surfaces, tab_logic
from scripts.google.cloud.live_console_explorer import (
    _extract_visible_console_snapshot,
    _redact_text,
    _redact_url,
    _risk_controls,
    load_latest_cloud_console_live_report,
)
from scripts.google.common.report_io import save_json_with_latest

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "data" / "google_surface_live"
LATEST_REPORT = ROOT / "data" / "google_surface_live_latest.json"


def _utc() -> str:
    return datetime.now(UTC).isoformat()


def _surface_tab_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for tab in tab_logic.build_all_tab_logic_catalog()["tabs"]:
        for surface in tab["surfaces"]:
            mapping[surface["key"]] = tab["tab_key"]
    return mapping


def select_surfaces(
    *,
    keys: list[str] | None = None,
    tabs: list[str] | None = None,
    exclude_tabs: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    catalog = surfaces.build_surface_catalog()["surfaces"]
    tab_by_surface = _surface_tab_map()
    selected = catalog
    if keys:
        wanted = set(keys)
        selected = [item for item in selected if item["key"] in wanted]
    if tabs:
        wanted_tabs = set(tabs)
        selected = [item for item in selected if tab_by_surface.get(item["key"]) in wanted_tabs]
    if exclude_tabs:
        blocked_tabs = set(exclude_tabs)
        selected = [item for item in selected if tab_by_surface.get(item["key"]) not in blocked_tabs]
    if limit is not None:
        selected = selected[:limit]
    return selected


def explore_google_surfaces_direct_cdp(
    *,
    keys: list[str] | None = None,
    tabs: list[str] | None = None,
    exclude_tabs: list[str] | None = None,
    wait_seconds: float = 3.0,
    limit: int | None = None,
    snapshot_limit: int = 80,
) -> tuple[dict[str, Any], Path]:
    selected = select_surfaces(keys=keys, tabs=tabs, exclude_tabs=exclude_tabs, limit=limit)
    tab_by_surface = _surface_tab_map()
    report: dict[str, Any] = {
        "site_id": "google",
        "generated_at": _utc(),
        "mode": "direct_cdp_read_only_no_click",
        "policy": {
            "entrypoint": "https://www.google.com/",
            "same_profile_subdomain_navigation": True,
            "no_click": True,
            "no_input": True,
            "no_submit": True,
            "cookie_export": False,
            "storage_export": False,
        },
        "filters": {
            "keys": keys or [],
            "tabs": tabs or [],
            "exclude_tabs": exclude_tabs or [],
            "limit": limit,
        },
        "counts": {
            "planned": len(selected),
            "visited": 0,
            "failed": 0,
            "risk_controls_detected": 0,
        },
        "surfaces": [],
    }
    try:
        with connect() as session:
            for item in selected:
                result = {
                    "key": item["key"],
                    "tab_key": tab_by_surface.get(item["key"], ""),
                    "label": item["label"],
                    "catalog_url": item["url"],
                    "catalog_risk": item["risk"],
                    "status": "started",
                    "visited_at": _utc(),
                    "final_url": "",
                    "title": "",
                    "headings": [],
                    "controls": [],
                    "nav": [],
                    "inputs": [],
                    "risk_controls": [],
                    "warnings": [],
                }
                try:
                    session.goto(item["url"], wait_idle=False)
                    session.wait(wait_seconds)
                    snapshot = _extract_visible_console_snapshot(session, limit=snapshot_limit)
                    result.update(snapshot)
                    result["final_url"] = _redact_url(str(snapshot.get("url", "")))
                    result["title"] = _redact_text(snapshot.get("title", ""))
                    result["risk_controls"] = _risk_controls(snapshot.get("controls", []))
                    result["status"] = "visited"
                    report["counts"]["visited"] += 1
                    if result["risk_controls"]:
                        report["counts"]["risk_controls_detected"] += 1
                except Exception as exc:  # noqa: BLE001 - 구글 서비스 표면 라이브 탐색(읽기 전용) -- 개별 화면 방문 실패는 report에 failed로 기록하고 계속, 예외 텍스트는 _redact_text로 민감정보를 제거한 뒤 저장
                    result["status"] = "failed"
                    result["warnings"].append(_redact_text(exc))
                    report["counts"]["failed"] += 1
                report["surfaces"].append(result)
    except Exception as exc:  # noqa: BLE001 - 구글 서비스 표면 라이브 탐색(읽기 전용) -- 개별 화면 방문 실패는 report에 failed로 기록하고 계속, 예외 텍스트는 _redact_text로 민감정보를 제거한 뒤 저장
        report["status"] = "failed"
        report["warnings"] = [_redact_text(exc)]
        report["counts"]["failed"] = len(selected)
        return save_google_surface_live_report(report)

    report["status"] = "completed"
    return save_google_surface_live_report(report)


def save_google_surface_live_report(report: dict[str, Any], path: Path | None = None) -> tuple[dict[str, Any], Path]:
    target = save_json_with_latest(report, REPORT_DIR, LATEST_REPORT, "google_surface_live", path, ensure_ascii=True)
    return report, target


def load_latest_google_surface_live_report(path: Path | None = None) -> dict[str, Any]:
    source = path or LATEST_REPORT
    if not source.exists():
        return {
            "site_id": "google",
            "status": "missing",
            "counts": {"planned": 0, "visited": 0, "failed": 0, "risk_controls_detected": 0},
            "surfaces": [],
        }
    return json.loads(source.read_text(encoding="utf-8"))


def build_google_surface_live_logic(report: dict[str, Any] | None = None) -> dict[str, Any]:
    source_reports: list[dict[str, Any]] = []
    if report is None:
        report = load_latest_google_surface_live_report()
        source_reports.append(report)
        cloud_keys = {surface["key"] for surface in tab_logic.build_tab_logic_catalog("cloud")["surfaces"]}
        live_cloud_keys = {
            item.get("key")
            for item in report.get("surfaces", [])
            if isinstance(item, dict) and item.get("status") == "visited"
        }
        cloud_report = load_latest_cloud_console_live_report()
        if cloud_report.get("status") != "missing" and not cloud_keys.issubset(live_cloud_keys):
            source_reports.append(cloud_report)
    else:
        source_reports.append(report)
    catalog = tab_logic.build_all_tab_logic_catalog()
    live_by_key: dict[str, dict[str, Any]] = {}
    for source in source_reports:
        for item in source.get("surfaces", []):
            if isinstance(item, dict) and item.get("key"):
                live_by_key[item["key"]] = item
    surfaces_logic: list[dict[str, Any]] = []

    for tab in catalog["tabs"]:
        actions_by_surface: dict[str, list[dict[str, Any]]] = {}
        for action in tab["actions"]:
            actions_by_surface.setdefault(action["surface_key"], []).append(action)
        for surface in tab["surfaces"]:
            key = surface["key"]
            live_item = live_by_key.get(key, {})
            actions = actions_by_surface.get(key, [])
            risk_controls = live_item.get("risk_controls", []) if isinstance(live_item, dict) else []
            surfaces_logic.append(
                {
                    "surface_key": key,
                    "tab_key": tab["tab_key"],
                    "label": surface["label"],
                    "host": surface["host"],
                    "catalog_risk": surface["risk"],
                    "live_status": live_item.get("status", "not_observed"),
                    "live_verified_readonly": live_item.get("status") == "visited",
                    "title": live_item.get("title", ""),
                    "observed_headings": live_item.get("headings", [])[:12],
                    "observed_control_count": len(live_item.get("controls", [])) if isinstance(live_item, dict) else 0,
                    "observed_input_count": len(live_item.get("inputs", [])) if isinstance(live_item, dict) else 0,
                    "observed_risk_controls": [
                        {
                            "text": item.get("text", ""),
                            "matched_keywords": item.get("matched_keywords", []),
                        }
                        for item in risk_controls
                    ],
                    "user_guidance": tab["user_guidance"],
                    "read_actions": [action["key"] for action in actions if not action["requires_approval"]],
                    "approval_actions": [action["key"] for action in actions if action["requires_approval"]],
                    "execution_policy": {
                        "read": "direct_cdp_or_local_agent_readonly",
                        "state_change": "approval_required_no_local_agent_task_before_approval",
                        "final_submit": "blocked_without_approval_phrase",
                        "secret_export": "blocked",
                    },
                }
            )

    return {
        "site_id": "google",
        "source_report_status": (
            "completed"
            if source_reports and all(item.get("status") == "completed" for item in source_reports)
            else report.get("status", "unknown")
        ),
        "source_generated_at": report.get("generated_at", ""),
        "source_reports": [
            {
                "status": item.get("status", "unknown"),
                "generated_at": item.get("generated_at", ""),
                "tab_key": item.get("tab_key", "all_surfaces"),
                "planned": item.get("counts", {}).get("planned", 0),
                "visited": item.get("counts", {}).get("visited", 0),
                "failed": item.get("counts", {}).get("failed", 0),
            }
            for item in source_reports
        ],
        "live_mode": report.get("mode", ""),
        "surface_count": len(surfaces_logic),
        "live_verified_count": sum(1 for item in surfaces_logic if item["live_verified_readonly"]),
        "approval_action_count": sum(len(item["approval_actions"]) for item in surfaces_logic),
        "risk_surface_count": sum(1 for item in surfaces_logic if item["observed_risk_controls"]),
        "surfaces": surfaces_logic,
    }


def print_google_surface_live_summary(report: dict[str, Any], path: Path) -> None:
    print("=" * 60)
    print("Google surface live read-only exploration")
    print("=" * 60)
    print(f"status: {report.get('status')}")
    print(f"mode: {report.get('mode')}")
    print(f"planned: {report['counts']['planned']}")
    print(f"visited: {report['counts']['visited']}")
    print(f"failed: {report['counts']['failed']}")
    print(f"risk_controls_detected: {report['counts']['risk_controls_detected']}")
    for item in report.get("surfaces", []):
        print(
            f"- {item['tab_key']}/{item['key']}: {item['status']} "
            f"controls={len(item.get('controls', []))} "
            f"risk={len(item.get('risk_controls', []))}"
        )
    if report.get("warnings"):
        print("warnings:")
        for warning in report["warnings"]:
            print(f"- {warning}")
    print(f"saved: {path}")
    print(f"latest: {LATEST_REPORT}")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--keys", default="")
    parser.add_argument("--tabs", default="")
    parser.add_argument("--exclude-tabs", default="")
    parser.add_argument("--wait-seconds", type=float, default=3.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--snapshot-limit", type=int, default=80)
    args = parser.parse_args()
    report, path = explore_google_surfaces_direct_cdp(
        keys=[item for item in args.keys.split(",") if item] or None,
        tabs=[item for item in args.tabs.split(",") if item] or None,
        exclude_tabs=[item for item in args.exclude_tabs.split(",") if item] or None,
        wait_seconds=args.wait_seconds,
        limit=args.limit or None,
        snapshot_limit=args.snapshot_limit,
    )
    print_google_surface_live_summary(report, path)
    return 0 if report.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
