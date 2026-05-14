"""네이버 서비스 라우터"""
from __future__ import annotations

import json

from . import blog, mail
from .base import check_session
from scripts.gate import check as gate_check
from scripts.naver.live_safety import before_live_navigation

__status__ = {
    "tasks": {
        "blog write":   "done",
        "blog publish": "done",
        "mail inbox":   "done",
        "mail compose": "done",
        "mail send":    "done",
        "content explore": "done",
        "content actions": "done",
        "company seo": "done",
        "company seo assets": "done",
        "company seo ownership": "done",
        "company seo exposure": "done",
        "company seo submit-plan": "done",
        "company seo monitor": "done",
        "developers entrypoints": "done",
        "shopping competitors": "done",
        "excel report": "done",
        "cafe list": "done",
        "cafe posts": "done",
        "cafe read": "done",
        "cafe write": "done",
        "calendar list/add": "done",
        "mybox list/search/upload": "done",
        "pay orders/points": "done",
        "talk list/send": "done",
        "place list/reviews": "done",
        "smartstore alias": "done",
        "service catalog": "done",
        "login":        "done",
        "session-check":"done",
    },
    "note": "블로그 글쓰기·발행, 메일 수신/발송 자동화 완성",
}


def run_naver(task: str, sub: str, args: list[str]) -> None:
    """네이버 서비스 라우팅.

    task: blog | mail | session-check | login
    sub: write / inbox / compose 등 하위 명령
    """
    match task:
        case "blog":
            _gate_blog(sub)
            blog.run(sub or "write", args)
        case "mail":
            _gate_mail(sub)
            mail.run(sub or "inbox", args)
        case "content":
            _cmd_content(sub or "explore", args)
        case "seo":
            _cmd_seo(sub or "plan", args)
        case "developers":
            _cmd_developers(sub or "entrypoints", args)
        case "shopping":
            _cmd_shopping(sub or "competitors", args)
        case "excel" | "report":
            _cmd_excel(sub or "report", args)
        case "cafe":
            _cmd_cafe(sub or "list", args)
        case "calendar":
            _cmd_calendar(sub or "list", args)
        case "mybox":
            _cmd_mybox(sub or "list", args)
        case "pay":
            _cmd_pay(sub or "orders", args)
        case "talk":
            _cmd_talk(sub or "list", args)
        case "place":
            _cmd_place(sub or "list", args)
        case "smartstore":
            _cmd_smartstore(sub or "actions", args)
        case "catalog" | "actions" | "index":
            _cmd_catalog()
        case "session-check":
            _cmd_session_check()
        case "login":
            gate_check("wait_login", risk="notify")
            _cmd_login()
        case _:
            print(f"  [오류] 알 수 없는 작업: {task}")


def _gate_blog(sub: str) -> None:
    if sub in ("publish", "send"):
        gate_check("blog_publish")       # APPROVE — 외부 공개
    elif sub in ("write", "draft", None, ""):
        gate_check("write_blog_post")    # APPROVE — 비가역 초안 작성
    else:
        gate_check("goto")               # AUTO — 읽기


def _gate_mail(sub: str) -> None:
    if sub in ("send", "compose"):
        gate_check("naver_mail_send")    # APPROVE — 외부 발송
    else:
        gate_check("goto")               # AUTO — 수신함 조회


def _option_value(args: list[str], prefix: str) -> str | None:
    for arg in args:
        text = str(arg)
        if text.startswith(prefix):
            return text.split("=", 1)[1]
    return None


def _option_phrase(args: list[str], prefix: str) -> str | None:
    for idx, arg in enumerate(args):
        text = str(arg)
        if not text.startswith(prefix):
            continue
        parts = [text.split("=", 1)[1]]
        for rest in args[idx + 1:]:
            rest_text = str(rest)
            if rest_text.startswith("--"):
                break
            parts.append(rest_text)
        return " ".join(part for part in parts if part).strip()
    return None


def _flag(args: list[str], name: str) -> bool:
    return name in args


