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
        "keyword tools": "done",
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
            if "--dry-run" not in [str(a) for a in args]:
                _gate_blog(sub)
            blog.run(sub or "write", args)
        case "mail":
            _gate_mail(sub)
            mail.run(sub or "inbox", args)
        case "blog-assets" | "blog-media":
            _cmd_blog_assets(sub or "plan", args)
        case "content":
            _cmd_content(sub or "explore", args)
        case "seo":
            _cmd_seo(sub or "plan", args)
        case "developers":
            _cmd_developers(sub or "entrypoints", args)
        case "shopping":
            _cmd_shopping(sub or "competitors", args)
        case "keyword-tools" | "keywords" | "keyword":
            _cmd_keyword_tools(sub or "catalog", args)
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
    if sub in ("send",):
        gate_check("naver_mail_send")    # APPROVE — 외부 발송
    elif sub in ("delete", "trash"):
        gate_check("naver_mail_delete")  # APPROVE — 메일 삭제/휴지통 이동
    elif sub in ("move", "archive", "spam", "label", "unlabel"):
        gate_check("naver_mail_move")    # APPROVE — 메일함/분류 상태 변경
    else:
        gate_check("goto")               # AUTO — 읽기/작성 준비


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


def _cmd_blog_assets(sub: str, args: list[str]) -> None:
    from pathlib import Path

    from scripts.naver.blog.assets import (
        analyze_blog_asset_images,
        analyze_blog_asset_images_with_pixels,
        collect_blog_asset_inventory,
        create_shopping_upload_manifest,
        build_blog_asset_plan,
        save_blog_image_analysis,
        save_blog_asset_plan,
        save_blog_pixel_analysis,
        save_shopping_upload_manifest,
    )

    blog_id = _option_value(args, "--blog-id=") or _option_value(args, "--blog=") or "gonobi"
    target_pages = _int_option(args, "--target=", 1000)

    if sub in ("plan", "prepare"):
        plan = build_blog_asset_plan(blog_id, target_pages=target_pages)
        path = save_blog_asset_plan(plan)
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        print(f"saved: {path}")
        return

    if sub in ("inventory", "collect", "scan"):
        gate_check("scan_page")
        port = _int_option(args, "--port=", 9232)
        max_index_pages = _int_option(args, "--max-index-pages=", 50)
        scroll_steps = _int_option(args, "--scroll-steps=", 10)
        wait_raw = _option_value(args, "--wait=") or "2.5"
        try:
            wait_seconds = float(wait_raw)
        except ValueError as exc:
            raise SystemExit("--wait=<seconds> required") from exc
        payload = collect_blog_asset_inventory(
            blog_id=blog_id,
            target_pages=target_pages,
            port=port,
            wait_seconds=wait_seconds,
            max_index_pages=max_index_pages,
            scroll_steps=scroll_steps,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if not payload.get("ok"):
            raise SystemExit(1)
        return

    if sub in ("analyze", "analysis", "image-analysis", "images"):
        inventory_path = Path(_option_value(args, "--data=") or "data/naver_blog_asset_inventory_latest.json")
        if not inventory_path.exists():
            raise SystemExit(f"inventory file not found: {inventory_path}")
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        payload = analyze_blog_asset_images(inventory)
        path = save_blog_image_analysis(payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"saved: {path}")
        return

    if sub in ("pixel-analyze", "pixel-analysis", "visual-analyze", "download-analyze"):
        inventory_path = Path(_option_value(args, "--data=") or "data/naver_blog_asset_inventory_latest.json")
        if not inventory_path.exists():
            raise SystemExit(f"inventory file not found: {inventory_path}")
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        limit = _int_option(args, "--limit=", 100)
        output_dir = _option_value(args, "--output-dir=") or "tmp/naver_blog_downloaded_images"
        payload = analyze_blog_asset_images_with_pixels(inventory, output_dir=output_dir, limit=limit)
        path = save_blog_pixel_analysis(payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"saved: {path}")
        return

    if sub in ("manifest", "shopping-manifest", "reuse-manifest"):
        inventory_path = Path(_option_value(args, "--data=") or "data/naver_blog_asset_inventory_latest.json")
        if not inventory_path.exists():
            raise SystemExit(f"inventory file not found: {inventory_path}")
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        confirm = _option_value(args, "--rights-confirm=") or ""
        payload = create_shopping_upload_manifest(inventory, rights_confirm=confirm)
        path = save_shopping_upload_manifest(payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"saved: {path}")
        if not payload.get("ok"):
            raise SystemExit(1)
        return

    print("usage: python scripts/cdp_client.py naver blog-assets [plan|inventory|analyze|pixel-analyze|manifest] --blog-id=gonobi [--target=1000]")


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


def _cmd_keyword_tools(sub: str, args: list[str]) -> None:
    from scripts.naver import keyword_tools

    query = _option_phrase(args, "--query=") or _option_value(args, "--keywords=") or ""
    topic = _option_value(args, "--topic=") or ""

    if sub in ("catalog", "tools", "status"):
        gate_check("scan_page")
        payload = keyword_tools.build_tool_catalog()
        path = keyword_tools.save_payload(payload)
        keyword_tools.print_summary(payload, path)
        return

    if sub in ("plan", "research-plan", "datalab", "shopping", "shopping-insight", "searchad-plan"):
        gate_check("scan_page")
        payload = keyword_tools.build_keyword_plan(query, topic=topic)
        payload["selected_tool"] = sub
        path = keyword_tools.save_payload(payload)
        keyword_tools.print_summary(payload, path)
        return

    if sub in ("paid-blocks", "paid-policy", "block-paid"):
        payload = keyword_tools.assert_paid_actions_blocked()
        path = keyword_tools.save_payload(payload)
        keyword_tools.print_summary(payload, path)
        return

    print("usage: python scripts/cdp_client.py naver keyword-tools [catalog|plan|datalab|shopping|searchad-plan|paid-blocks] --query=...")

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
        from scripts.naver.cafe import list_background_runner

        strict_domain = "--strict-domain" in args
        report = list_background_runner.collect_background(
            allow_mixed_readonly=not strict_domain,
            per_page=_int_option(args, "--per-page=", 100),
        )
        if not report.ok:
            raise SystemExit(json.dumps(report.to_dict(), ensure_ascii=False))
        out = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "cafes": report.cafes,
            "favorites": report.favorites,
            "manages": report.manages,
            "joined_total": report.joined_total,
            "favorite_total": report.favorite_total,
            "manage_total": report.manage_total,
            "readonly": True,
            "attach_only": True,
            "browser_launch": False,
            "browser_close": False,
        }
        path = Path("data/naver_cafes_latest.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"saved: {path}")
        return

    if sub in ("home", "main", "main-page"):
        gate_check("scan_page")
        from scripts.naver.cafe import list_background_runner

        strict_domain = "--strict-domain" in args
        report = list_background_runner.collect_main_background(
            allow_mixed_readonly=not strict_domain,
        )
        if not report.ok:
            raise SystemExit(json.dumps(report.to_dict(), ensure_ascii=False))
        out = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            **report.to_dict(),
            "readonly": True,
            "attach_only": True,
            "browser_launch": False,
            "browser_close": False,
        }
        path = Path("data/naver_cafe_main_latest.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"saved: {path}")
        return

    if sub in ("topic-search", "search", "topics"):
        gate_check("scan_page")
        from scripts.naver.cafe import list_background_runner

        strict_domain = "--strict-domain" in args
        query = _option_phrase(args, "--query=") or _option_value(args, "--keywords=") or ""
        report = list_background_runner.collect_topic_search_background(
            allow_mixed_readonly=not strict_domain,
            keywords=query,
            limit_per_keyword=_int_option(args, "--limit=", 10),
        )
        if not report.ok:
            raise SystemExit(json.dumps(report.to_dict(), ensure_ascii=False))
        out = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            **report.to_dict(),
            "readonly": True,
            "attach_only": True,
            "browser_launch": False,
            "browser_close": False,
        }
        path = Path("data/naver_cafe_topic_search_latest.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"saved: {path}")
        return

    if sub in ("join-submit", "join-approve"):
        from scripts.naver.cafe.join_request import APPROVAL_CONFIRM_TEXT

        cafe_url = _option_value(args, "--cafe-url=") or _option_value(args, "--cafe=") or (
            args[0] if args and not str(args[0]).startswith("--") else ""
        )
        approved = "--approved" in args
        confirm = _option_value(args, "--confirm=") or ""
        approved_by = _option_value(args, "--approved-by=") or "operator"
        if not cafe_url:
            raise SystemExit("cafe join-submit requires --cafe-url=CAFE")
        if not approved or confirm != APPROVAL_CONFIRM_TEXT:
            raise SystemExit(f"cafe join-submit requires --approved --confirm={APPROVAL_CONFIRM_TEXT}")
        gate_check(
            "naver_cafe_join_submit",
            risk="approve",
            force=True,
            service="naver_cafe",
            cafe_url=cafe_url,
            approved_by=approved_by,
        )
        out = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "ok": True,
            "cafe_url": cafe_url,
            "approval_gate": "naver_cafe_join_submit",
            "approved_by": approved_by,
            "browser_submit_executed": False,
            "final_click_adapter_required": True,
            "message": "Join submit approval gate passed; final browser click must be executed by a visible-form adapter.",
        }
        safe_cafe = "".join(ch for ch in cafe_url if ch.isalnum() or ch in ("_", "-")) or "cafe"
        path = Path(f"data/naver_cafe_{safe_cafe}_join_submit_latest.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"saved: {path}")
        return

    if sub in ("join", "join-request", "join-prepare", "approval-request"):
        gate_check("scan_page")
        from scripts.naver.cafe import list_background_runner

        strict_domain = "--strict-domain" in args
        cafe_url = _option_value(args, "--cafe-url=") or _option_value(args, "--cafe=") or (
            args[0] if args and not str(args[0]).startswith("--") else ""
        )
        if not cafe_url:
            raise SystemExit("cafe join-request requires --cafe-url=CAFE")
        nickname = _option_phrase(args, "--nickname=") or ""
        purpose = _option_phrase(args, "--purpose=") or ""
        answers = {}
        for arg in args:
            text = str(arg)
            if text.startswith("--answer=") and ":" in text:
                key, value = text.split("=", 1)[1].split(":", 1)
                answers[key.strip()] = value.strip()
        report = list_background_runner.collect_joined_cafe_background(
            cafe_url=cafe_url,
            mode="join-request",
            allow_mixed_readonly=not strict_domain,
            nickname=nickname,
            purpose=purpose,
            answers=answers,
        )
        if not report.ok:
            raise SystemExit(json.dumps(report.to_dict(), ensure_ascii=False))
        out = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            **report.to_dict(),
            "readonly": False,
            "prepare_only": True,
            "approval_required": True,
            "final_submit_blocked": True,
            "attach_only": True,
            "browser_launch": False,
            "browser_close": False,
        }
        safe_cafe = "".join(ch for ch in cafe_url if ch.isalnum() or ch in ("_", "-")) or "cafe"
        path = Path(f"data/naver_cafe_{safe_cafe}_join_request_latest.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"saved: {path}")
        return

    if sub in ("collect", "collect-home", "member-collect", "boards", "collect-boards"):
        gate_check("scan_page")
        from scripts.naver.cafe import list_background_runner

        strict_domain = "--strict-domain" in args
        cafe_url = _option_value(args, "--cafe-url=") or _option_value(args, "--cafe=") or (
            args[0] if args and not str(args[0]).startswith("--") else "soho"
        )
        mode = "boards" if sub in ("boards", "collect-boards") or "--boards" in args else "home"
        report = list_background_runner.collect_joined_cafe_background(
            cafe_url=cafe_url,
            mode=mode,
            allow_mixed_readonly=not strict_domain,
        )
        if not report.ok:
            raise SystemExit(json.dumps(report.to_dict(), ensure_ascii=False))
        out = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            **report.to_dict(),
            "readonly": True,
            "attach_only": True,
            "browser_launch": False,
            "browser_close": False,
        }
        suffix = "boards" if mode == "boards" else "collect"
        safe_cafe = "".join(ch for ch in cafe_url if ch.isalnum() or ch in ("_", "-")) or "cafe"
        path = Path(f"data/naver_cafe_{safe_cafe}_{suffix}_latest.json")
        path.parent.mkdir(parents=True, exist_ok=True)
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
        print("usage: python scripts/cdp_client.py naver cafe [list|home|topic-search|join-request|collect|boards|posts|read|write|publish] ...")
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
    result = NaverTalk(get_page()).send_message(partner, message, confirm=True, approval_confirm=confirm)
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
    """네이버 로그인 — 브라우저에서 사용자가 로그인하면 자동 감지.

    input() / 터미널 입력 없음. 앱에서 호출 시에도 동일하게 동작.
    CDP 데몬이 꺼져 있으면 자동 시작 후 연결.
    """
    from scripts.web_connector import browser_session
    from scripts.login_session import is_logged_in
    from scripts.login_detector import monitor_for_login
    from scripts.naver.browser_gate import require_naver_browser

    print("=" * 60)
    print("네이버 로그인")
    print("=" * 60)

    require_naver_browser()
    with browser_session() as page:
        page.goto("https://www.naver.com/", timeout=60000)

        if is_logged_in(page, "naver"):
            print("✓ 이미 로그인 상태입니다")
            print("=" * 60)
            return

        print("\n브라우저에서 네이버에 로그인하세요 (최대 5분 대기)")
        print("로그인 완료되면 자동으로 진행됩니다\n")

        # 터미널 input() 없이 로그인 자동 감지
        result = monitor_for_login(page, check_interval=2, timeout_s=300)

        if result.get("detected"):
            print(f"✓ 로그인 감지 완료 — {result.get('elapsed_s', 0):.0f}초")
        else:
            reason = result.get("aborted_reason", "timeout")
            print(f"⚠  로그인 미감지 — {reason}")
            print("   브라우저에서 로그인 완료 후 다시 시도하세요")

    print("=" * 60)
