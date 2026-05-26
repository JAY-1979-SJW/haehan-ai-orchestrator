"""Google service router."""
from __future__ import annotations

import json

from . import (
    ai_usage_labels,
    android_app_dev_labels,
    android_app_dev_report,
    domain_taxonomy,
    live_inputs,
    live_surface_explorer,
    precision_report,
    subdomain_logic,
    surface_explorer,
    surfaces,
    tab_logic,
    workflows,
    youtube_upload,
    managed_console,
    oauth_console_fill,
)
from .base import check_session
from .cloud import live_console_explorer
from .workspace import router as workspace_router
from scripts.gate import check as gate_check
from .gates import gate_google_send_plan, gate_google_submit_plan, gate_google_oauth_required  # noqa: F401
from .profile import GOOGLE_PROFILE  # noqa: F401
from .validators import validate_google_no_plain_secret  # noqa: F401

__status__ = {
    "tasks": {
        "mail list": "done",
        "mail analyze": "done",
        "mail compose": "done",
        "mail send": "done",
        "drive list": "partial",
        "calendar today": "partial",
        "docs recent": "partial",
        "sheets recent": "partial",
        "surfaces catalog": "done",
        "surfaces live-read": "read_only",
        "subdomains catalog": "done",
        "subdomains classify": "done",
        "tabs catalog": "done",
        "tabs classify": "done",
        "android labels": "done",
        "android report": "done",
        "domains taxonomy": "done",
        "cloud live-read": "read_only",
        "surfaces explore": "read_only",
        "work catalog": "done",
        "work adapters": "done",
        "work prepare": "done",
        "work execute": "approval_gated",
        "work verify": "done",
        "work live-fill": "no_final_submit",
        "work live-coverage": "done",
        "login": "done",
        "session-check": "done",
    },
    "note": (
        "Gmail is implemented; Drive/Calendar/Docs/Sheets are partial. "
        "Google/YouTube/Console surfaces are catalog-first and approval-gated."
    ),
}


def run_google(site: str, task: str, sub: str, args: list[str]) -> None:
    """Route Google service workflows.

    site: google | gmail
    task: session-check | login | mail | drive | calendar | docs | sheets | surfaces | work
    """
    if site == "gmail":
        sub = sub or task
        task = "mail"

    match task:
        case "session-check":
            _cmd_session_check()
        case "login":
            gate_check("wait_login", risk="notify")
            _cmd_login()
        case "mail":
            gate_check(
                "gmail_send" if sub in ("send", "compose") else "goto",
                risk="approve" if sub in ("send", "compose") else "auto",
            )
            workspace_router.run_workspace("gmail", sub or "list", args)
        case "drive":
            gate_check("goto")
            workspace_router.run_workspace("drive", sub or "list", args)
        case "calendar":
            gate_check("goto")
            workspace_router.run_workspace("calendar", sub or "today", args)
        case "cloud":
            _cmd_cloud(sub or "summary", args)
        case "console":
            _cmd_console(sub or "summary", args)
        case "docs":
            gate_check("goto")
            workspace_router.run_workspace("docs", sub or "recent", args)
        case "sheets":
            gate_check("goto")
            workspace_router.run_workspace("sheets", sub or "recent", args)
        case "surfaces":
            _cmd_surfaces(sub or "catalog", args)
        case "subdomains":
            _cmd_subdomains(sub or "catalog", args)
        case "tabs":
            _cmd_tabs(sub or "catalog", args)
        case "youtube":
            _cmd_youtube(sub or "catalog", args)
        case "ai":
            _cmd_ai(sub or "catalog", args)
        case "android" | "android-app" | "app-dev":
            _cmd_android(sub or "report", args)
        case "domains" | "taxonomy" | "classification":
            _cmd_domains(sub or "report", args)
        case "report" | "precision":
            _cmd_precision(sub or "build", args)
        case "work" | "actions":
            _cmd_work(sub or "catalog", args)
        case _:
            print(f"  [error] unknown google task: {task}")


def _cmd_session_check() -> None:
    print("=" * 60)
    print("Google session check")
    print("=" * 60)
    result = check_session()
    if result["error"]:
        print(f"[fail] daemon connection failed: {result['error']}")
    elif result["logged_in"]:
        print("[ok] logged in")
    else:
        print("[needs-login] run: python scripts/cdp_client.py google login")
    print("=" * 60)


