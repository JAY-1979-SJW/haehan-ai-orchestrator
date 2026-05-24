"""Google service router."""
from __future__ import annotations

from . import live_inputs, surface_explorer, surfaces, workflows
from .base import check_session
from .workspace import router as workspace_router
from scripts.gate import check as gate_check
from .gates import gate_google_send_plan, gate_google_submit_plan, gate_google_oauth_required  # noqa: F401
from .profile import GOOGLE_PROFILE  # noqa: F401
from .validators import validate_google_no_plain_secret  # noqa: F401

__status__ = {
    "tasks": {
        "mail list": "done",
        "mail compose": "done",
        "mail send": "done",
        "drive list": "partial",
        "calendar today": "partial",
        "docs recent": "partial",
        "sheets recent": "partial",
        "surfaces catalog": "done",
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
        case "docs":
            gate_check("goto")
            workspace_router.run_workspace("docs", sub or "recent", args)
        case "sheets":
            gate_check("goto")
            workspace_router.run_workspace("sheets", sub or "recent", args)
        case "surfaces":
            _cmd_surfaces(sub or "catalog", args)
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