def _int_option(args: list[str], prefix: str, default: int) -> int:
    value = _option_value(args, prefix)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"{prefix}<int> required") from exc


def _save_latest(name: str, payload: dict) -> str:
    from pathlib import Path

    path = Path("data") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _print_saved(payload: dict, path: str) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved: {path}")


def _parse_datetime_arg(value: str, field: str):
    from datetime import datetime

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"{field} must be ISO datetime, example: 2026-05-13T15:00:00") from exc


def _cmd_content(sub: str, args: list[str]) -> None:
    from scripts.web_connector import get_page
    from scripts.naver.content import (
        build_action_catalog,
        print_action_summary,
        print_surface_summary,
        save_action_catalog,
        save_surface_report,
        scan_target,
        select_targets,
    )

    name = args[0] if args and not str(args[0]).startswith("--") else "all"
    limit = int(_option_value(args, "--limit=") or "80")

    if sub in ("explore", "scan", "surfaces"):
        before_live_navigation(
            args,
            site="naver",
            workflow="content_explore",
            multi_target=(name == "all"),
        )
        gate_check("scan_page")
        page = get_page()
        results = [scan_target(page, key, target, limit=limit) for key, target in select_targets(name).items()]
        path = save_surface_report(results)
        print_surface_summary(results, path)
    elif sub in ("actions", "action-catalog"):
        gate_check("scan_page")
        catalog = build_action_catalog()
        if name and name != "all":
            catalog["targets"] = [target for target in catalog.get("targets", []) if target.get("key") == name]
            if not catalog["targets"]:
                raise KeyError(f"unknown Naver content target: {name}")
        path = save_action_catalog(catalog)
        print_action_summary(catalog, path)
    else:
        print("usage: python scripts/cdp_client.py naver content [explore|actions] [blog|blog_admin|cafe|all] [--limit=80]")


