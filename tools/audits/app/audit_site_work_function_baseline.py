"""Audit the locked site work function baseline."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE = ROOT / "docs" / "baseline" / "SITE_WORK_FUNCTION_BASELINE.md"

REQUIRED_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: SITE-WORK-FUNCTION-BASELINE-01",
    "`google`",
    "`naver`",
    "`smartstore`",
    "`hiworks`",
    "`gabia`",
    "`youtube`",
    "web_open_url_readonly",
    "State-changing actions must be approval-gated",
    "raw cookies, sessions",
    "passwords, OTPs, API keys, bearer tokens, or Authorization headers",
    "Required actions: 96",
    "Required read actions: 50",
    "Required approval actions: 46",
    "Required live-input supported approval actions: 46",
    "Required action catalog minimum services: 17",
    "## Site Work Matrix",
    "## Work Acceptance Rule",
    "### Google Work Matrix",
    "### Naver Work Matrix",
    "### SmartStore Work Matrix",
    "### Hiworks Work Matrix",
    "### Gabia Work Matrix",
    "### YouTube Work Matrix",
    "Claims about actual business completion must be downgraded to WARN",
)

SERVICE_COMMANDS = ("google", "gmail", "naver", "smartstore", "hiworks", "gabia", "youtube")
NAVER_CATEGORIES = {
    "session",
    "mail",
    "content",
    "seo",
    "developers",
    "shopping",
    "excel",
    "cafe",
    "calendar",
    "mybox",
    "pay",
    "talk",
    "place",
    "smartstore",
}


def _missing(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def _status(module_name: str) -> dict:
    module = importlib.import_module(module_name)
    status = getattr(module, "__status__", {})
    return status if isinstance(status, dict) else {}


def _task_status(module_name: str) -> dict:
    status = _status(module_name)
    tasks = status.get("tasks", {})
    return tasks if isinstance(tasks, dict) else {}


def _count_naver_catalog_categories() -> set[str]:
    from scripts.naver.service_catalog import build_catalog

    catalog = build_catalog()
    categories: set[str] = set()
    for item in catalog.get("services", []):
        key = item.get("key") or item.get("service") or item.get("name")
        if key:
            categories.add(str(key))
    for item in catalog.get("categories", []):
        key = item.get("key") or item.get("name")
        if key:
            categories.add(str(key))
    if not categories and isinstance(catalog.get("actions"), dict):
        categories.update(str(key) for key in catalog["actions"])
    if isinstance(catalog.get("features"), dict):
        categories.update(str(key) for key in catalog["features"])
    return categories


def _audit_routing(failures, is_service_cmd, validate_registry):
    not_routed = [cmd for cmd in SERVICE_COMMANDS if not is_service_cmd(cmd)]
    if not_routed:
        failures.append(
            "service command(s) not routed through scripts.site_engine.command_router: " + ", ".join(not_routed)
        )

    registry_errors = validate_registry()
    if registry_errors:
        failures.extend(registry_errors)


def _audit_google_counts(failures, workflows, live_inputs):
    google_catalog = workflows.build_action_catalog()
    google_actions = google_catalog.get("actions", [])
    read_count = sum(1 for action in google_actions if action.get("operation") == "read")
    approval_count = sum(1 for action in google_actions if action.get("operation") != "read")
    if len(google_actions) != 96:
        failures.append(f"google action count mismatch: {len(google_actions)}")
    if read_count != 50:
        failures.append(f"google read action count mismatch: {read_count}")
    if approval_count != 46:
        failures.append(f"google approval action count mismatch: {approval_count}")

    coverage = live_inputs.build_live_input_coverage()
    supported_count = coverage.get("counts", {}).get("live_input_supported")
    if supported_count != 46:
        failures.append(f"google live input support mismatch: {supported_count}")


def _audit_google_tasks(failures, dry_run_cloud_readonly_browser_task):
    cloud_dry = dry_run_cloud_readonly_browser_task("compute", "open")
    task = cloud_dry.get("local_agent_task", {})
    if task.get("action") != "web_open_url_readonly" or task.get("execution_location") != "local_agent":
        failures.append("google cloud read-only local browser task contract failed")

    google_tasks = _task_status("scripts.google.router")
    if google_tasks.get("drive list") != "partial":
        failures.append("google drive list must remain partial until live evidence is added")
    if google_tasks.get("work execute") != "approval_gated":
        failures.append("google work execute must be approval_gated")


def _audit_naver(failures):
    naver_tasks = _task_status("scripts.naver.router")
    # defect_index #38: CLI 'mail inbox' 는 미구현을 정직하게 표기(not_implemented_cli) — done 으로 요구하지 않고 그 표기가 유지되는지 검사
    if naver_tasks.get("mail inbox") != "not_implemented_cli":
        failures.append("naver mail inbox must stay honestly marked not_implemented_cli")
    for key in ("blog write", "cafe write", "calendar list/add", "mybox list/search/upload"):
        if naver_tasks.get(key) != "done":
            failures.append(f"naver task not marked done: {key}")
    naver_categories = _count_naver_catalog_categories()
    missing_naver_categories = sorted(NAVER_CATEGORIES - naver_categories)
    if missing_naver_categories:
        failures.append("naver catalog missing categories: " + ", ".join(missing_naver_categories))


def _audit_smartstore(failures, build_smartstore_action_catalog):
    smartstore_catalog = build_smartstore_action_catalog()
    smart_counts = {
        item.get("name"): item.get("summary", {})
        for item in smartstore_catalog.get("sections", [])
        if isinstance(item, dict)
    }
    expected_smart = {"read": 8, "prepare": 3, "approval": 6}
    for risk, expected in expected_smart.items():
        item = smart_counts.get(risk)
        total = item.get("total") if isinstance(item, dict) else None
        if total != expected:
            failures.append(f"smartstore {risk} total mismatch: {total}")
    smart_tasks = _task_status("scripts.naver.smartstore.api.router")
    if smart_tasks.get("seo") != "todo" or smart_tasks.get("product register") != "complete_baseline":
        failures.append("smartstore status boundaries changed unexpectedly")


def _audit_hiworks_gabia(failures, build_hiworks_action_catalog):
    hiworks_catalog = build_hiworks_action_catalog()
    hiworks_services = hiworks_catalog.get("services", [])
    if len(hiworks_services) < 17:
        failures.append(f"hiworks service count below baseline: {len(hiworks_services)}")

    gabia_tasks = _task_status("scripts.gabia.router")
    for key in ("status", "dns", "login", "domain", "hosting", "payment"):
        if key not in gabia_tasks:
            failures.append(f"gabia status missing task: {key}")
    if gabia_tasks.get("payment") != "user_direct_required":
        failures.append("gabia payment must remain user_direct_required")


def _audit_youtube(failures, uploader):
    youtube_tasks = _task_status("scripts.youtube.router")
    for key in (
        "record prepare",
        "record execute",
        "upload prepare",
        "upload execute",
        "upload verify",
        "research search",
        "research video-info",
        "research comments",
        "research transcript-plan",
        "research analyze",
        "research context-report",
        "research scorecard",
        "research comment-plan",
        "research channel-ops-plan",
    ):
        if key not in youtube_tasks:
            failures.append(f"youtube status missing task: {key}")
    plan, _path = uploader.prepare_upload_plan(
        ROOT / "data" / "test_runtime" / "missing_site_work_baseline.mp4", {"title": "baseline"}
    )
    if plan.get("ready_for_approval") is not False or "local_video_file" not in plan.get("missing_requirements", []):
        failures.append("youtube missing video file must block approval readiness")


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not BASELINE.exists():
        return False, ["docs/baseline/SITE_WORK_FUNCTION_BASELINE.md missing"]

    text = BASELINE.read_text(encoding="utf-8", errors="replace")
    missing = _missing(text, REQUIRED_PHRASES)
    if missing:
        failures.append("site work baseline missing phrase(s): " + ", ".join(missing))

    from scripts.google.cloud.local_browser import dry_run_cloud_readonly_browser_task
    from scripts.google.common import live_inputs, workflows
    from scripts.hiworks.actions import build_action_catalog as build_hiworks_action_catalog
    from scripts.naver.smartstore.actions import build_action_catalog as build_smartstore_action_catalog
    from scripts.site_engine.command_router import is_service_cmd
    from scripts.site_engine.subdomain_registry import validate_registry
    from scripts.youtube import uploader

    _audit_routing(failures, is_service_cmd, validate_registry)

    _audit_google_counts(failures, workflows, live_inputs)

    _audit_google_tasks(failures, dry_run_cloud_readonly_browser_task)

    _audit_naver(failures)

    _audit_smartstore(failures, build_smartstore_action_catalog)

    _audit_hiworks_gabia(failures, build_hiworks_action_catalog)

    _audit_youtube(failures, uploader)

    return not failures, failures or [
        "SITE_WORK_FUNCTION_BASELINE exists and is locked",
        "site service commands are routed through scripts.site_engine.command_router",
        "Google/Naver/SmartStore/Hiworks/Gabia/YouTube work contracts match baseline",
        "state-changing work remains approval-gated or user-direct",
    ]


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "SITE_WORK_FUNCTION_BASELINE")


if __name__ == "__main__":
    raise SystemExit(main())