def _cmd_login() -> None:
    """User-present Google login helper."""
    from scripts.google.auth import login_google
    from scripts.web_connector import get_page

    print("=" * 60)
    print("Google login")
    print("=" * 60)
    page = get_page()
    result = login_google(page, wait_for_user_s=300)
    if result["ok"]:
        print(f"[ok] login success: {result.get('user')} ({result.get('reason')})")
    else:
        print(f"[fail] login failed: {result.get('reason')}")
        if result.get("hint"):
            print(f"  hint: {result['hint']}")
    print("=" * 60)


def _cmd_surfaces(sub: str, args: list[str] | None = None) -> None:
    args = args or []
    if sub in ("live-logic", "logic"):
        logic = live_surface_explorer.build_google_surface_live_logic()
        print(json.dumps(logic, ensure_ascii=False, indent=2, default=str))
        return
    if sub in ("live-read", "live-explore"):
        keys: list[str] = []
        tabs: list[str] = []
        exclude_tabs: list[str] = []
        wait_seconds = 3.0
        limit = None
        snapshot_limit = 80
        for arg in args:
            if arg.startswith("--key="):
                keys.append(arg.split("=", 1)[1])
            elif arg.startswith("--keys="):
                keys.extend([key for key in arg.split("=", 1)[1].split(",") if key])
            elif arg.startswith("--tabs="):
                tabs.extend([tab for tab in arg.split("=", 1)[1].split(",") if tab])
            elif arg.startswith("--exclude-tabs="):
                exclude_tabs.extend([tab for tab in arg.split("=", 1)[1].split(",") if tab])
            elif arg.startswith("--wait-seconds="):
                wait_seconds = float(arg.split("=", 1)[1])
            elif arg.startswith("--limit="):
                limit = int(arg.split("=", 1)[1])
            elif arg.startswith("--snapshot-limit="):
                snapshot_limit = int(arg.split("=", 1)[1])
        report, path = live_surface_explorer.explore_google_surfaces_direct_cdp(
            keys=keys or None,
            tabs=tabs or None,
            exclude_tabs=exclude_tabs or None,
            wait_seconds=wait_seconds,
            limit=limit,
            snapshot_limit=snapshot_limit,
        )
        live_surface_explorer.print_google_surface_live_summary(report, path)
        return
    if sub in ("explore", "scan", "read"):
        keys: list[str] = []
        limit = None
        timeout_ms = 30000
        for arg in args:
            if arg.startswith("--key="):
                keys.append(arg.split("=", 1)[1])
            elif arg.startswith("--keys="):
                keys.extend([key for key in arg.split("=", 1)[1].split(",") if key])
            elif arg.startswith("--limit="):
                limit = int(arg.split("=", 1)[1])
            elif arg.startswith("--timeout-ms="):
                timeout_ms = int(arg.split("=", 1)[1])
        report, path = surface_explorer.explore_google_surfaces(
            keys=keys or None,
            limit=limit,
            timeout_ms=timeout_ms,
        )
        surface_explorer.print_surface_exploration_summary(report, path)
        return
    if sub not in ("catalog", "list", "index"):
        print(f"  [error] unknown surfaces task: {sub}")
        return
    catalog = surfaces.build_surface_catalog()
    path = surfaces.save_surface_catalog(catalog)
    surfaces.print_surface_summary(catalog, path)


def _cmd_subdomains(sub: str, args: list[str]) -> None:
    if sub in ("catalog", "list", "index"):
        catalog = subdomain_logic.build_google_subdomain_logic_catalog()
        print("=" * 60)
        print("Google subdomain logic catalog")
        print("=" * 60)
        print(f"subdomains: {catalog['subdomain_count']}")
        print(f"login_policy: {catalog['login_policy']}")
        for item in catalog["subdomains"]:
            print(
                f"- {item['host']}: "
                f"surfaces={len(item['surface_keys'])} "
                f"read={len(item['read_actions'])} "
                f"approval={len(item['approval_actions'])} "
                f"{item['risk_boundary']}"
            )
        return
    if sub in ("classify", "check", "task"):
        if not args:
            print("  [error] usage: python scripts/cdp_client.py google subdomains classify <host-or-service> [operation]")
            return
        operation = args[1] if len(args) > 1 else "read"
        result = subdomain_logic.classify_google_subdomain_operation(args[0], operation)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return
    print(f"  [error] unknown subdomains task: {sub}")