def _cmd_seo(sub: str, args: list[str]) -> None:
    from pathlib import Path

    from scripts.naver.company_seo import (
        analyze_html,
        audit_site_assets,
        build_exposure_plan,
        build_company_seo_plan,
        build_entrypoints,
        build_monitor_report,
        build_ownership_plan,
        build_submit_plan,
        print_assets_summary,
        print_diagnosis_summary,
        print_plan_summary,
        save_assets,
        save_diagnosis,
        save_entrypoints,
        save_exposure_plan,
        save_monitor_report,
        save_ownership_plan,
        save_plan,
        save_submit_plan,
    )

    site_url = _option_value(args, "--site=") or _option_value(args, "--url=") or "https://haehan-ai.kr"
    company = _option_value(args, "--company=") or "haehan-ai"
    keywords_raw = _option_value(args, "--keywords=") or ""
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]

    if sub in ("entrypoints", "where", "links"):
        gate_check("scan_page")
        path = save_entrypoints()
        payload = build_entrypoints()
        _print_saved(payload, str(path))
        return

    if sub in ("plan", "prepare", "searchadvisor"):
        gate_check("scan_page")
        plan = build_company_seo_plan(site_url, company_name=company, keywords=keywords)
        path = save_plan(plan)
        print_plan_summary(plan, path)
        return

    if sub in ("assets", "asset-audit", "live-audit", "full-audit"):
        gate_check("scan_page")
        assets = audit_site_assets(site_url)
        path = save_assets(assets)
        print_assets_summary(assets, path)
        save_diagnosis(assets["diagnosis"])
        return

    if sub in ("ownership", "verify-plan", "verification"):
        gate_check("scan_page")
        plan = build_ownership_plan(site_url, company_name=company)
        path = save_ownership_plan(plan)
        _print_saved(plan, str(path))
        return

    if sub in ("exposure", "search-status", "index-status"):
        gate_check("scan_page")
        plan = build_exposure_plan(site_url, keywords=keywords)
        path = save_exposure_plan(plan)
        _print_saved(plan, str(path))
        return

    if sub in ("submit-plan", "submission-plan", "index-request-plan"):
        gate_check("scan_page")
        plan = build_submit_plan(site_url, keywords=keywords, company_name=company)
        path = save_submit_plan(plan)
        _print_saved(plan, str(path))
        return

    if sub in ("monitor", "report-status"):
        gate_check("scan_page")
        assets = audit_site_assets(site_url)
        exposure = build_exposure_plan(site_url, keywords=keywords)
        submit_plan = build_submit_plan(site_url, keywords=keywords, company_name=company)
        save_assets(assets)
        save_exposure_plan(exposure)
        save_submit_plan(submit_plan)
        report = build_monitor_report(site_url, assets=assets, exposure=exposure, submit_plan=submit_plan)
        path = save_monitor_report(report)
        _print_saved(report, str(path))
        save_diagnosis(assets["diagnosis"])
        return

    if sub in ("full", "all"):
        gate_check("scan_page")
        plan = build_company_seo_plan(site_url, company_name=company, keywords=keywords)
        assets = audit_site_assets(site_url)
        ownership = build_ownership_plan(site_url, company_name=company)
        exposure = build_exposure_plan(site_url, keywords=keywords)
        submit_plan = build_submit_plan(site_url, keywords=keywords, company_name=company)
        monitor = build_monitor_report(site_url, assets=assets, exposure=exposure, submit_plan=submit_plan)
        paths = {
            "plan": str(save_plan(plan)),
            "assets": str(save_assets(assets)),
            "diagnosis": str(save_diagnosis(assets["diagnosis"])),
            "ownership": str(save_ownership_plan(ownership)),
            "exposure": str(save_exposure_plan(exposure)),
            "submit_plan": str(save_submit_plan(submit_plan)),
            "monitor": str(save_monitor_report(monitor)),
        }
        _print_saved(
            {
                "workflow": "naver_company_seo_full",
                "site_url": site_url,
                "ok": True,
                "score": assets.get("score"),
                "monitor_status": monitor.get("status"),
                "paths": paths,
            },
            _save_latest("naver_company_seo_full_latest.json", {"paths": paths, "score": assets.get("score")}),
        )
        return

    if sub in ("diagnose", "diagnosis", "audit"):
        html_path = _option_value(args, "--html=")
        if not html_path:
            assets = audit_site_assets(site_url)
            path = save_diagnosis(assets["diagnosis"])
            print_diagnosis_summary(assets["diagnosis"], path)
            save_assets(assets)
            return
        html = Path(html_path).read_text(encoding="utf-8")
        diagnosis = analyze_html(site_url, html)
        path = save_diagnosis(diagnosis)
        print_diagnosis_summary(diagnosis, path)
        return

    if sub in ("submit", "register"):
        approved = _flag(args, "--approved")
        confirm = _option_value(args, "--confirm=") or ""
        if not approved or confirm != "NAVER_APPROVED_SEO_SUBMIT":
            raise SystemExit("seo submit requires --approved --confirm=NAVER_APPROVED_SEO_SUBMIT")
        gate_check("blog_publish", force=approved, service="naver_searchadvisor", site_url=site_url)
        plan = build_submit_plan(site_url, company_name=company, keywords=keywords)
        record = {
            **plan,
            "ok": False,
            "submit_executed": False,
            "reason": "Search Advisor submit is approval-gated; browser adapter must confirm visible form before final click",
        }
        _print_saved(record, _save_latest("naver_company_seo_submit_latest.json", record))
        return

    print("usage: python scripts/cdp_client.py naver seo [entrypoints|plan|assets|ownership|exposure|submit-plan|monitor|full|diagnose|submit] --site=https://haehan-ai.kr")


