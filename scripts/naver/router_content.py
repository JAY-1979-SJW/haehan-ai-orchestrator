"""네이버 콘텐츠/SEO/검색/키워드 명령 핸들러"""

from __future__ import annotations

from scripts.common.gate import check as gate_check
from scripts.naver.common.router_common import (
    _flag,
    _int_option,
    _option_phrase,
    _option_value,
    _print_saved,
    _save_latest,
)


def _cmd_content(sub: str, args: list[str]) -> None:
    from scripts.browser.cdp.connection import get_page
    from scripts.naver.common.content import (
        build_action_catalog,
        print_action_summary,
        print_surface_summary,
        save_action_catalog,
        save_surface_report,
        scan_target,
        select_targets,
    )
    from scripts.naver.common.live_safety import before_live_navigation

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
        print(
            "usage: python scripts/entry/cdp_cli.py naver content [explore|actions] [blog|blog_admin|cafe|all] [--limit=80]"
        )


def _seo_monitor(site_url: str, company: str, keywords: list[str]) -> None:
    """seo monitor/report-status."""
    from scripts.naver.company_seo import (
        audit_site_assets,
        build_exposure_plan,
        build_monitor_report,
        build_submit_plan,
        save_assets,
        save_diagnosis,
        save_exposure_plan,
        save_monitor_report,
        save_submit_plan,
    )
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


def _seo_full(site_url: str, company: str, keywords: list[str]) -> None:
    """seo full/all."""
    from scripts.naver.company_seo import (
        audit_site_assets,
        build_company_seo_plan,
        build_exposure_plan,
        build_monitor_report,
        build_ownership_plan,
        build_submit_plan,
        save_assets,
        save_diagnosis,
        save_exposure_plan,
        save_monitor_report,
        save_ownership_plan,
        save_plan,
        save_submit_plan,
    )
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


def _seo_diagnose(args: list[str], site_url: str) -> None:
    """seo diagnose/diagnosis/audit."""
    from pathlib import Path

    from scripts.naver.company_seo import (
        analyze_html,
        audit_site_assets,
        print_diagnosis_summary,
        save_assets,
        save_diagnosis,
    )

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


def _seo_submit(args: list[str], site_url: str, company: str, keywords: list[str]) -> None:
    """seo submit/register(승인 게이트)."""
    from scripts.naver.company_seo import build_submit_plan

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


def _seo_plan_group(sub: str, site_url: str, company: str, keywords: list[str]) -> bool:
    """seo ownership/exposure/submit-plan 처리. 처리했으면 True."""
    from scripts.naver.company_seo import (
        build_exposure_plan,
        build_ownership_plan,
        build_submit_plan,
        save_exposure_plan,
        save_ownership_plan,
        save_submit_plan,
    )

    if sub in ("ownership", "verify-plan", "verification"):
        gate_check("scan_page")
        plan = build_ownership_plan(site_url, company_name=company)
        path = save_ownership_plan(plan)
        _print_saved(plan, str(path))
        return True

    if sub in ("exposure", "search-status", "index-status"):
        gate_check("scan_page")
        plan = build_exposure_plan(site_url, keywords=keywords)
        path = save_exposure_plan(plan)
        _print_saved(plan, str(path))
        return True

    if sub in ("submit-plan", "submission-plan", "index-request-plan"):
        gate_check("scan_page")
        plan = build_submit_plan(site_url, keywords=keywords, company_name=company)
        path = save_submit_plan(plan)
        _print_saved(plan, str(path))
        return True
    return False


def _cmd_seo(sub: str, args: list[str]) -> None:
    from scripts.naver.company_seo import (
        audit_site_assets,
        build_company_seo_plan,
        build_entrypoints,
        print_assets_summary,
        print_plan_summary,
        save_assets,
        save_diagnosis,
        save_entrypoints,
        save_plan,
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

    if _seo_plan_group(sub, site_url, company, keywords):
        return

    if sub in ("monitor", "report-status"):
        gate_check("scan_page")
        _seo_monitor(site_url, company, keywords)
        return

    if sub in ("full", "all"):
        gate_check("scan_page")
        _seo_full(site_url, company, keywords)
        return

    if sub in ("diagnose", "diagnosis", "audit"):
        _seo_diagnose(args, site_url)
        return

    if sub in ("submit", "register"):
        _seo_submit(args, site_url, company, keywords)
        return

    print(
        "usage: python scripts/entry/cdp_cli.py naver seo [entrypoints|plan|assets|ownership|exposure|submit-plan|monitor|full|diagnose|submit] --site=https://haehan-ai.kr"
    )


def _cmd_developers(sub: str, args: list[str]) -> None:
    from datetime import datetime

    from scripts.naver.company_seo import OFFICIAL_ENTRYPOINTS

    gate_check("scan_page")
    if sub not in ("entrypoints", "plan", "apps"):
        print("usage: python scripts/entry/cdp_cli.py naver developers [entrypoints|plan]")
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
    from scripts.naver.shopping.competitor_report import (
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
        print(
            "usage: python scripts/entry/cdp_cli.py naver shopping competitors --query=KEYWORD [--display=20] [--my-price=N]"
        )
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
        print("usage: python scripts/entry/cdp_cli.py naver excel report [--output=PATH]")
        return
    gate_check("file_write")
    output = _option_value(args, "--output=")
    result = build_excel_report(output=output)
    print_excel_summary(result)


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

    print(
        "usage: python scripts/entry/cdp_cli.py naver keyword-tools [catalog|plan|datalab|shopping|searchad-plan|paid-blocks] --query=..."
    )
