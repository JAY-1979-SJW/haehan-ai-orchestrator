"""SmartStore service router."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.gate import check as gate_check
from scripts.logger import get_logger
from scripts.naver.live_safety import before_live_navigation, ensure_page_safe
from scripts.smartstore.actions import APPROVAL_CONFIRM_TEXT

__status__ = {
    "tasks": {
        "action catalog": "done",
        "prepare plan": "done",
        "approved submit": "done",
        "product list": "partial",
        "product register": "complete_baseline",
        "order new": "partial",
        "inventory": "partial",
        "seo": "todo",
        "ai review-reply": "todo",
        "competitor": "todo",
        "csv import": "todo",
        "analytics": "partial",
    },
    "note": (
        "SmartStore now has a static action catalog, dry-run prepare plans, "
        "and approval-gated submit records. Live Naver exploration remains paused "
        "after robot detection unless explicitly approved."
    ),
}

_log = get_logger(__name__)


def run_smartstore(task: str | None, sub: str | None, args: list[str]) -> None:
    """Route SmartStore commands.

    task: actions | prepare | submit | product | order | inventory | seo |
          ai | competitor | csv | analytics | session-check | live-probe |
          page-tools | page-functions | dashboard | menus | advanced |
          draft-fill | login-watch
    """
    match task or "help":
        case "actions" | "action-catalog":
            _cmd_actions(sub or "catalog", args)
        case "prepare":
            _cmd_prepare(sub or "product", args)
        case "submit":
            _cmd_submit(sub or "product", args)
        case "product":
            _cmd_product(sub, args)
        case "order":
            _cmd_order(sub, args)
        case "inventory":
            _cmd_inventory(sub, args)
        case "seo":
            _cmd_seo(sub, args)
        case "ai":
            _cmd_ai(sub, args)
        case "competitor":
            _cmd_competitor(sub, args)
        case "csv":
            _cmd_csv(sub, args)
        case "analytics":
            _cmd_analytics(sub, args)
        case "session-check":
            _cmd_session_check()
        case "live-probe" | "dashboard-check" | "probe":
            _cmd_live_probe(([sub] if sub else []) + args)
        case "page-tools" | "page-inventory" | "tools-from-page":
            _cmd_page_tools(([sub] if sub else []) + args)
        case "page-functions" | "current-page-functions" | "functions":
            _cmd_page_functions(([sub] if sub else []) + args)
        case "dashboard" | "dashboard-summary":
            _cmd_dashboard_summary(([sub] if sub else []) + args)
        case "menus" | "menu":
            _cmd_menus(sub, args)
        case "advanced" | "analyze-menu" | "menu-advanced":
            _cmd_advanced(sub, args)
        case "draft-fill" | "fill-draft" | "write-draft":
            _cmd_draft_fill(sub, args)
        case "product-register" | "register-pipeline" | "pipeline":
            _cmd_product_register(sub, args)
        case "approved" | "approve":
            _cmd_approved(sub, args)
        case "login-watch" | "watch-login":
            _cmd_login_watch(([sub] if sub else []) + args)
        case _:
            _print_help()


def _option_value(args: list[str], prefix: str) -> str | None:
    for arg in args:
        text = str(arg)
        if text.startswith(prefix):
            return text.split("=", 1)[1]
    return None


def _flag(args: list[str], name: str) -> bool:
    return name in args


def _live_page(args: list[str], *, workflow: str):
    before_live_navigation(args, site="smartstore", workflow=workflow)
    from scripts.web_connector import get_page

    page = get_page()
    ensure_page_safe(page, site="smartstore", workflow=workflow, phase="before_action")
    return page


def _read_json_arg(args: list[str]) -> tuple[dict, str]:
    try:
        from scripts.smartstore.product_register.input_data import require_product_data_arg

        source = require_product_data_arg(args)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return source.data, source.path


def _cmd_actions(sub: str | None, args: list[str]) -> None:
    from scripts.smartstore.actions import (
        build_action_catalog,
        print_action_catalog_summary,
        save_action_catalog,
    )

    if sub not in ("catalog", "actions", "list", None, ""):
        print("usage: python scripts/cdp_client.py smartstore actions catalog")
        return
    gate_check("scan_page")
    catalog = build_action_catalog()
    path = save_action_catalog(catalog)
    print_action_catalog_summary(catalog, path)


def _cmd_prepare(sub: str | None, args: list[str]) -> None:
    from scripts.smartstore.actions import build_prepare_plan, print_prepare_plan_summary, save_prepare_plan

    if sub not in ("product", "register", "general", "group", None, ""):
        print(
            "usage: python scripts/cdp_client.py smartstore prepare product "
            "--data=<json> [--product-type=general|group] [--save-after] [--dry-run]"
        )
        return

    data, data_path = _read_json_arg(args)
    product_type = _option_value(args, "--product-type=") or ("group" if sub == "group" else "general")
    save_after = _flag(args, "--save-after") or _flag(args, "--save")
    dry_run = _flag(args, "--dry-run") or not _flag(args, "--execute")

    gate_check("type_into", service="smartstore", product_type=product_type, save_after=save_after)

    plan = build_prepare_plan(data, product_type=product_type, save_after=save_after, dry_run=dry_run)
    plan["data_path"] = data_path
    path = save_prepare_plan(plan)
    print_prepare_plan_summary(plan, path)

    if not plan["validation"]["ok"]:
        raise SystemExit("SmartStore product data validation failed")
    if save_after and not dry_run:
        raise SystemExit(
            f"live save requires submit command with --approved --confirm={APPROVAL_CONFIRM_TEXT}"
        )
    if dry_run:
        return

    from scripts.smartstore import SmartStore
    from scripts.smartstore.actions import save_submit_record
    page = _live_page(args, workflow="product_prepare")
    ss = SmartStore(page)
    if product_type == "general":
        result = ss.store.register_general_product(data, save_after=save_after, require_confirm=True)
    else:
        result = ss.store.register_product(data, save_after=save_after, require_confirm=True)
    record = {**plan, "ok": bool(result.get("ok")), "prepared": bool(result.get("ok")), "result": result}
    out = save_submit_record(record)
    _print_result(record)
    print(f"saved: {out}")


def _cmd_submit(sub: str | None, args: list[str]) -> None:
    from scripts.smartstore.actions import build_submit_plan, load_product_data, save_submit_record

    product_type = _option_value(args, "--product-type=") or "general"
    action_id = _option_value(args, "--action-id=") or f"product.{product_type}.save"
    data_path = _option_value(args, "--data=") or _option_value(args, "--file=")
    dry_run = _flag(args, "--dry-run") or not _flag(args, "--execute")
    approved = _flag(args, "--approved")
    confirm = _option_value(args, "--confirm=") or ""
    approved_by = _option_value(args, "--approved-by=") or "operator"

    if not approved or confirm != APPROVAL_CONFIRM_TEXT:
        raise SystemExit(f"smartstore submit requires --approved --confirm={APPROVAL_CONFIRM_TEXT}")
    gate_check("eum_register", force=approved, service="smartstore", action_id=action_id)

    plan = build_submit_plan(action_id=action_id, product_type=product_type, approved_by=approved_by, dry_run=dry_run)
    if data_path:
        plan["data_path"] = data_path
    if dry_run:
        record = {**plan, "ok": True, "note": "dry-run only; no browser write"}
        path = save_submit_record(record)
        _print_result(record)
        print(f"saved: {path}")
        return

    if not data_path:
        raise SystemExit("non-dry-run submit requires --data=<json>")
    data = load_product_data(data_path)

    from scripts.smartstore import SmartStore
    page = _live_page(args, workflow="product_submit")
    ss = SmartStore(page)
    if action_id == "product.general.save":
        result = ss.store.register_general_product(data, save_after=True, require_confirm=False)
    elif action_id == "product.group.save":
        result = ss.store.register_product(data, save_after=True, require_confirm=False)
    elif action_id == "product.bulk.save":
        products = data.get("products")
        if not isinstance(products, list):
            raise SystemExit("bulk submit data requires products list")
        result = ss.store.register_bulk(products, product_type=product_type, save_after=True, require_confirm=False)
    else:
        raise SystemExit(f"unsupported live SmartStore submit action: {action_id}")

    record = {
        **plan,
        "ok": bool(result.get("ok")),
        "prepared": bool(result.get("ok")),
        "saved": bool(result.get("saved")),
        "submit_executed": bool(result.get("saved")),
        "result": result,
    }
    path = save_submit_record(record)
    _print_result(record)
    print(f"saved: {path}")


def _cmd_product(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    action = sub or "list"
    print(f"[smartstore] product {action}")
    if action == "list":
        from scripts.smartstore import SmartStore
        ss = SmartStore(_live_page(args, workflow="product_list"))
        result = ss.store.list_products()
        _print_result(result)
    elif action == "register":
        _cmd_prepare("product", args)
    else:
        print(f"unknown product subcommand: {action}")


def _cmd_order(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    action = sub or "new"
    print(f"[smartstore] order {action}")
    from scripts.smartstore import SmartStore
    ss = SmartStore(_live_page(args, workflow="order"))
    result = ss.orders.fetch_new()
    _print_result(result)


def _cmd_inventory(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    print("[smartstore] inventory")
    from scripts.smartstore import SmartStore
    ss = SmartStore(_live_page(args, workflow="inventory"))
    result = ss.inventory.check_low_stock()
    _print_result(result)


def _cmd_seo(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    print("[smartstore] seo")
    from scripts.smartstore import SmartStore
    ss = SmartStore(_live_page(args, workflow="seo"))
    result = ss.seo.optimize({})
    _print_result(result)


def _cmd_ai(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    print("[smartstore] ai review reply")
    from scripts.smartstore import SmartStore
    ss = SmartStore(_live_page(args, workflow="ai_review_reply"))
    review = " ".join(args) if args else ""
    result = ss.ai.reply_review(review) if review else {"error": "review text required"}
    _print_result(result)


def _cmd_competitor(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    keyword = " ".join(args) or sub or ""
    print(f"[smartstore] competitor: {keyword or '(keyword required)'}")
    from scripts.smartstore import SmartStore
    ss = SmartStore(_live_page(args, workflow="competitor"))
    result = ss.competitor.track(keyword)
    _print_result(result)


def _cmd_csv(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    file_path = args[0] if args else sub or ""
    if not file_path:
        print("usage: smartstore csv <file-path>")
        return
    print(f"[smartstore] csv import: {file_path}")
    from scripts.smartstore import SmartStore
    ss = SmartStore(_live_page(args, workflow="csv_import"))
    result = ss.csv.import_csv(file_path)
    _print_result(result)


def _cmd_analytics(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    print("[smartstore] analytics today")
    from scripts.smartstore import SmartStore
    ss = SmartStore(_live_page(args, workflow="analytics"))
    result = ss.analytics.collect_today()
    _print_result(result)


def _cmd_session_check() -> None:
    from scripts.site_base import check_session

    print("=" * 60)
    print("SmartStore session check")
    print("=" * 60)
    result = check_session("naver")
    if result["error"]:
        print(f"connection failed: {result['error']}")
    elif result["logged_in"]:
        print("Naver login ok; SmartStore access can be checked manually")
    else:
        print("Naver login required")
    print("=" * 60)


def _cmd_live_probe(args: list[str]) -> None:
    from scripts.smartstore.live_probe import probe_dashboard, save_probe_report

    allow_mixed = _flag(args, "--allow-mixed-readonly")
    wait_seconds = float(_option_value(args, "--wait=") or 6.0)
    result = probe_dashboard(allow_mixed_readonly=allow_mixed, wait_seconds=wait_seconds)
    path = save_probe_report(result)
    _print_result(result.to_dict())
    print(f"saved: {path}")


def _cmd_page_tools(args: list[str]) -> None:
    from scripts.smartstore.page_tools import collect_page_tools, save_page_tools_report

    allow_mixed = _flag(args, "--allow-mixed-readonly")
    wait_seconds = float(_option_value(args, "--wait=") or 8.0)
    result = collect_page_tools(allow_mixed_readonly=allow_mixed, wait_seconds=wait_seconds)
    path = save_page_tools_report(result)
    _print_result(result.to_dict())
    print(f"saved: {path}")


def _cmd_page_functions(args: list[str]) -> None:
    from scripts.smartstore.page_functions import collect_current_page_functions, save_page_functions_report

    allow_mixed = _flag(args, "--allow-mixed-readonly")
    result = collect_current_page_functions(allow_mixed_readonly=allow_mixed)
    path = save_page_functions_report(result)
    _print_result(result.to_dict())
    print(f"saved: {path}")
    if not result.ok:
        raise SystemExit(1)


def _cmd_dashboard_summary(args: list[str]) -> None:
    from scripts.smartstore.page_tools import collect_dashboard_summary, save_dashboard_report

    allow_mixed = _flag(args, "--allow-mixed-readonly")
    result = collect_dashboard_summary(allow_mixed_readonly=allow_mixed)
    path = save_dashboard_report(result)
    _print_result(result.to_dict())
    print(f"saved: {path}")


def _cmd_menus(sub: str | None, args: list[str]) -> None:
    from scripts.smartstore.menu_tools import (
        build_menu_catalog,
        collect_all_menu_snapshots,
        collect_menu_snapshot,
        list_menu_specs,
        save_all_menu_snapshots,
        save_menu_catalog,
        save_menu_snapshot,
    )

    action = sub or "catalog"
    allow_mixed = _flag(args, "--allow-mixed-readonly")
    wait_seconds = float(_option_value(args, "--wait=") or 6.0)

    if action in ("catalog", "list", "tools"):
        catalog = build_menu_catalog()
        path = save_menu_catalog(catalog)
        _print_result(catalog)
        print(f"saved: {path}")
        return

    if action in ("snapshot", "open", "inspect"):
        menu_id = _option_value(args, "--menu=") or (args[0] if args else "")
        if not menu_id:
            names = ", ".join(spec.menu_id for spec in list_menu_specs())
            raise SystemExit(f"menu id required: --menu=<id>; available={names}")
        result = collect_menu_snapshot(menu_id, allow_mixed_readonly=allow_mixed, wait_seconds=wait_seconds)
        path = save_menu_snapshot(result)
        _print_result(result.to_dict())
        print(f"saved: {path}")
        if not result.ok:
            raise SystemExit(1)
        return

    if action in ("all", "snapshot-all", "inspect-all"):
        payload = collect_all_menu_snapshots(allow_mixed_readonly=allow_mixed, wait_seconds=wait_seconds)
        path = save_all_menu_snapshots(payload)
        _print_result(payload)
        print(f"saved: {path}")
        if payload.get("ok_count") != payload.get("menu_count"):
            raise SystemExit(1)
        return

    menu_ids = {spec.menu_id for spec in list_menu_specs()}
    if action in menu_ids:
        result = collect_menu_snapshot(action, allow_mixed_readonly=allow_mixed, wait_seconds=wait_seconds)
        path = save_menu_snapshot(result)
        _print_result(result.to_dict())
        print(f"saved: {path}")
        if not result.ok:
            raise SystemExit(1)
        return

    print("usage: python scripts/cdp_client.py smartstore menus catalog")
    print("       python scripts/cdp_client.py smartstore menus snapshot --menu=<id>")


def _cmd_advanced(sub: str | None, args: list[str]) -> None:
    from scripts.smartstore.advanced_tools import (
        analyze_all_menus,
        analyze_menu,
        build_advanced_catalog,
        save_advanced_all,
        save_advanced_report,
    )

    action = sub or "catalog"
    allow_mixed = _flag(args, "--allow-mixed-readonly")
    wait_seconds = float(_option_value(args, "--wait=") or 6.0)
    if action in ("catalog", "profiles", "tools"):
        _print_result(build_advanced_catalog())
        return
    if action in ("all", "analyze-all"):
        payload = analyze_all_menus(allow_mixed_readonly=allow_mixed, wait_seconds=wait_seconds)
        path = save_advanced_all(payload)
        _print_result(payload)
        print(f"saved: {path}")
        if payload.get("ok_count") != payload.get("menu_count"):
            raise SystemExit(1)
        return
    from scripts.smartstore.menu_tools import list_menu_specs

    menu_ids = {spec.menu_id for spec in list_menu_specs()}
    menu_id = _option_value(args, "--menu=") or (action if action in menu_ids else "")
    if not menu_id:
        menu_id = next((arg for arg in args if not str(arg).startswith("--")), action)
    result = analyze_menu(menu_id, allow_mixed_readonly=allow_mixed, wait_seconds=wait_seconds)
    path = save_advanced_report(result)
    _print_result(result.to_dict())
    print(f"saved: {path}")
    if not result.ok:
        raise SystemExit(1)


def _cmd_draft_fill(sub: str | None, args: list[str]) -> None:
    from scripts.smartstore.draft_fill import fill_product_draft, load_product_data, save_draft_fill_report

    workflow = sub or "product"
    allow_mixed = _flag(args, "--allow-mixed-readonly")
    wait_seconds = float(_option_value(args, "--wait=") or 12.0)
    data_path = _option_value(args, "--data=") or _option_value(args, "--file=")
    if workflow not in ("product", "product-draft", "sample-product"):
        raise SystemExit("usage: python scripts/cdp_client.py smartstore draft-fill product --data=<utf8-json-file>")
    if workflow == "sample-product":
        data = load_product_data(None)
    else:
        if not data_path:
            raise SystemExit(
                "smartstore draft-fill product requires --data=<utf8-json-file>. "
                "Use sample-product explicitly for generated test data."
            )
        _read_json_arg([f"--data={data_path}"])
        data = load_product_data(data_path)
    result = fill_product_draft(data, allow_mixed_readonly=allow_mixed, wait_seconds=wait_seconds)
    path = save_draft_fill_report(result)
    _print_result(result.to_dict())
    print(f"saved: {path}")
    if not result.ok:
        raise SystemExit(1)


def _cmd_product_register(sub: str | None, args: list[str]) -> None:
    from scripts.smartstore.product_register import build_product_register_pipeline

    action = sub or "pipeline"
    if action not in ("pipeline", "plan", "gates", "modules", None, ""):
        raise SystemExit("usage: python scripts/cdp_client.py smartstore product-register pipeline")
    payload = build_product_register_pipeline()
    _print_result(payload)


def _cmd_approved(sub: str | None, args: list[str]) -> None:
    from scripts.smartstore.approved_product_workflow import (
        approved_both_test_product_cycle,
        approved_cleanup_product,
        approved_save_product,
        approved_test_product_cycle,
        save_approved_product_report,
    )

    action = sub or "save-product"
    allow_mixed = _flag(args, "--allow-mixed-readonly")
    approved = _flag(args, "--approved")
    confirm = _option_value(args, "--confirm=") or ""
    cleanup = _flag(args, "--cleanup") or _flag(args, "--delete-after")
    wait_seconds = float(_option_value(args, "--wait=") or 10.0)
    if action in ("save-product", "product-save", "publish-product"):
        result = approved_save_product(
            approved=approved,
            confirm=confirm,
            allow_mixed_readonly=allow_mixed,
            cleanup=cleanup,
            wait_seconds=wait_seconds,
        )
    elif action in ("test-cycle", "both-test-cycle"):
        payload = approved_both_test_product_cycle(
            approved=approved,
            confirm=confirm,
            allow_mixed_readonly=allow_mixed,
            cleanup=cleanup,
            wait_seconds=wait_seconds,
        )
        from pathlib import Path
        out = Path("data/smartstore_approved_product_latest.json")
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _print_result(payload)
        print(f"saved: {out.resolve()}")
        if not payload.get("ok"):
            raise SystemExit(1)
        return
    elif action in ("test-individual", "individual-test-cycle"):
        result = approved_test_product_cycle(
            product_type="individual",
            approved=approved,
            confirm=confirm,
            allow_mixed_readonly=allow_mixed,
            cleanup=cleanup,
            wait_seconds=wait_seconds,
        )
    elif action in ("test-group", "group-test-cycle"):
        result = approved_test_product_cycle(
            product_type="group",
            approved=approved,
            confirm=confirm,
            allow_mixed_readonly=allow_mixed,
            cleanup=cleanup,
            wait_seconds=wait_seconds,
        )
    elif action in ("cleanup-product", "delete-product"):
        product_name = _option_value(args, "--name=") or _option_value(args, "--product-name=") or ""
        if not product_name:
            raise SystemExit("approved cleanup-product requires --name=<test product name>")
        result = approved_cleanup_product(
            product_name=product_name,
            approved=approved,
            confirm=confirm,
            allow_mixed_readonly=allow_mixed,
            wait_seconds=wait_seconds,
        )
    else:
        raise SystemExit("usage: smartstore approved save-product --approved --confirm=SMARTSTORE_APPROVED_SUBMIT [--cleanup]")
    path = save_approved_product_report(result)
    _print_result(result.to_dict())
    print(f"saved: {path}")
    if not result.ok:
        raise SystemExit(1)


def _cmd_login_watch(args: list[str]) -> None:
    from scripts.smartstore.live_probe import watch_login_and_save

    allow_mixed = _flag(args, "--allow-mixed-readonly")
    timeout_seconds = int(_option_value(args, "--timeout=") or 300)
    interval_seconds = float(_option_value(args, "--interval=") or 1.0)
    result = watch_login_and_save(
        allow_mixed_readonly=allow_mixed,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
    )
    _print_result(result.to_dict())
    if not result.ok:
        raise SystemExit(1)


def _print_help() -> None:
    print(
        """SmartStore usage:
  python scripts/cdp_client.py smartstore actions catalog
  python scripts/cdp_client.py smartstore prepare product --data=<json> [--dry-run]
  python scripts/cdp_client.py smartstore submit product --data=<json> --dry-run --approved --confirm=SMARTSTORE_APPROVED_SUBMIT
  python scripts/cdp_client.py smartstore product list --live-ok
  python scripts/cdp_client.py smartstore order new --live-ok
  python scripts/cdp_client.py smartstore inventory --live-ok
  python scripts/cdp_client.py smartstore seo
  python scripts/cdp_client.py smartstore ai <review-text>
  python scripts/cdp_client.py smartstore competitor <keyword>
  python scripts/cdp_client.py smartstore csv <file>
  python scripts/cdp_client.py smartstore analytics
  python scripts/cdp_client.py smartstore live-probe --allow-mixed-readonly
  python scripts/cdp_client.py smartstore page-tools --allow-mixed-readonly
  python scripts/cdp_client.py smartstore page-functions
  python scripts/cdp_client.py smartstore dashboard --allow-mixed-readonly
  python scripts/cdp_client.py smartstore menus catalog
  python scripts/cdp_client.py smartstore menus snapshot --menu=product
  python scripts/cdp_client.py smartstore menus snapshot-all
  python scripts/cdp_client.py smartstore advanced product
  python scripts/cdp_client.py smartstore advanced all
  python scripts/cdp_client.py smartstore draft-fill product
  python scripts/cdp_client.py smartstore login-watch --timeout=300"""
    )


def _print_result(result) -> None:
    if isinstance(result, dict):
        print(json.dumps(result, ensure_ascii=False, indent=2)[:1000])
    else:
        print(result)