def _cmd_developers(sub: str, args: list[str]) -> None:
    from datetime import datetime

    from scripts.naver.company_seo import OFFICIAL_ENTRYPOINTS

    gate_check("scan_page")
    if sub not in ("entrypoints", "plan", "apps"):
        print("usage: python scripts/cdp_client.py naver developers [entrypoints|plan]")
        return
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "naver_developers_setup",
        "entrypoints": {
            "developers": OFFICIAL_ENTRYPOINTS["developers"],
            "developers_apps": OFFICIAL_ENTRYPOINTS["developers_apps"],
        },
        "api_use_cases": [
            {"id": "search_blog", "purpose": "public blog search monitoring", "state_change": False},
            {"id": "search_shop", "purpose": "shopping competitor monitoring", "state_change": False},
            {"id": "login", "purpose": "owned service login integration", "state_change": True},
        ],
        "approval_required_for": ["app_register", "api_scope_change", "credential_issue"],
        "credential_policy": "store credentials only through encrypted credential/env flow; never log raw Client Secret",
    }
    _print_saved(payload, _save_latest("naver_developers_plan_latest.json", payload))


def _cmd_shopping(sub: str, args: list[str]) -> None:
    from datetime import datetime

    from scripts.naver.company_seo import OFFICIAL_ENTRYPOINTS
    from scripts.naver.shopping_competitor import (
        collect_openapi_competitors,
        print_competitor_summary,
        save_competitor_report,
    )

    if sub in ("entrypoints", "where", "links"):
        gate_check("scan_page")
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "workflow": "naver_shopping_entrypoints",
            "entrypoints": {
                "shopping": {"label": "Naver Shopping", "url": "https://shopping.naver.com/"},
                "shopping_partner": OFFICIAL_ENTRYPOINTS["shopping_partner"],
                "smartstore": OFFICIAL_ENTRYPOINTS["smartstore"],
                "search_ad": OFFICIAL_ENTRYPOINTS["search_ad"],
            },
            "competitor_use": "use public shopping search/OpenAPI metadata for price, mall, brand, and category comparison",
            "blocked_actions": ["purchase", "cart", "review_write", "ad_budget_change"],
        }
        _print_saved(payload, _save_latest("naver_shopping_entrypoints_latest.json", payload))
        return

    if sub not in ("competitors", "competitor", "search"):
        print("usage: python scripts/cdp_client.py naver shopping competitors --query=KEYWORD [--display=20] [--my-price=N]")
        return

    gate_check("scan_page")
    query = _option_phrase(args, "--query=") or " ".join(a for a in args if not str(a).startswith("--"))
    if not query:
        raise SystemExit("shopping competitors requires --query=KEYWORD")
    display = _int_option(args, "--display=", 20)
    sort = _option_value(args, "--sort=") or "sim"
    my_price_raw = _option_value(args, "--my-price=")
    my_price = int(my_price_raw) if my_price_raw else None
    my_mall = _option_value(args, "--my-mall=") or ""
    report = collect_openapi_competitors(query, display=display, sort=sort, my_price=my_price, my_mall=my_mall)
    path = save_competitor_report(report)
    print_competitor_summary(report, path)


def _cmd_excel(sub: str, args: list[str]) -> None:
    from scripts.naver.excel_reports import build_excel_report, print_excel_summary

    if sub not in ("report", "build", "latest"):
        print("usage: python scripts/cdp_client.py naver excel report [--output=PATH]")
        return
    gate_check("file_write")
    output = _option_value(args, "--output=")
    result = build_excel_report(output=output)
    print_excel_summary(result)