def _cmd_tabs(sub: str, args: list[str]) -> None:
    if sub in ("catalog", "list", "index"):
        catalog = tab_logic.build_all_tab_logic_catalog()
        print("=" * 60)
        print("Google tab logic catalog")
        print("=" * 60)
        print(f"tabs: {catalog['tab_count']}")
        for item in catalog["tabs"]:
            print(
                f"- {item['tab_key']}: "
                f"surfaces={item['surface_count']} "
                f"read={item['read_action_count']} "
                f"approval={item['approval_action_count']} "
                f"hosts={len(item['hosts'])}"
            )
        return
    if sub in ("classify", "check", "task"):
        if len(args) < 2:
            print("  [error] usage: python scripts/cdp_client.py google tabs classify <tab> <host-or-service> [operation]")
            return
        operation = args[2] if len(args) > 2 else "read"
        result = tab_logic.classify_tab_operation(args[0], args[1], operation)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return
    print(f"  [error] unknown tabs task: {sub}")


def _cmd_cloud(sub: str, args: list[str]) -> None:
    if sub in ("live-read", "live-explore", "console-read"):
        keys: list[str] = []
        wait_seconds = 4.0
        limit = 80
        for arg in args:
            if arg.startswith("--keys="):
                keys.extend([key for key in arg.split("=", 1)[1].split(",") if key])
            elif arg.startswith("--wait-seconds="):
                wait_seconds = float(arg.split("=", 1)[1])
            elif arg.startswith("--limit="):
                limit = int(arg.split("=", 1)[1])
        report, path = live_console_explorer.explore_cloud_console_surfaces(
            keys=keys or None,
            wait_seconds=wait_seconds,
            limit=limit,
        )
        live_console_explorer.print_cloud_console_live_summary(report, path)
        return
    if sub in ("live-logic", "console-logic"):
        logic = live_console_explorer.build_cloud_console_live_logic()
        print(json.dumps(logic, ensure_ascii=False, indent=2, default=str))
        return
    if sub in ("summary", "catalog"):
        catalog = tab_logic.build_tab_logic_catalog("cloud")
        print(json.dumps(catalog, ensure_ascii=False, indent=2, default=str))
        return
    print(f"  [error] unknown cloud task: {sub}")


