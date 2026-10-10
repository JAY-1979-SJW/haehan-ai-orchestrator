"""Read-only Google Cloud Console explorer using direct CDP.

This avoids Playwright process startup and talks to the already-running Chrome
debugging port. It navigates only, does not click, type, submit, export
cookies, or read storage.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.browser.cdp.cdp_console import connect
from scripts.google.common import surfaces, tab_logic
from scripts.google.common.report_io import save_json_with_latest
from scripts.google.common.surface_explorer import RISK_CONTROL_KEYWORDS

ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = ROOT / "data" / "google_cloud_console_live"
LATEST_REPORT = ROOT / "data" / "google_cloud_console_live_latest.json"

CLOUD_SURFACE_USER_GUIDANCE: dict[str, dict[str, list[str]]] = {
    "cloud_console": {
        "user_can_request": [
            "Check project console overview.",
            "List visible quick access options.",
            "Identify visible create/deploy shortcuts.",
        ],
        "approval_required_for": ["Create API key", "create VM", "deploy application", "create bucket", "create agent"],
    },
    "maps_platform": {
        "user_can_request": ["Open Maps Platform read-only.", "Check visible API/key/quota navigation."],
        "approval_required_for": ["Change API key", "change quota", "enable billing-impacting service"],
    },
    "cloud_apis_credentials": {
        "user_can_request": ["Open APIs and Credentials read-only.", "Check visible credential/API navigation."],
        "approval_required_for": ["Create API key", "create OAuth client", "enable/disable API"],
    },
    "cloud_iam": {
        "user_can_request": ["Open IAM read-only.", "Check visible IAM/admin navigation."],
        "approval_required_for": ["Add principal", "remove principal", "change role", "create service account"],
    },
    "cloud_billing": {
        "user_can_request": ["Open Billing read-only.", "Check visible billing navigation."],
        "approval_required_for": ["Link billing account", "change budget", "payment or billing setting change"],
    },
    "cloud_run": {
        "user_can_request": ["Open Cloud Run read-only.", "Check visible service/deploy navigation."],
        "approval_required_for": ["Deploy service", "change traffic", "delete service"],
    },
    "compute_engine": {
        "user_can_request": [
            "Open Compute Engine read-only.",
            "Check VM, storage, instance group, and VM Manager navigation.",
        ],
        "approval_required_for": ["Create VM", "start/stop/delete VM", "change disk/network/firewall settings"],
    },
    "cloud_storage": {
        "user_can_request": ["Open Cloud Storage read-only.", "Check bucket/object navigation."],
        "approval_required_for": ["Create bucket", "upload/delete object", "change permissions"],
    },
    "bigquery": {
        "user_can_request": ["Open BigQuery read-only.", "Check dataset/query navigation."],
        "approval_required_for": ["Run query", "export data", "create/delete dataset or table"],
    },
    "gke": {
        "user_can_request": ["Open Kubernetes Engine read-only.", "Check cluster navigation."],
        "approval_required_for": ["Create/update/delete cluster", "apply workload change"],
    },
    "cloud_sql": {
        "user_can_request": ["Open Cloud SQL read-only.", "Check instance navigation."],
        "approval_required_for": ["Create/update/delete instance", "change users/network/backups"],
    },
    "pubsub": {
        "user_can_request": ["Open Pub/Sub read-only.", "Check topic/subscription navigation."],
        "approval_required_for": ["Create topic/subscription", "publish message", "delete resource"],
    },
    "secret_manager": {
        "user_can_request": [
            "Open Secret Manager read-only.",
            "Check secret navigation without reading secret values.",
        ],
        "approval_required_for": ["Create/update/delete secret", "access secret value", "change IAM"],
    },
    "cloud_logging": {
        "user_can_request": [
            "Open Logging read-only.",
            "Check logs explorer, detection, and configuration navigation.",
        ],
        "approval_required_for": ["Create sink", "change retention/configuration", "export logs"],
    },
    "cloud_monitoring": {
        "user_can_request": [
            "Open Monitoring read-only.",
            "Check monitoring, detection, and configuration navigation.",
        ],
        "approval_required_for": ["Create alert", "change dashboard/policy/notification channel"],
    },
}

EMAIL_RE = re.compile(r"(?i)[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")
LONG_NUMBER_RE = re.compile(r"\b\d{6,}\b")
PROJECT_ID_RE = re.compile(r"(?i)\b[a-z][a-z0-9-]{5,30}\b")


def _utc() -> str:
    return datetime.now(UTC).isoformat()


def _redact_text(value: Any) -> str:
    text = str(value or "")
    text = EMAIL_RE.sub("[email-redacted]", text)
    text = LONG_NUMBER_RE.sub("[number-redacted]", text)
    return text.strip()


def _redact_url(value: str) -> str:
    text = _redact_text(value)
    if "?" in text:
        text = text.split("?", 1)[0] + "?[query-redacted]"
    if "#" in text:
        text = text.split("#", 1)[0] + "#[fragment-redacted]"
    return text


def _cloud_surfaces(keys: list[str] | None = None) -> list[dict[str, Any]]:
    cloud = tab_logic.get_tab_summary("cloud")
    wanted = set(keys or [item["key"] for item in cloud["surfaces"]])
    by_key = {item["key"]: item for item in surfaces.build_surface_catalog()["surfaces"]}
    return [by_key[key] for key in wanted if key in by_key]


def _extract_visible_console_snapshot(session: Any, *, limit: int) -> dict[str, Any]:
    data, err = session.js_json(
        f"""(function() {{
            function visible(el) {{
                var r = el.getBoundingClientRect();
                var style = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            }}
            function textOf(el, max) {{
                return ((el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || el.title || '') + '')
                    .replace(/\\s+/g, ' ').trim().slice(0, max);
            }}
            function item(el) {{
                return {{
                    tag: el.tagName.toLowerCase(),
                    text: textOf(el, 80),
                    aria: (el.getAttribute('aria-label') || '').slice(0, 80),
                    title: (el.title || '').slice(0, 80),
                    role: (el.getAttribute('role') || '').slice(0, 40),
                    href: (el.href || '').slice(0, 160)
                }};
            }}
            var headings = Array.from(document.querySelectorAll('h1,h2,h3,[role=heading]'))
                .filter(visible).map(function(el) {{ return textOf(el, 100); }}).filter(Boolean).slice(0, {limit});
            var controls = Array.from(document.querySelectorAll('button,a,input[type=button],input[type=submit],[role=button],[role=menuitem]'))
                .filter(visible).map(item).filter(function(x) {{ return x.text || x.aria || x.title; }}).slice(0, {limit});
            var nav = Array.from(document.querySelectorAll('nav a, [role=navigation] a, a[href]'))
                .filter(visible).map(item).filter(function(x) {{ return x.text || x.aria || x.title; }}).slice(0, {limit});
            var inputs = Array.from(document.querySelectorAll('input,textarea,select'))
                .filter(visible).map(function(el) {{
                    return {{
                        tag: el.tagName.toLowerCase(),
                        type: (el.type || '').slice(0, 40),
                        name: (el.name || '').slice(0, 80),
                        placeholder: (el.placeholder || '').slice(0, 80),
                        aria: (el.getAttribute('aria-label') || '').slice(0, 80)
                    }};
                }}).slice(0, {limit});
            return {{
                url: location.href,
                title: document.title,
                body_length: (document.body && document.body.innerText || '').length,
                headings: headings,
                controls: controls,
                nav: nav,
                inputs: inputs
            }};
        }})()"""
    )
    if err or not isinstance(data, dict):
        return {"error": _redact_text(data), "headings": [], "controls": [], "nav": [], "inputs": []}
    return _sanitize_snapshot(data)


def _sanitize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(snapshot)
    sanitized["url"] = _redact_url(str(sanitized.get("url", "")))
    sanitized["title"] = _redact_text(sanitized.get("title", ""))
    sanitized["headings"] = [_redact_text(item) for item in sanitized.get("headings", [])]
    for key in ("controls", "nav", "inputs"):
        rows = []
        for row in sanitized.get(key, []):
            if isinstance(row, dict):
                rows.append({k: (_redact_url(v) if k == "href" else _redact_text(v)) for k, v in row.items()})
        sanitized[key] = rows
    return sanitized


def _risk_controls(controls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for control in controls:
        haystack = " ".join(str(control.get(key, "")) for key in ("text", "aria", "title"))
        matches = [keyword for keyword in RISK_CONTROL_KEYWORDS if keyword.lower() in haystack.lower()]
        if matches:
            found.append(
                {
                    "tag": control.get("tag", ""),
                    "text": _redact_text(control.get("text", "")),
                    "matched_keywords": matches,
                }
            )
    return found


def explore_cloud_console_surfaces(
    *,
    keys: list[str] | None = None,
    wait_seconds: float = 4.0,
    limit: int = 80,
) -> tuple[dict[str, Any], Path]:
    selected = _cloud_surfaces(keys)
    report: dict[str, Any] = {
        "site_id": "google",
        "tab_key": "cloud",
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
                    snapshot = _extract_visible_console_snapshot(session, limit=limit)
                    result.update(snapshot)
                    result["final_url"] = _redact_url(str(snapshot.get("url", "")))
                    result["title"] = _redact_text(snapshot.get("title", ""))
                    result["risk_controls"] = _risk_controls(snapshot.get("controls", []))
                    result["status"] = "visited"
                    report["counts"]["visited"] += 1
                    if result["risk_controls"]:
                        report["counts"]["risk_controls_detected"] += 1
                except Exception as exc:  # noqa: BLE001 - 구글 클라우드 콘솔 라이브 탐색(읽기 전용) -- 개별 화면 방문 실패는 report에 failed로 기록하고 계속, 예외 텍스트는 _redact_text로 민감정보를 제거한 뒤 저장
                    result["status"] = "failed"
                    result["warnings"].append(_redact_text(exc))
                    report["counts"]["failed"] += 1
                report["surfaces"].append(result)
    except Exception as exc:  # noqa: BLE001 - 구글 클라우드 콘솔 라이브 탐색(읽기 전용) -- 개별 화면 방문 실패는 report에 failed로 기록하고 계속, 예외 텍스트는 _redact_text로 민감정보를 제거한 뒤 저장
        report["status"] = "failed"
        report["warnings"] = [_redact_text(exc)]
        report["counts"]["failed"] = len(selected)
        return save_cloud_console_live_report(report)

    report["status"] = "completed"
    return save_cloud_console_live_report(report)


def save_cloud_console_live_report(report: dict[str, Any], path: Path | None = None) -> tuple[dict[str, Any], Path]:
    target = save_json_with_latest(report, REPORT_DIR, LATEST_REPORT, "google_cloud_console_live", path, ensure_ascii=True)
    return report, target


def load_latest_cloud_console_live_report(path: Path | None = None) -> dict[str, Any]:
    source = path or LATEST_REPORT
    if not source.exists():
        return {
            "site_id": "google",
            "tab_key": "cloud",
            "status": "missing",
            "counts": {"planned": 0, "visited": 0, "failed": 0, "risk_controls_detected": 0},
            "surfaces": [],
        }
    return json.loads(source.read_text(encoding="utf-8"))


def build_cloud_console_live_logic(report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Convert live read-only evidence into app-attachable Cloud tab logic."""
    report = report or load_latest_cloud_console_live_report()
    cloud_catalog = tab_logic.build_tab_logic_catalog("cloud")
    actions_by_surface: dict[str, list[dict[str, Any]]] = {}
    for action in cloud_catalog["actions"]:
        actions_by_surface.setdefault(action["surface_key"], []).append(action)

    live_by_key = {item["key"]: item for item in report.get("surfaces", [])}
    surfaces_logic: list[dict[str, Any]] = []
    for surface in cloud_catalog["surfaces"]:
        key = surface["key"]
        live_item = live_by_key.get(key, {})
        actions = actions_by_surface.get(key, [])
        read_actions = [action["key"] for action in actions if not action["requires_approval"]]
        approval_actions = [action["key"] for action in actions if action["requires_approval"]]
        risk_controls = live_item.get("risk_controls", []) if isinstance(live_item, dict) else []
        surfaces_logic.append(
            {
                "surface_key": key,
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
                "user_guidance": {
                    "user_can_request": CLOUD_SURFACE_USER_GUIDANCE.get(key, {}).get("user_can_request", []),
                    "approval_required_for": CLOUD_SURFACE_USER_GUIDANCE.get(key, {}).get("approval_required_for", []),
                    "not_allowed": [
                        "Final state change without approval phrase",
                        "Credential, cookie, token, session, or secret value export",
                    ],
                },
                "read_actions": read_actions,
                "approval_actions": approval_actions,
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
        "tab_key": "cloud",
        "source_report_status": report.get("status", "unknown"),
        "source_generated_at": report.get("generated_at", ""),
        "live_mode": report.get("mode", ""),
        "surface_count": len(surfaces_logic),
        "live_verified_count": sum(1 for item in surfaces_logic if item["live_verified_readonly"]),
        "approval_action_count": sum(len(item["approval_actions"]) for item in surfaces_logic),
        "risk_surface_count": sum(1 for item in surfaces_logic if item["observed_risk_controls"]),
        "surfaces": surfaces_logic,
    }


def print_cloud_console_live_summary(report: dict[str, Any], path: Path) -> None:
    print("=" * 60)
    print("Google Cloud Console live read-only exploration")
    print("=" * 60)
    print(f"status: {report.get('status')}")
    print(f"mode: {report.get('mode')}")
    print(f"planned: {report['counts']['planned']}")
    print(f"visited: {report['counts']['visited']}")
    print(f"failed: {report['counts']['failed']}")
    print(f"risk_controls_detected: {report['counts']['risk_controls_detected']}")
    for item in report.get("surfaces", []):
        print(
            f"- {item['key']}: {item['status']} "
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
    parser.add_argument("--wait-seconds", type=float, default=4.0)
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--logic", action="store_true")
    args = parser.parse_args()
    if args.logic:
        print(json.dumps(build_cloud_console_live_logic(), ensure_ascii=False, indent=2))
        return 0
    keys = [key for key in args.keys.split(",") if key] or None
    report, path = explore_cloud_console_surfaces(
        keys=keys,
        wait_seconds=args.wait_seconds,
        limit=args.limit,
    )
    print_cloud_console_live_summary(report, path)
    return 0 if report.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