def _cmd_cafe(sub: str, args: list[str]) -> None:
    from datetime import datetime
    from pathlib import Path

    from scripts.web_connector import get_page
    from scripts.naver.cafe import NaverCafe
    from scripts.naver.content import (
        APPROVAL_CONFIRM_TEXT,
        build_cafe_write_plan,
        save_cafe_submit_record,
        save_cafe_write_plan,
    )

    if sub in ("list", "cafes"):
        gate_check("scan_page")
        page = get_page()
        cafes = NaverCafe(page).open_my_cafes()
        out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "cafes": cafes}
        path = Path("data/naver_cafes_latest.json")
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"saved: {path}")
        return

    if sub in ("posts", "list-posts", "articles"):
        gate_check("scan_page")
        cafe_url = _option_value(args, "--cafe-url=") or (args[0] if args and not str(args[0]).startswith("--") else "")
        board_no = _option_value(args, "--board-no=") or _option_value(args, "--board=") or ""
        limit = _int_option(args, "--limit=", 30)
        if not cafe_url:
            raise SystemExit("cafe posts requires --cafe-url=URL [--board-no=N] [--limit=30]")
        page = get_page()
        posts = NaverCafe(page).list_posts(cafe_url=cafe_url, board_no=board_no, limit=limit)
        out = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "cafe_url": cafe_url,
            "board_no": board_no,
            "posts": posts,
        }
        _print_saved(out, _save_latest("naver_cafe_posts_latest.json", out))
        return

    if sub in ("read", "read-post", "post"):
        gate_check("scan_page")
        post_url = _option_value(args, "--post-url=") or _option_value(args, "--url=") or (
            args[0] if args and not str(args[0]).startswith("--") else ""
        )
        if not post_url:
            raise SystemExit("cafe read requires --post-url=URL")
        page = get_page()
        post = NaverCafe(page).read_post(post_url)
        out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "post_url": post_url, "post": post}
        _print_saved(out, _save_latest("naver_cafe_post_latest.json", out))
        return

    if sub not in ("write", "prepare-post", "publish"):
        print("usage: python scripts/cdp_client.py naver cafe [list|posts|read|write|publish] ...")
        return

    cafe_url = _option_value(args, "--cafe-url=") or ""
    board_no = _option_value(args, "--board-no=") or ""
    title = _option_value(args, "--title=") or ""
    body = _option_value(args, "--body=") or ""
    dry_run = "--dry-run" in args
    publish = sub == "publish" or "--publish" in args
    approved = "--approved" in args
    confirm = _option_value(args, "--confirm=") or ""
    approved_by = _option_value(args, "--approved-by=") or "operator"

    if not cafe_url or not board_no or not title:
        raise SystemExit("cafe write requires --cafe-url, --board-no, --title, and optional --body")
    if publish and (not approved or confirm != APPROVAL_CONFIRM_TEXT):
        raise SystemExit(f"cafe publish requires --approved --confirm={APPROVAL_CONFIRM_TEXT}")

    if publish:
        gate_check("blog_publish", force=approved, service="naver_cafe", cafe_url=cafe_url, board_no=board_no)
    else:
        gate_check("type_into", service="naver_cafe", cafe_url=cafe_url, board_no=board_no)

    plan = build_cafe_write_plan(
        cafe_url=cafe_url,
        board_no=board_no,
        title=title,
        body=body,
        publish=publish,
        approved_by=approved_by,
        dry_run=dry_run,
    )
    save_cafe_write_plan(plan)

    if dry_run:
        record = {**plan, "ok": True, "prepared": False, "published": False, "note": "dry-run only; no browser write"}
    else:
        page = get_page()
        result = NaverCafe(page).write_post(cafe_url=cafe_url, board_no=board_no, title=title, body=body, send=publish)
        record = {
            **plan,
            "ok": bool(result.get("ok")),
            "prepared": bool(result.get("ok")),
            "published": result.get("mode") == "published",
            "result": result,
        }
    path = save_cafe_submit_record(record)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    print(f"saved: {path}")


