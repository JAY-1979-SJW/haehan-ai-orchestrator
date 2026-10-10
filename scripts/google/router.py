"""Google service router."""

from __future__ import annotations

import json
from collections.abc import Callable

from scripts.common.gate import check as gate_check

from scripts.google import ads_signup, ai_usage_labels, android_app_dev_labels, android_app_dev_report, live_surface_explorer, managed_console, oauth_console_fill, precision_report, router_management, vision_usage_gate, workspace_basic
from scripts.google.common import domain_taxonomy
from scripts.google.common import live_inputs
from scripts.google.common import subdomain_logic
from scripts.google.common import surface_explorer
from scripts.google.common import surfaces
from scripts.google.common import tab_logic
from scripts.google.common import workflows
from scripts.google.common import youtube_upload
from .cloud import live_console_explorer
from .gates import gate_google_oauth_required, gate_google_send_plan, gate_google_submit_plan  # noqa: F401
from .site_profile import GOOGLE_PROFILE  # noqa: F401
from .validators import validate_google_no_plain_secret  # noqa: F401
from .workspace import router as workspace_router

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
        "work ai_orchestrator.connectors.g2b": "done",
        "work prepare": "done",
        "work execute": "approval_gated",
        "work verify": "done",
        "work live-fill": "no_final_submit",
        "work live-coverage": "done",
        "login": "done",
        "session-check": "done",
        "check": "done",
    },
    "note": (
        "Gmail is implemented; Drive/Calendar/Docs/Sheets are partial. "
        "Google/YouTube/Console surfaces are catalog-first and approval-gated."
    ),
}


def _task_session_check(sub: str, args: list[str]) -> None:
    router_management.run_session_check()


def _task_check(sub: str, args: list[str]) -> None:
    router_management.run_module_check()


def _task_records(sub: str, args: list[str]) -> None:
    router_management.run_work_records(([sub] if sub else []) + args)


def _task_login(sub: str, args: list[str]) -> None:
    router_management.run_login()


def _task_mail(sub: str, args: list[str]) -> None:
    gate_check(
        "gmail_send" if sub in ("send", "compose") else "goto",
        risk="approve" if sub in ("send", "compose") else "auto",
    )
    workspace_router.run_workspace("gmail", sub or "list", args)


def _task_drive(sub: str, args: list[str]) -> None:
    gate_check("goto")
    workspace_router.run_workspace("drive", sub or "list", args)


def _task_calendar(sub: str, args: list[str]) -> None:
    gate_check("goto")
    workspace_router.run_workspace("calendar", sub or "today", args)


def _task_cloud(sub: str, args: list[str]) -> None:
    _cmd_cloud(sub or "summary", args)


def _task_console(sub: str, args: list[str]) -> None:
    _cmd_console(sub or "summary", args)


def _task_docs(sub: str, args: list[str]) -> None:
    gate_check("goto")
    workspace_router.run_workspace("docs", sub or "recent", args)


def _task_basic(sub: str, args: list[str]) -> None:
    _cmd_workspace_basic(sub or "catalog", args)


def _task_sheets(sub: str, args: list[str]) -> None:
    gate_check("goto")
    workspace_router.run_workspace("sheets", sub or "recent", args)


def _task_surfaces(sub: str, args: list[str]) -> None:
    _cmd_surfaces(sub or "catalog", args)


def _task_subdomains(sub: str, args: list[str]) -> None:
    _cmd_subdomains(sub or "catalog", args)


def _task_tabs(sub: str, args: list[str]) -> None:
    _cmd_tabs(sub or "catalog", args)


def _task_youtube(sub: str, args: list[str]) -> None:
    _cmd_youtube(sub or "catalog", args)


def _task_ai(sub: str, args: list[str]) -> None:
    _cmd_ai(sub or "catalog", args)


def _task_ads(sub: str, args: list[str]) -> None:
    _cmd_ads(sub or "signup-plan", args)


def _task_vision(sub: str, args: list[str]) -> None:
    _cmd_vision(sub or "gate", args)


def _task_android(sub: str, args: list[str]) -> None:
    _cmd_android(sub or "report", args)


