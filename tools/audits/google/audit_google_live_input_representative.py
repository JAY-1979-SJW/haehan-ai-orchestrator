"""Build a representative Google live-input dry-preflight report.

This audit does not open a browser and does not submit external Google state.
It verifies the locked live-input coverage, prepares representative approval
plans, and records the exact no-final-submit live command for user-approved
local browser verification.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timezone
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT_DIR = ROOT / "docs" / "reports"
LATEST_JSON = ROOT / "data" / "google_live_input_representative_preflight_latest.json"

REPRESENTATIVE_ACTIONS: tuple[tuple[str, dict[str, str]], ...] = (
    (
        "gmail_send_email",
        {
            "to": "reviewer@example.com",
            "subject": "DRAFT_ONLY_REPRESENTATIVE_CHECK",
            "body": "Representative no-final-submit Gmail draft check.",
        },
    ),
    (
        "search_console_submit_sitemap",
        {
            "property": "https://example.com/",
            "sitemap_url": "https://example.com/sitemap.xml",
        },
    ),
    (
        "cloud_create_api_credential",
        {
            "project": "example-project",
            "credential_type": "api_key",
            "name": "draft-only-key",
            "label": "draft-only-key",
        },
    ),
    (
        "cloud_iam_change_role",
        {
            "project": "example-project",
            "principal": "user@example.com",
            "role": "roles/viewer",
            "change": "grant",
        },
    ),
)


def build_report() -> dict:
    from scripts.google.common import live_inputs, workflows

    coverage = live_inputs.build_live_input_coverage()
    supported = {item["action_key"] for item in coverage["supported"]}
    items: list[dict] = []
    for action_key, values in REPRESENTATIVE_ACTIONS:
        plan, plan_path = workflows.prepare_action(action_key, values)
        action = plan["action"]
        items.append(
            {
                "action_key": action_key,
                "surface_key": action["surface_key"],
                "mode": live_inputs.LIVE_INPUT_ADAPTERS.get(action_key, ""),
                "ready_for_approval": plan["ready_for_approval"],
                "missing_inputs": plan["missing_inputs"],
                "state_change": plan["state_change"],
                "no_final_submit_command": (
                    f"python scripts\\entry\\cdp_cli.py google work live-fill {plan_path} --no-final-submit"
                ),
            }
        )

    checks = {
        "approval_actions_46": coverage["counts"]["approval_actions"] == 46,
        "live_input_supported_46": coverage["counts"]["live_input_supported"] == 46,
        "prepare_or_open_only_zero": coverage["counts"]["prepare_or_open_only"] == 0,
        "representatives_supported": all(action_key in supported for action_key, _ in REPRESENTATIVE_ACTIONS),
        "representatives_ready": all(item["ready_for_approval"] and not item["missing_inputs"] for item in items),
        "state_change_false": all(item["state_change"] is False for item in items),
    }
    status = "passed" if all(checks.values()) else "failed"
    return {
        "site_id": "google",
        "report_type": "representative_live_input_dry_preflight",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": status,
        "policy": {
            "live_browser_opened": False,
            "external_state_change": False,
            "final_submit_policy": "blocked; live command requires --no-final-submit",
            "representative_scope": "Gmail, Search Console, Cloud credential, Cloud IAM",
        },
        "coverage_counts": coverage["counts"],
        "checks": checks,
        "representatives": items,
    }


def save_report(report: dict | None = None) -> tuple[Path, Path]:
    report = report or build_report()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_JSON.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = REPORT_DIR / f"google_live_input_representative_preflight_{timestamp}.json"
    md_path = REPORT_DIR / f"google_live_input_representative_preflight_{timestamp}.md"
    text = json.dumps(report, ensure_ascii=False, indent=2)
    json_path.write_text(text, encoding="utf-8")
    LATEST_JSON.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def render_markdown(report: dict) -> str:
    lines = [
        "# Google Live Input Representative Preflight",
        "",
        f"- Status: {report['status']}",
        f"- Generated at: {report['generated_at']}",
        f"- Live browser opened: {report['policy']['live_browser_opened']}",
        f"- External state change: {report['policy']['external_state_change']}",
        f"- Approval actions: {report['coverage_counts']['approval_actions']}",
        f"- Live input supported: {report['coverage_counts']['live_input_supported']}",
        f"- Prepare/open-only: {report['coverage_counts']['prepare_or_open_only']}",
        "",
        "## Checks",
        "",
    ]
    for key, value in report["checks"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Representatives", ""])
    for item in report["representatives"]:
        lines.extend(
            [
                f"### {item['action_key']}",
                "",
                f"- Surface: {item['surface_key']}",
                f"- Adapter mode: {item['mode']}",
                f"- Ready for approval: {item['ready_for_approval']}",
                f"- Missing inputs: {', '.join(item['missing_inputs']) if item['missing_inputs'] else '-'}",
                f"- State change: {item['state_change']}",
                "- Live command:",
                "",
                "```text",
                item["no_final_submit_command"],
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Next Step",
            "",
            "Run the listed live commands only when a user-present local browser session is ready.",
            "Every command must include `--no-final-submit`; final Send/Submit/Create/Grant controls remain blocked.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    report = build_report()
    json_path, md_path = save_report(report)
    print("Google live input representative preflight")
    print(f"status: {report['status']}")
    print(f"json: {json_path}")
    print(f"markdown: {md_path}")
    print(f"live_input_supported: {report['coverage_counts']['live_input_supported']}")
    print(f"prepare_or_open_only: {report['coverage_counts']['prepare_or_open_only']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
