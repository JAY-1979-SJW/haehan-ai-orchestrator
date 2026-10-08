"""네이버 페이/톡/장소/스마트스토어 명령 핸들러"""

from __future__ import annotations

from typing import Any

from scripts.common.gate import check as gate_check

from scripts.naver.common.router_common import _flag, _int_option, _option_value, _print_saved, _save_latest


def _cmd_pay(sub: str, args: list[str]) -> None:
    from datetime import datetime

    from scripts.naver.pay import NaverPay
    from scripts.browser.cdp.connection import get_page

    gate_check("scan_page")
    pay = NaverPay(get_page())
    if sub in ("orders", "order", "list"):
        limit = _int_option(args, "--limit=", 30)
        orders = pay.list_orders(limit=limit)
        out: dict[str, Any] = {"generated_at": datetime.now().isoformat(timespec="seconds"), "orders": orders}
        _print_saved(out, _save_latest("naver_pay_orders_latest.json", out))
    elif sub in ("points", "point", "balance"):
        points = pay.points()
        out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "points": points}
        _print_saved(out, _save_latest("naver_pay_points_latest.json", out))
    else:
        print("usage: python scripts/entry/cdp_cli.py naver pay [orders|points] [--limit=30]")


def _cmd_talk(sub: str, args: list[str]) -> None:
    from datetime import datetime

    from scripts.naver.common.talk import NaverTalk
    from scripts.browser.cdp.connection import get_page

    if sub in ("list", "chats"):
        gate_check("scan_page")
        limit = _int_option(args, "--limit=", 30)
        chats = NaverTalk(get_page()).list_chats(limit=limit)
        out: dict[str, Any] = {"generated_at": datetime.now().isoformat(timespec="seconds"), "chats": chats}
        _print_saved(out, _save_latest("naver_talk_chats_latest.json", out))
        return

    if sub not in ("send", "message"):
        print(
            "usage: python scripts/entry/cdp_cli.py naver talk [list|send] --partner=NAME --message=TEXT [--dry-run|--execute --approved --confirm=NAVER_APPROVED_SEND]"
        )
        return

    partner = _option_value(args, "--partner=") or _option_value(args, "--to=") or ""
    message = _option_value(args, "--message=") or _option_value(args, "--body=") or ""
    dry_run = _flag(args, "--dry-run") or not _flag(args, "--execute")
    approved = _flag(args, "--approved")
    confirm = _option_value(args, "--confirm=") or ""
    if not partner or not message:
        raise SystemExit("talk send requires --partner=NAME --message=TEXT")
    if not dry_run and (not approved or confirm != "NAVER_APPROVED_SEND"):
        raise SystemExit("talk send execute requires --approved --confirm=NAVER_APPROVED_SEND")

    plan: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "talk_send",
        "partner": partner,
        "message_length": len(message),
        "dry_run": dry_run,
        "approval_required": True,
    }
    if dry_run:
        out = {**plan, "ok": True, "note": "dry-run only; no browser write"}
        _print_saved(out, _save_latest("naver_talk_send_latest.json", out))
        return

    gate_check("naver_mail_send", force=approved, service="naver_talk", partner=partner)
    result = NaverTalk(get_page()).send_message(partner, message, confirm=True, approval_confirm=confirm)
    out = {**plan, "ok": bool(result.get("ok")), "result": result}
    _print_saved(out, _save_latest("naver_talk_send_latest.json", out))


def _cmd_place(sub: str, args: list[str]) -> None:
    from datetime import datetime

    from scripts.naver.common.place import NaverPlace
    from scripts.browser.cdp.connection import get_page

    gate_check("scan_page")
    place = NaverPlace(get_page())
    if sub in ("list", "places"):
        places = place.list_places()
        out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "places": places}
        _print_saved(out, _save_latest("naver_place_list_latest.json", out))
    elif sub in ("reviews", "review"):
        limit = _int_option(args, "--limit=", 30)
        reviews = place.reviews(limit=limit)
        out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "reviews": reviews}
        _print_saved(out, _save_latest("naver_place_reviews_latest.json", out))
    else:
        print("usage: python scripts/entry/cdp_cli.py naver place [list|reviews] [--limit=30]")


def _cmd_smartstore(sub: str, args: list[str]) -> None:
    from scripts.naver.smartstore.api.router import run_smartstore

    run_smartstore(sub or "actions", args[0] if args else None, args[1:] if args else [])