def _task_domains(sub: str, args: list[str]) -> None:
    _cmd_domains(sub or "report", args)


def _task_precision(sub: str, args: list[str]) -> None:
    _cmd_precision(sub or "build", args)


def _task_work(sub: str, args: list[str]) -> None:
    _cmd_work(sub or "catalog", args)


# task 문자열 → 실행 함수. 원래 run_google() 의 match task: 순서를 그대로 옮긴 것 — 동작은
# 동일하다(2026-09-29 STD-08: match 32개 case 가 mccabe/pylint 에 "분기 25개"로 그대로 잡혀
# dict 조회로 바꿨다).
_TASK_HANDLERS: dict[str, Callable[[str, list[str]], None]] = {
    "session-check": _task_session_check,
    "check": _task_check,
    "module-check": _task_check,
    "modules": _task_check,
    "records": _task_records,
    "work-records": _task_records,
    "worklog": _task_records,
    "login": _task_login,
    "mail": _task_mail,
    "drive": _task_drive,
    "calendar": _task_calendar,
    "cloud": _task_cloud,
    "console": _task_console,
    "docs": _task_docs,
    "basic": _task_basic,
    "workspace-basic": _task_basic,
    "sheets": _task_sheets,
    "surfaces": _task_surfaces,
    "subdomains": _task_subdomains,
    "tabs": _task_tabs,
    "youtube": _task_youtube,
    "ai": _task_ai,
    "ads": _task_ads,
    "vision": _task_vision,
    "android": _task_android,
    "android-app": _task_android,
    "app-dev": _task_android,
    "domains": _task_domains,
    "taxonomy": _task_domains,
    "classification": _task_domains,
    "report": _task_precision,
    "precision": _task_precision,
    "work": _task_work,
    "actions": _task_work,
}


def run_google(site: str, task: str, sub: str, args: list[str]) -> None:
    """Route Google service workflows.

    site: google | gmail
    task: session-check | login | mail | drive | calendar | docs | sheets | surfaces | work
    """
    if site == "gmail":
        sub = sub or task
        task = "mail"

    handler = _TASK_HANDLERS.get(task)
    if handler is None:
        print(f"  [error] unknown google task: {task}")
        return
    handler(sub, args)


def _surfaces_live_logic(args: list[str]) -> None:
    logic = live_surface_explorer.build_google_surface_live_logic()
    print(json.dumps(logic, ensure_ascii=False, indent=2, default=str))


def _surfaces_live_read(args: list[str]) -> None:
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


def _surfaces_explore(args: list[str]) -> None:
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


def _surfaces_catalog(args: list[str]) -> None:
    catalog = surfaces.build_surface_catalog()
    path = surfaces.save_surface_catalog(catalog)
    surfaces.print_surface_summary(catalog, path)


_SURFACES_HANDLERS: dict[str, Callable[[list[str]], None]] = {
    "live-logic": _surfaces_live_logic,
    "logic": _surfaces_live_logic,
    "live-read": _surfaces_live_read,
    "live-explore": _surfaces_live_read,
    "explore": _surfaces_explore,
    "scan": _surfaces_explore,
    "read": _surfaces_explore,
    "catalog": _surfaces_catalog,
    "list": _surfaces_catalog,
    "index": _surfaces_catalog,
}