def _cmd_calendar(sub: str, args: list[str]) -> None:
    from datetime import datetime

    from scripts.web_connector import get_page
    from scripts.naver.calendar import NaverCalendar

    if sub in ("list", "events"):
        gate_check("scan_page")
        events = NaverCalendar(get_page()).list_events()
        out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "events": events}
        _print_saved(out, _save_latest("naver_calendar_events_latest.json", out))
        return

    if sub not in ("add", "prepare", "save"):
        print("usage: python scripts/cdp_client.py naver calendar [list|add] --title=TITLE --start=ISO [--end=ISO] [--dry-run|--execute] [--save --approved --confirm=NAVER_APPROVED_SAVE]")
        return

    title = _option_value(args, "--title=") or ""
    start_raw = _option_value(args, "--start=") or ""
    end_raw = _option_value(args, "--end=") or ""
    location = _option_value(args, "--location=") or ""
    memo = _option_value(args, "--memo=") or ""
    save = sub == "save" or _flag(args, "--save")
    dry_run = _flag(args, "--dry-run") or not _flag(args, "--execute")
    approved = _flag(args, "--approved")
    confirm = _option_value(args, "--confirm=") or ""

    if not title or not start_raw:
        raise SystemExit("calendar add requires --title=TITLE --start=ISO")
    if save and (not approved or confirm != "NAVER_APPROVED_SAVE"):
        raise SystemExit("calendar save requires --approved --confirm=NAVER_APPROVED_SAVE")

    plan = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "calendar_add",
        "title": title,
        "start": start_raw,
        "end": end_raw,
        "location": location,
        "memo_present": bool(memo),
        "dry_run": dry_run,
        "save_requested": save,
        "approval_required": save,
    }
    if dry_run:
        out = {**plan, "ok": True, "note": "dry-run only; no browser write"}
        _print_saved(out, _save_latest("naver_calendar_add_latest.json", out))
        return

    gate_check("blog_publish" if save else "type_into", force=approved, service="naver_calendar")
    result = NaverCalendar(get_page()).add_event(
        title=title,
        start=_parse_datetime_arg(start_raw, "--start"),
        end=_parse_datetime_arg(end_raw, "--end") if end_raw else None,
        location=location,
        memo=memo,
        confirm=save,
    )
    out = {**plan, "ok": bool(result.get("ok")), "result": result}
    _print_saved(out, _save_latest("naver_calendar_add_latest.json", out))


def _cmd_mybox(sub: str, args: list[str]) -> None:
    from datetime import datetime
    from pathlib import Path

    from scripts.web_connector import get_page
    from scripts.naver.mybox import NaverMyBox

    if sub in ("list", "files"):
        gate_check("scan_page")
        limit = _int_option(args, "--limit=", 50)
        items = NaverMyBox(get_page()).list_files(limit=limit)
        out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "files": items}
        _print_saved(out, _save_latest("naver_mybox_files_latest.json", out))
        return

    if sub == "search":
        gate_check("scan_page")
        query = _option_value(args, "--query=") or " ".join(a for a in args if not str(a).startswith("--"))
        if not query:
            raise SystemExit("mybox search requires --query=TEXT")
        items = NaverMyBox(get_page()).search(query)
        out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "query": query, "files": items}
        _print_saved(out, _save_latest("naver_mybox_search_latest.json", out))
        return

    if sub != "upload":
        print("usage: python scripts/cdp_client.py naver mybox [list|search|upload] ...")
        return

    local_path = _option_value(args, "--file=") or _option_value(args, "--path=") or (
        args[0] if args and not str(args[0]).startswith("--") else ""
    )
    dry_run = _flag(args, "--dry-run") or not _flag(args, "--execute")
    approved = _flag(args, "--approved")
    confirm = _option_value(args, "--confirm=") or ""
    if not local_path:
        raise SystemExit("mybox upload requires --file=PATH")
    if not Path(local_path).exists():
        raise SystemExit(f"upload file not found: {local_path}")
    if not dry_run and (not approved or confirm != "NAVER_APPROVED_UPLOAD"):
        raise SystemExit("mybox upload execute requires --approved --confirm=NAVER_APPROVED_UPLOAD")

    plan = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "mybox_upload",
        "file_name": Path(local_path).name,
        "file_size": Path(local_path).stat().st_size,
        "dry_run": dry_run,
        "approval_required": True,
    }
    if dry_run:
        out = {**plan, "ok": True, "note": "dry-run only; no browser upload"}
        _print_saved(out, _save_latest("naver_mybox_upload_latest.json", out))
        return

    gate_check("blog_publish", force=approved, service="naver_mybox", file=Path(local_path).name)
    result = NaverMyBox(get_page()).upload(local_path)
    out = {**plan, "ok": bool(result.get("ok")), "result": result}
    _print_saved(out, _save_latest("naver_mybox_upload_latest.json", out))