def _cmd_console(sub: str, args: list[str]) -> None:
    dry_run = "--dry-run" in args
    secret_action_mode = "final_approval_only"
    secret_issue_approved = "--secret-issue-approved" in args
    for arg in args:
        if arg.startswith("--secret-action-mode="):
            secret_action_mode = arg.split("=", 1)[1]
    if sub in ("youtube-oauth-plan", "youtube-oauth-preapproval", "plan"):
        print(json.dumps(
            managed_console.build_youtube_oauth_console_open_plan(
                secret_action_mode=secret_action_mode,
                secret_issue_approved=secret_issue_approved,
            ),
            ensure_ascii=False,
            indent=2,
            default=str,
        ))
        return
    if sub in ("youtube-oauth-open", "open-youtube-oauth", "open"):
        result = managed_console.open_youtube_oauth_console_managed(
            dry_run=dry_run,
            secret_action_mode=secret_action_mode,
            secret_issue_approved=secret_issue_approved,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return
    if sub in ("youtube-oauth-fill", "fill-youtube-oauth", "youtube-oauth-prefill"):
        approved_api_enable = "--approved-api-enable" in args
        result, path = oauth_console_fill.prefill_youtube_oauth_console(
            dry_run=dry_run,
            approved_api_enable=approved_api_enable,
            secret_action_mode=secret_action_mode,
            secret_issue_approved=secret_issue_approved,
        )
        oauth_console_fill.print_prefill_summary(result, path)
        return
    if sub in ("summary", "catalog"):
        print(json.dumps({"commands": ["youtube-oauth-plan", "youtube-oauth-open --dry-run", "youtube-oauth-open", "youtube-oauth-fill --dry-run", "youtube-oauth-fill"]}, ensure_ascii=False, indent=2))
        return
    print(f"  [error] unknown console task: {sub}")


def _cmd_ai(sub: str, args: list[str]) -> None:
    if sub in ("labels", "usage", "pricing", "catalog"):
        print(json.dumps(ai_usage_labels.build_google_ai_usage_labels(), ensure_ascii=False, indent=2, default=str))
        return
    print(f"  [error] unknown ai task: {sub}")


def _cmd_android(sub: str, args: list[str]) -> None:
    if sub in ("labels", "usage", "pricing", "catalog"):
        print(json.dumps(android_app_dev_labels.build_android_app_dev_labels(), ensure_ascii=False, indent=2, default=str))
        return
    if sub in ("report", "build", "verify"):
        report, json_path, md_path = android_app_dev_report.save_android_app_dev_report()
        android_app_dev_report.print_android_app_dev_summary(report, json_path, md_path)
        return
    print(f"  [error] unknown android task: {sub}")


def _cmd_domains(sub: str, args: list[str]) -> None:
    if sub in ("page-tabs", "tabs", "subtabs"):
        surface_key = args[0] if args else None
        catalog = domain_taxonomy.build_google_page_tab_catalog(surface_key)
        domain_taxonomy.print_google_page_tab_summary(catalog)
        return
    if sub in ("catalog", "labels", "taxonomy", "classify", "report", "build", "verify"):
        report, json_path, md_path = domain_taxonomy.save_google_domain_taxonomy()
        domain_taxonomy.print_google_domain_taxonomy_summary(report, json_path, md_path)
        return
    print(f"  [error] unknown domains task: {sub}")


def _cmd_youtube(sub: str, args: list[str]) -> None:
    from scripts.google import youtube

    if sub in ("catalog", "summary"):
        print(json.dumps(youtube.catalog(), ensure_ascii=False, indent=2, default=str))
        return
    if sub in ("tabs", "page-tabs", "subtabs"):
        print(json.dumps(youtube.page_tabs(), ensure_ascii=False, indent=2, default=str))
        return
    if sub in ("upload-prepare", "prepare-upload", "upload-plan"):
        values = workflows.parse_kv_args(args)
        plan, path = workflows.prepare_action("youtube_studio_upload_video", values)
        print("=" * 60)
        print("YouTube Studio upload prepare")
        print("=" * 60)
        print(f"saved: {path}")
        print(f"latest: {workflows.LATEST_PREPARE}")
        print(f"ready_for_approval: {plan['ready_for_approval']}")
        print(f"approval_required: {plan['approval']['required']}")
        print(f"state_change: {plan['state_change']}")
        if plan["missing_inputs"]:
            print(f"missing_inputs: {', '.join(plan['missing_inputs'])}")
        print("live_fill: python scripts/cdp_client.py google youtube upload-live-fill <plan_path> --no-final-submit")
        return
    if sub in ("upload-check", "check-upload", "upload-preapproval"):
        values = workflows.parse_kv_args(args)
        plan, path = youtube_upload.save_youtube_upload_plan(values)
        youtube_upload.print_youtube_upload_plan(plan, path)
        return
    if sub in ("upload-live-fill", "live-fill-upload"):
        if not args:
            print("  [error] usage: python scripts/cdp_client.py google youtube upload-live-fill <plan_path> --no-final-submit")
            return
        if "--no-final-submit" not in args:
            print("  [error] youtube upload-live-fill requires --no-final-submit")
            return
        result, path = live_inputs.run_live_input(args[0], no_final_submit=True)
        live_inputs.print_live_input_summary(result, path)
        return
    if sub in ("classify", "check"):
        target = args[0] if args else "www.youtube.com"
        operation = args[1] if len(args) > 1 else "read"
        print(json.dumps(youtube.classify_operation(target, operation), ensure_ascii=False, indent=2, default=str))
        return
    print(f"  [error] unknown youtube task: {sub}")


def _cmd_precision(sub: str, args: list[str]) -> None:
    if sub in ("build", "report", "verify"):
        report, json_path, md_path = precision_report.save_google_precision_report()
        precision_report.print_google_precision_summary(report, json_path, md_path)
        return
    print(f"  [error] unknown precision task: {sub}")


def _cmd_work(sub: str, args: list[str]) -> None:
    if sub in ("catalog", "list", "index"):
        catalog = workflows.build_action_catalog()
        path = workflows.save_action_catalog(catalog)
        workflows.print_action_summary(catalog, path)
        return
    if sub in ("adapters", "adapter-catalog"):
        catalog = workflows.build_adapter_catalog()
        path = workflows.save_adapter_catalog(catalog)
        workflows.print_adapter_summary(catalog, path)
        return
    if sub in ("undeveloped", "gaps", "missing", "todo"):
        report = workflows.build_undeveloped_report()
        path = workflows.save_undeveloped_report(report)
        workflows.print_undeveloped_summary(report, path)
        return
    if sub == "prepare":
        if not args:
            print("  [error] usage: python scripts/cdp_client.py google work prepare <action_key> [key=value ...]")
            return
        action_key = args[0]
        values = workflows.parse_kv_args(args[1:])
        plan, path = workflows.prepare_action(action_key, values)
        print("=" * 60)
        print("Google work prepare")
        print("=" * 60)
        print(f"action: {action_key}")
        print(f"saved: {path}")
        print(f"latest: {workflows.LATEST_PREPARE}")
        print(f"ready_for_approval: {plan['ready_for_approval']}")
        if plan["missing_inputs"]:
            print(f"missing_inputs: {', '.join(plan['missing_inputs'])}")
        print(f"approval_required: {plan['approval']['required']}")
        print(f"execute: {plan['execution_gate']['command']}")
        return
    if sub == "execute":
        if not args:
            print("  [error] usage: python scripts/cdp_client.py google work execute <plan_path> --approved --confirm=GOOGLE_APPROVED_EXECUTE")
            return
        plan_path = args[0]
        approved = "--approved" in args
        live_open = "--live-open" in args
        confirm = ""
        for arg in args[1:]:
            if arg.startswith("--confirm="):
                confirm = arg.split("=", 1)[1]
        result, path = workflows.execute_prepared_action(
            plan_path,
            approved=approved,
            confirm=confirm,
            live_open=live_open,
        )
        print("=" * 60)
        print("Google work execute")
        print("=" * 60)
        print(f"action: {result['action_key']}")
        print(f"status: {result['status']}")
        print(f"reason: {result['reason']}")
        print(f"state_change: {result['state_change']}")
        print(f"saved: {path}")
        return
    if sub == "verify":
        if not args:
            print("  [error] usage: python scripts/cdp_client.py google work verify <result_path>")
            return
        verification, path = workflows.verify_execution_result(args[0])
        print("=" * 60)
        print("Google work verify")
        print("=" * 60)
        print(f"action: {verification['action_key']}")
        print(f"status: {verification['status']}")
        print(f"saved: {path}")
        return
    if sub in ("live-fill", "fill"):
        if not args:
            print("  [error] usage: python scripts/cdp_client.py google work live-fill <plan_path> --no-final-submit")
            return
        if "--no-final-submit" not in args:
            print("  [error] live-fill requires --no-final-submit")
            return
        result, path = live_inputs.run_live_input(args[0], no_final_submit=True)
        live_inputs.print_live_input_summary(result, path)
        return
    if sub in ("live-coverage", "fill-coverage"):
        coverage = live_inputs.build_live_input_coverage()
        path = live_inputs.save_live_input_coverage(coverage)
        live_inputs.print_live_input_coverage(coverage, path)
        return
    if sub in ("live-fill-manifest", "fill-manifest"):
        if not args:
            print("  [error] usage: python scripts/cdp_client.py google work live-fill-manifest <manifest_path> --no-final-submit")
            return
        if "--no-final-submit" not in args:
            print("  [error] live-fill-manifest requires --no-final-submit")
            return
        summary, path = live_inputs.run_live_input_manifest(args[0], no_final_submit=True)
        live_inputs.print_live_manifest_summary(summary, path)
        return
    print(f"  [error] unknown google work task: {sub}")