def _cmd_surfaces(sub: str, args: list[str] | None = None) -> None:
    args = args or []
    handler = _SURFACES_HANDLERS.get(sub)
    if handler is None:
        print(f"  [error] unknown surfaces task: {sub}")
        return
    handler(args)


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
            print(
                "  [error] usage: python scripts/entry/cdp_cli.py google subdomains classify <host-or-service> [operation]"
            )
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
            print(
                "  [error] usage: python scripts/entry/cdp_cli.py google tabs classify <tab> <host-or-service> [operation]"
            )
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
        print(
            json.dumps(
                managed_console.build_youtube_oauth_console_open_plan(
                    secret_action_mode=secret_action_mode,
                    secret_issue_approved=secret_issue_approved,
                ),
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
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
        print(
            json.dumps(
                {
                    "commands": [
                        "youtube-oauth-plan",
                        "youtube-oauth-open --dry-run",
                        "youtube-oauth-open",
                        "youtube-oauth-fill --dry-run",
                        "youtube-oauth-fill",
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    print(f"  [error] unknown console task: {sub}")


def _cmd_ai(sub: str, args: list[str]) -> None:
    if sub in ("labels", "usage", "pricing", "catalog"):
        print(json.dumps(ai_usage_labels.build_google_ai_usage_labels(), ensure_ascii=False, indent=2, default=str))
        return
    print(f"  [error] unknown ai task: {sub}")


def _cmd_ads(sub: str, args: list[str]) -> None:
    values = _parse_option_args(args)
    google_work_mode = values.get("google-work-mode") or values.get("google_work_mode")
    background_approved = values.get("background-approved", values.get("background_approved", "false")).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    ads_signup_approved = values.get("ads-signup-approved", values.get("ads_signup_approved", "false")).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    website_asset_scan_approved = values.get(
        "website-asset-scan-approved",
        values.get("website_asset_scan_approved", "false"),
    ).lower() in ("1", "true", "yes", "on")
    if sub in ("signup-plan", "signup", "account-signup", "keyword-planner-gate"):
        print(
            json.dumps(
                ads_signup.build_ads_signup_plan(
                    google_work_mode=google_work_mode,
                    background_approved=background_approved,
                    ads_signup_approved=ads_signup_approved,
                    website_asset_scan_approved=website_asset_scan_approved,
                ),
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return
    if sub in ("classify-signup-screen", "classify"):
        text = " ".join(args)
        print(json.dumps(ads_signup.classify_ads_signup_screen(text), ensure_ascii=False, indent=2, default=str))
        return
    if sub in ("summary", "catalog"):
        print(
            json.dumps(
                {"commands": ["signup-plan --google-work-mode=main --ads-signup-approved"]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    print(f"  [error] unknown ads task: {sub}")


def _cmd_workspace_basic(sub: str, args: list[str]) -> None:
    values = _parse_option_args(args)
    google_work_mode = values.get("google-work-mode") or values.get("google_work_mode")
    background_approved = values.get("background-approved", values.get("background_approved", "false")).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    final_execution_approved = values.get(
        "final-execution-approved",
        values.get("final_execution_approved", "false"),
    ).lower() in ("1", "true", "yes", "on")
    if sub in ("catalog", "list", "summary"):
        print(json.dumps(workspace_basic.build_basic_feature_catalog(), ensure_ascii=False, indent=2, default=str))
        return
    if sub in ("plan", "prepare"):
        if len(args) < 2:
            print(
                "  [error] usage: python scripts/entry/cdp_cli.py google basic plan <surface> <operation> [key=value ...] --google-work-mode=main"
            )
            return
        surface = args[0]
        operation = args[1]
        plan_values = workflows.parse_kv_args([arg for arg in args[2:] if not arg.startswith("--")])
        print(
            json.dumps(
                workspace_basic.build_basic_work_plan(
                    surface,
                    operation,
                    plan_values,
                    google_work_mode=google_work_mode,
                    background_approved=background_approved,
                    final_execution_approved=final_execution_approved,
                ),
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return
    print(f"  [error] unknown workspace basic task: {sub}")


def _cmd_vision(sub: str, args: list[str]) -> None:
    if sub not in ("gate", "usage-gate", "monthly-free-gate", "free-gate"):
        print(f"  [error] unknown vision task: {sub}")
        return
    values = _parse_option_args(args)
    features = values.get("features", "text_detection").replace(";", ",").split(",")
    payload = vision_usage_gate.evaluate_vision_monthly_free_gate(
        current_month_units=int(values.get("current-month-units", "0")),
        image_count=int(values.get("images", "0")),
        page_count=int(values.get("pages", "0")),
        features=features,
        cost_approved=values.get("cost-approved", "false").lower() in ("1", "true", "yes"),
    )
    path = vision_usage_gate.save_vision_monthly_free_gate(payload)
    print(
        "google_vision_usage_gate "
        f"status={payload['status']} ok={payload['ok']} "
        f"current={payload['current_month_units']} requested={payload['requested_units']} "
        f"projected={payload['projected_month_units']} limit={payload['monthly_free_limit_units']} "
        f"report={path}"
    )


def _cmd_android(sub: str, args: list[str]) -> None:
    if sub in ("labels", "usage", "pricing", "catalog"):
        print(
            json.dumps(android_app_dev_labels.build_android_app_dev_labels(), ensure_ascii=False, indent=2, default=str)
        )
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


def _youtube_catalog(args: list[str]) -> None:
    from scripts.google import youtube

    print(json.dumps(youtube.catalog(), ensure_ascii=False, indent=2, default=str))


def _youtube_tabs(args: list[str]) -> None:
    from scripts.google import youtube

    print(json.dumps(youtube.page_tabs(), ensure_ascii=False, indent=2, default=str))


def _youtube_signal_model(args: list[str]) -> None:
    from scripts.google import youtube

    print(json.dumps(youtube.public_signal_model(), ensure_ascii=False, indent=2, default=str))


def _youtube_search(args: list[str]) -> None:
    from scripts.google import youtube

    values = _parse_option_args(args)
    positional = [arg for arg in args if not arg.startswith("--") and "=" not in arg]
    query = values.get("query") or values.get("q") or " ".join(positional)
    if not query:
        print(
            "  [error] usage: python scripts/entry/cdp_cli.py google youtube search --query=... "
            "[--source=auto|official|browser] [--limit=10]"
        )
        return
    result, path = youtube.video_search(
        query,
        max_results=int(values.get("limit", values.get("max", "10"))),
        source=values.get("source", "auto"),
        wait_seconds=float(values.get("wait-seconds", values.get("wait_seconds", "3"))),
    )
    print("=" * 60)
    print("Google YouTube search")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"source: {result.get('source')}")
    print(f"result_count: {result.get('result_count', 0)}")
    print(f"reason: {result.get('reason') or '-'}")
    print(f"saved: {path}")
    for item in result.get("results", [])[:10]:
        print(f"- {item.get('video_id') or '-'} | {item.get('title') or '-'} | {item.get('channel_title') or '-'}")


def _youtube_rank(args: list[str]) -> None:
    from scripts.google import youtube

    values = _parse_option_args(args)
    positional = [arg for arg in args if not arg.startswith("--") and "=" not in arg]
    query = values.get("query") or values.get("q") or " ".join(positional)
    collect_transcripts = values.get("collect-transcripts", values.get("collect_transcripts", "true")).lower() not in (
        "0",
        "false",
        "no",
    )
    result, path = youtube.rank_analysis(
        query=query,
        search_report_path=values.get("search-report") or values.get("search_report"),
        max_videos=int(values.get("limit", values.get("max", "5"))),
        collect_transcripts=collect_transcripts,
        wait_seconds=float(values.get("wait-seconds", values.get("wait_seconds", "3"))),
    )
    print("=" * 60)
    print("Google YouTube rank transcript analysis")
    print("=" * 60)
    print(f"query: {result.get('query') or '-'}")
    print(f"analyzed_count: {result.get('analyzed_count', 0)}")
    print(f"raw_transcript_stored: {result.get('raw_transcript_stored', False)}")
    print(f"saved: {path}")
    for item in result.get("ranked_videos", [])[:10]:
        scores = item.get("scores", {})
        transcript = item.get("transcript_summary", {})
        print(
            f"- score={scores.get('overall_opportunity_score')} "
            f"rank={item.get('search_rank')} "
            f"transcript={transcript.get('status')} "
            f"{item.get('title') or '-'}"
        )


def _youtube_research_run(args: list[str]) -> None:
    from scripts.google import youtube

    values = _parse_option_args(args)
    topic = values.get("topic", "")
    auto_keywords = values.get("auto-keywords", values.get("auto_keywords", "true")).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    raw_keywords = values.get("keywords") or values.get("queries") or values.get("query") or values.get("q") or ""
    keywords = [item.strip() for item in raw_keywords.replace(";", ",").split(",") if item.strip()]
    keywords.extend([arg for arg in args if not arg.startswith("--") and "=" not in arg])
    collect_transcripts = values.get("collect-transcripts", values.get("collect_transcripts", "false")).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    collect_comments = values.get("collect-comments", values.get("collect_comments", "true")).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    result, json_path, markdown_path = youtube.market_research_run(
        topic=topic,
        keywords=keywords,
        auto_keywords=auto_keywords,
        per_keyword_limit=int(
            values.get(
                "per-keyword-limit", values.get("per_keyword_limit", values.get("videos", values.get("limit", "10")))
            )
        ),
        source=values.get("source", "auto"),
        collect_transcripts=collect_transcripts,
        max_transcript_videos=int(
            values.get("max-transcript-videos", values.get("max_transcript_videos", values.get("transcripts", "5")))
        ),
        collect_comments=collect_comments,
        max_comment_videos=int(values.get("max-comment-videos", values.get("max_comment_videos", "5"))),
        max_comments=int(values.get("max-comments", values.get("max_comments", values.get("comments", "20")))),
        max_comment_pages=int(values.get("max-comment-pages", values.get("max_comment_pages", "1"))),
        include_comment_replies=values.get(
            "include-comment-replies", values.get("include_comment_replies", "false")
        ).lower()
        in (
            "1",
            "true",
            "yes",
            "on",
        ),
        wait_seconds=float(values.get("wait-seconds", values.get("wait_seconds", "3"))),
    )
    print("=" * 60)
    print("Google YouTube market research run")
    print("=" * 60)
    print(f"status: {result.get('status')}")
    print(f"topic: {result.get('topic') or '-'}")
    print(f"keywords: {', '.join(result.get('keywords', [])) or '-'}")
    print(f"unique_video_count: {result.get('unique_video_count', 0)}")
    print(f"json: {json_path}")
    print(f"markdown: {markdown_path}")
    for item in result.get("top_videos", [])[:10]:
        scores = item.get("scores", {})
        topic_info = item.get("topic_classification", {})
        print(
            f"- score={scores.get('topic_opportunity_score')} "
            f"coverage={item.get('coverage_count')} "
            f"topic={topic_info.get('primary_topic')} "
            f"{item.get('title') or '-'}"
        )


def _youtube_topic(args: list[str]) -> None:
    from scripts.google import youtube

    values = _parse_option_args(args)
    keywords: list[str] = []
    topic = values.get("topic", "")
    auto_keywords = values.get("auto-keywords", values.get("auto_keywords", "false")).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if topic:
        keywords.extend(youtube.expand_topic_keywords(topic, auto_keywords=auto_keywords))
    raw_keywords = values.get("keywords") or values.get("queries") or values.get("query") or values.get("q") or ""
    if raw_keywords:
        keywords.extend([item.strip() for item in raw_keywords.replace(";", ",").split(",") if item.strip()])
    keywords.extend([arg for arg in args if not arg.startswith("--") and "=" not in arg])
    collect_transcripts = values.get("collect-transcripts", values.get("collect_transcripts", "false")).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    collect_comments = values.get("collect-comments", values.get("collect_comments", "false")).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    result, path = youtube.topic_analysis(
        keywords,
        per_keyword_limit=int(
            values.get("per-keyword-limit", values.get("per_keyword_limit", values.get("limit", "10")))
        ),
        source=values.get("source", "auto"),
        collect_transcripts=collect_transcripts,
        max_transcript_videos=int(values.get("max-transcript-videos", values.get("max_transcript_videos", "5"))),
        collect_comments=collect_comments,
        max_comment_videos=int(values.get("max-comment-videos", values.get("max_comment_videos", "5"))),
        max_comments=int(values.get("max-comments", values.get("max_comments", "20"))),
        max_comment_pages=int(values.get("max-comment-pages", values.get("max_comment_pages", "1"))),
        include_comment_replies=values.get(
            "include-comment-replies", values.get("include_comment_replies", "false")
        ).lower()
        in (
            "1",
            "true",
            "yes",
            "on",
        ),
        wait_seconds=float(values.get("wait-seconds", values.get("wait_seconds", "3"))),
    )
    print("=" * 60)
    print("Google YouTube keyword topic market analysis")
    print("=" * 60)
    print(f"status: {result.get('status')}")
    print(f"keywords: {', '.join(result.get('keywords', [])) or '-'}")
    print(f"unique_video_count: {result.get('unique_video_count', 0)}")
    print(f"raw_transcript_stored: {result.get('raw_transcript_stored', False)}")
    print(f"raw_comments_stored: {result.get('raw_comments_stored', False)}")
    print(f"saved: {path}")
    for item in result.get("videos", [])[:10]:
        scores = item.get("scores", {})
        topic = item.get("topic_classification", {})
        print(
            f"- score={scores.get('topic_opportunity_score')} "
            f"coverage={item.get('coverage_count')} "
            f"rank={item.get('best_observed_rank')} "
            f"topic={topic.get('primary_topic')} "
            f"{item.get('title') or '-'}"
        )


def _youtube_upload_prepare(args: list[str]) -> None:
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
    print("live_fill: python scripts/entry/cdp_cli.py google youtube upload-live-fill <plan_path> --no-final-submit")


def _youtube_upload_check(args: list[str]) -> None:
    values = workflows.parse_kv_args(args)
    plan, path = youtube_upload.save_youtube_upload_plan(values)
    youtube_upload.print_youtube_upload_plan(plan, path)


def _run_live_fill_plan(args: list[str], usage: str, requirement: str) -> None:
    """실입력 계획 파일(args[0])을 최종 제출 없이 채운다 — 인자 없거나 --no-final-submit 빠지면 오류 출력 후 중단."""
    if not args:
        print(usage)
        return
    if "--no-final-submit" not in args:
        print(requirement)
        return
    result, path = live_inputs.run_live_input(args[0], no_final_submit=True)
    live_inputs.print_live_input_summary(result, path)


def _youtube_upload_live_fill(args: list[str]) -> None:
    _run_live_fill_plan(
        args,
        "  [error] usage: python scripts/entry/cdp_cli.py google youtube upload-live-fill <plan_path> --no-final-submit",
        "  [error] youtube upload-live-fill requires --no-final-submit",
    )


def _youtube_classify(args: list[str]) -> None:
    from scripts.google import youtube

    target = args[0] if args else "www.youtube.com"
    operation = args[1] if len(args) > 1 else "read"
    print(json.dumps(youtube.classify_operation(target, operation), ensure_ascii=False, indent=2, default=str))


_YOUTUBE_HANDLERS: dict[str, Callable[[list[str]], None]] = {
    "catalog": _youtube_catalog,
    "summary": _youtube_catalog,
    "tabs": _youtube_tabs,
    "page-tabs": _youtube_tabs,
    "subtabs": _youtube_tabs,
    "signal-model": _youtube_signal_model,
    "public-signal-model": _youtube_signal_model,
    "data-model": _youtube_signal_model,
    "limits": _youtube_signal_model,
    "search": _youtube_search,
    "search-videos": _youtube_search,
    "video-search": _youtube_search,
    "rank": _youtube_rank,
    "rank-analysis": _youtube_rank,
    "analyze-search": _youtube_rank,
    "search-analysis": _youtube_rank,
    "research-run": _youtube_research_run,
    "market-run": _youtube_research_run,
    "run-market-research": _youtube_research_run,
    "topic": _youtube_topic,
    "topic-analysis": _youtube_topic,
    "market": _youtube_topic,
    "market-analysis": _youtube_topic,
    "upload-prepare": _youtube_upload_prepare,
    "prepare-upload": _youtube_upload_prepare,
    "upload-plan": _youtube_upload_prepare,
    "upload-check": _youtube_upload_check,
    "check-upload": _youtube_upload_check,
    "upload-preapproval": _youtube_upload_check,
    "upload-live-fill": _youtube_upload_live_fill,
    "live-fill-upload": _youtube_upload_live_fill,
    "classify": _youtube_classify,
    "check": _youtube_classify,
}


def _cmd_youtube(sub: str, args: list[str]) -> None:
    handler = _YOUTUBE_HANDLERS.get(sub)
    if handler is None:
        print(f"  [error] unknown youtube task: {sub}")
        return
    handler(args)


def _cmd_precision(sub: str, args: list[str]) -> None:
    if sub in ("build", "report", "verify"):
        report, json_path, md_path = precision_report.save_google_precision_report()
        precision_report.print_google_precision_summary(report, json_path, md_path)
        return
    print(f"  [error] unknown precision task: {sub}")


def _work_catalog(args: list[str]) -> None:
    catalog = workflows.build_action_catalog()
    path = workflows.save_action_catalog(catalog)
    workflows.print_action_summary(catalog, path)


def _work_adapters(args: list[str]) -> None:
    catalog = workflows.build_adapter_catalog()
    path = workflows.save_adapter_catalog(catalog)
    workflows.print_adapter_summary(catalog, path)


def _work_undeveloped(args: list[str]) -> None:
    report = workflows.build_undeveloped_report()
    path = workflows.save_undeveloped_report(report)
    workflows.print_undeveloped_summary(report, path)


def _work_prepare(args: list[str]) -> None:
    if not args:
        print("  [error] usage: python scripts/entry/cdp_cli.py google work prepare <action_key> [key=value ...]")
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


def _work_execute(args: list[str]) -> None:
    if not args:
        print(
            "  [error] usage: python scripts/entry/cdp_cli.py google work execute "
            "<plan_path> --approved --confirm=GOOGLE_APPROVED_EXECUTE"
        )
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


def _work_verify(args: list[str]) -> None:
    if not args:
        print("  [error] usage: python scripts/entry/cdp_cli.py google work verify <result_path>")
        return
    verification, path = workflows.verify_execution_result(args[0])
    print("=" * 60)
    print("Google work verify")
    print("=" * 60)
    print(f"action: {verification['action_key']}")
    print(f"status: {verification['status']}")
    print(f"saved: {path}")


def _work_live_fill(args: list[str]) -> None:
    _run_live_fill_plan(
        args,
        "  [error] usage: python scripts/entry/cdp_cli.py google work live-fill <plan_path> --no-final-submit",
        "  [error] live-fill requires --no-final-submit",
    )


def _work_live_coverage(args: list[str]) -> None:
    coverage = live_inputs.build_live_input_coverage()
    path = live_inputs.save_live_input_coverage(coverage)
    live_inputs.print_live_input_coverage(coverage, path)


def _work_live_fill_manifest(args: list[str]) -> None:
    if not args:
        print(
            "  [error] usage: python scripts/entry/cdp_cli.py google work live-fill-manifest "
            "<manifest_path> --no-final-submit"
        )
        return
    if "--no-final-submit" not in args:
        print("  [error] live-fill-manifest requires --no-final-submit")
        return
    summary, path = live_inputs.run_live_input_manifest(args[0], no_final_submit=True)
    live_inputs.print_live_manifest_summary(summary, path)


_WORK_HANDLERS: dict[str, Callable[[list[str]], None]] = {
    "catalog": _work_catalog,
    "list": _work_catalog,
    "index": _work_catalog,
    "ai_orchestrator.connectors.g2b": _work_adapters,
    "adapter-catalog": _work_adapters,
    "undeveloped": _work_undeveloped,
    "gaps": _work_undeveloped,
    "missing": _work_undeveloped,
    "todo": _work_undeveloped,
    "prepare": _work_prepare,
    "execute": _work_execute,
    "verify": _work_verify,
    "live-fill": _work_live_fill,
    "fill": _work_live_fill,
    "live-coverage": _work_live_coverage,
    "fill-coverage": _work_live_coverage,
    "live-fill-manifest": _work_live_fill_manifest,
    "fill-manifest": _work_live_fill_manifest,
}


def _cmd_work(sub: str, args: list[str]) -> None:
    handler = _WORK_HANDLERS.get(sub)
    if handler is None:
        print(f"  [error] unknown google work task: {sub}")
        return
    handler(args)


def _parse_option_args(args: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    index = 0
    while index < len(args):
        arg = args[index]
        if not arg.startswith("--"):
            index += 1
            continue
        key = arg[2:]
        if "=" in key:
            name, value = key.split("=", 1)
            values[name] = value
        elif index + 1 < len(args) and not args[index + 1].startswith("--"):
            values[key] = args[index + 1]
            index += 1
        else:
            values[key] = "true"
        index += 1
    return values