def _cmd_pay(sub: str, args: list[str]) -> None:
    from datetime import datetime

    from scripts.web_connector import get_page
    from scripts.naver.pay import NaverPay

    gate_check("scan_page")
    pay = NaverPay(get_page())
    if sub in ("orders", "order", "list"):
        limit = _int_option(args, "--limit=", 30)
        orders = pay.list_orders(limit=limit)
        out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "orders": orders}
        _print_saved(out, _save_latest("naver_pay_orders_latest.json", out))
    elif sub in ("points", "point", "balance"):
        points = pay.points()
        out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "points": points}
        _print_saved(out, _save_latest("naver_pay_points_latest.json", out))
    else:
        print("usage: python scripts/cdp_client.py naver pay [orders|points] [--limit=30]")


def _cmd_talk(sub: str, args: list[str]) -> None:
    from datetime import datetime

    from scripts.web_connector import get_page
    from scripts.naver.talk import NaverTalk

    if sub in ("list", "chats"):
        gate_check("scan_page")
        limit = _int_option(args, "--limit=", 30)
        chats = NaverTalk(get_page()).list_chats(limit=limit)
        out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "chats": chats}
        _print_saved(out, _save_latest("naver_talk_chats_latest.json", out))
        return

    if sub not in ("send", "message"):
        print("usage: python scripts/cdp_client.py naver talk [list|send] --partner=NAME --message=TEXT [--dry-run|--execute --approved --confirm=NAVER_APPROVED_SEND]")
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

    plan = {
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
    result = NaverTalk(get_page()).send_message(partner, message, confirm=True)
    out = {**plan, "ok": bool(result.get("ok")), "result": result}
    _print_saved(out, _save_latest("naver_talk_send_latest.json", out))


def _cmd_place(sub: str, args: list[str]) -> None:
    from datetime import datetime

    from scripts.web_connector import get_page
    from scripts.naver.place import NaverPlace

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
        print("usage: python scripts/cdp_client.py naver place [list|reviews] [--limit=30]")


def _cmd_smartstore(sub: str, args: list[str]) -> None:
    from scripts.smartstore.router import run_smartstore

    run_smartstore(sub or "actions", args[0] if args else None, args[1:] if args else [])


def _cmd_catalog() -> None:
    from scripts.naver.service_catalog import build_catalog, print_catalog_summary, save_catalog

    gate_check("scan_page")
    catalog = build_catalog()
    path = save_catalog(catalog)
    print_catalog_summary(catalog, path)


def _cmd_session_check() -> None:
    print("=" * 60)
    print("네이버 세션 확인")
    print("=" * 60)
    result = check_session()

    if result["error"]:
        print(f"⚠  데몬 연결 실패: {result['error']}")
        print("  python scripts/cdp_daemon.py start")
    elif result["logged_in"]:
        print("✓ 로그인 상태 정상")
    else:
        print("✗ 로그인 필요")
        print("  python scripts/cdp_client.py naver login")

    print("=" * 60)


def _cmd_login() -> None:
    import sys
    from scripts.web_connector import browser_session
    from scripts.login_session import is_logged_in

    print("=" * 60)
    print("네이버 로그인")
    print("=" * 60)

    with browser_session() as page:
        page.goto("https://www.naver.com/", timeout=60000)

        if is_logged_in(page, "naver"):
            print("✓ 이미 로그인 상태입니다")
        elif sys.stdin.isatty():
            print("\n브라우저에서 네이버에 로그인하세요")
            input("👉 로그인 완료 후 Enter를 누르세요: ")
            if is_logged_in(page, "naver"):
                print("✓ 로그인 완료")
            else:
                print("⚠  로그인 확인 실패 — 다시 시도하세요")
        else:
            print("\n브라우저에 네이버 페이지를 열었습니다")
            print("브라우저에서 직접 로그인 후, 아래 명령으로 세션 확인:")
            print("  python scripts/cdp_client.py naver session-check")

    print("=" * 60)
