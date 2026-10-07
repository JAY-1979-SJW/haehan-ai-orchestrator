"""SmartStore service router."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.common.gate import check as gate_check
from scripts.common.logger import get_logger
from scripts.naver.common.live_safety import before_live_navigation, ensure_page_safe
from scripts.naver.smartstore.api.actions import APPROVAL_CONFIRM_TEXT

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
          ai | competitor | csv | analytics | session-check
    """
    handlers = {
        "actions": lambda: _cmd_actions(sub or "catalog", args),
        "action-catalog": lambda: _cmd_actions(sub or "catalog", args),
        "prepare": lambda: _cmd_prepare(sub or "product", args),
        "submit": lambda: _cmd_submit(sub or "product", args),
        "product": lambda: _cmd_product(sub, args),
        "order": lambda: _cmd_order(sub, args),
        "inventory": lambda: _cmd_inventory(sub, args),
        "seo": lambda: _cmd_seo(sub, args),
        "ai": lambda: _cmd_ai(sub, args),
        "competitor": lambda: _cmd_competitor(sub, args),
        "csv": lambda: _cmd_csv(sub, args),
        "analytics": lambda: _cmd_analytics(sub, args),
        "session-check": _cmd_session_check,
    }
    handlers.get(task or "help", _print_help)()


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
    from scripts.browser.cdp.connection import get_page

    page = get_page()
    ensure_page_safe(page, site="smartstore", workflow=workflow, phase="before_action")
    return page


def _read_json_arg(args: list[str]) -> tuple[dict, str]:
    path = _option_value(args, "--data=") or _option_value(args, "--file=")
    if not path:
        sample = Path("data/sample_product_data.json")
        raise SystemExit(f"product data required: --data=<json>; sample={sample}")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("product data JSON must be an object")
    return data, path


def _cmd_actions(sub: str | None, args: list[str]) -> None:
    from scripts.naver.smartstore.api.actions import (
        build_action_catalog,
        print_action_catalog_summary,
        save_action_catalog,
    )

    if sub not in ("catalog", "actions", "list", None, ""):
        print("usage: python scripts/entry/cdp_cli.py smartstore actions catalog")
        return
    gate_check("scan_page")
    catalog = build_action_catalog()
    path = save_action_catalog(catalog)
    print_action_catalog_summary(catalog, path)


def _cmd_prepare(sub: str | None, args: list[str]) -> None:
    from scripts.naver.smartstore.actions import build_prepare_plan, print_prepare_plan_summary, save_prepare_plan

    if sub not in ("product", "register", "general", "group", None, ""):
        print(
            "usage: python scripts/entry/cdp_cli.py smartstore prepare product "
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

    from scripts.naver.smartstore import NaverSmartStore
    from scripts.naver.smartstore.actions import save_submit_record
    page = _live_page(args, workflow="product_prepare")
    ss = NaverSmartStore(page)
    if product_type == "general":
        result = ss.register_general_product(data, save_after=save_after, require_confirm=True)
    else:
        result = ss.register_product(data, save_after=save_after, require_confirm=True)
    record = {**plan, "ok": bool(result.get("ok")), "prepared": bool(result.get("ok")), "result": result}
    out = save_submit_record(record)
    _print_result(record)
    print(f"saved: {out}")


def _cmd_submit(sub: str | None, args: list[str]) -> None:
    from scripts.naver.smartstore.actions import build_submit_plan, load_product_data, save_submit_record

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

    from scripts.naver.smartstore import NaverSmartStore
    page = _live_page(args, workflow="product_submit")
    ss = NaverSmartStore(page)
    if action_id == "product.general.save":
        result = ss.register_general_product(data, save_after=True, require_confirm=False)
    elif action_id == "product.group.save":
        result = ss.register_product(data, save_after=True, require_confirm=False)
    elif action_id == "product.bulk.save":
        products = data.get("products")
        if not isinstance(products, list):
            raise SystemExit("bulk submit data requires products list")
        result = ss.register_bulk(products, product_type=product_type, save_after=True, require_confirm=False)
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
        from scripts.naver.smartstore import NaverSmartStore
        ss = NaverSmartStore(_live_page(args, workflow="product_list"))
        result = ss.list_products()
        _print_result(result)
    elif action == "register":
        _cmd_prepare("product", args)
    else:
        print(f"unknown product subcommand: {action}")


def _cmd_order(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    action = sub or "new"
    print(f"[smartstore] order {action}")
    from scripts.naver.smartstore import NaverSmartStore
    ss = NaverSmartStore(_live_page(args, workflow="order"))
    result = ss.list_orders()
    _print_result(result)


def _cmd_inventory(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    print("[smartstore] inventory")
    from scripts.naver.smartstore import NaverSmartStore
    ss = NaverSmartStore(_live_page(args, workflow="inventory"))
    result = ss.list_products()
    _print_result(result)


def _cmd_seo(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    print("[smartstore] seo")
    from scripts.naver.smartstore import NaverSmartStore
    ss = NaverSmartStore(_live_page(args, workflow="seo"))
    result = ss.store_info()
    _print_result(result)


def _cmd_ai(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    print("[smartstore] ai review reply")
    from scripts.naver.smartstore import NaverSmartStore
    ss = NaverSmartStore(_live_page(args, workflow="ai_review_reply"))
    result = ss.list_reviews()
    _print_result(result)


def _cmd_competitor(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    keyword = " ".join(args) or sub or ""
    print(f"[smartstore] competitor: {keyword or '(keyword required)'}")
    from scripts.naver.smartstore import NaverSmartStore
    ss = NaverSmartStore(_live_page(args, workflow="competitor"))
    result = ss.stats()
    _print_result(result)


def _cmd_csv(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    file_path = args[0] if args else sub or ""
    if not file_path:
        print("usage: smartstore csv <file-path>")
        return
    print(f"[smartstore] csv import: {file_path}")
    from scripts.naver.smartstore import NaverSmartStore
    ss = NaverSmartStore(_live_page(args, workflow="csv_import"))
    result = ss.list_products()
    _print_result(result)


def _cmd_analytics(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    print("[smartstore] analytics today")
    from scripts.naver.smartstore import NaverSmartStore
    ss = NaverSmartStore(_live_page(args, workflow="analytics"))
    result = ss.stats()
    _print_result(result)


def _cmd_session_check() -> None:
    from scripts.site_engine.site_base import check_session

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


def _print_help() -> None:
    print(
        """SmartStore usage:
  python scripts/entry/cdp_cli.py smartstore actions catalog
  python scripts/entry/cdp_cli.py smartstore prepare product --data=<json> [--dry-run]
  python scripts/entry/cdp_cli.py smartstore submit product --data=<json> --dry-run --approved --confirm=SMARTSTORE_APPROVED_SUBMIT
  python scripts/entry/cdp_cli.py smartstore product list --live-ok
  python scripts/entry/cdp_cli.py smartstore order new --live-ok
  python scripts/entry/cdp_cli.py smartstore inventory --live-ok
  python scripts/entry/cdp_cli.py smartstore seo
  python scripts/entry/cdp_cli.py smartstore ai <review-text>
  python scripts/entry/cdp_cli.py smartstore competitor <keyword>
  python scripts/entry/cdp_cli.py smartstore csv <file>
  python scripts/entry/cdp_cli.py smartstore analytics"""
    )


def _print_result(result) -> None:
    if isinstance(result, dict):
        print(json.dumps(result, ensure_ascii=False, indent=2)[:1000])
    else:
        print(result)
