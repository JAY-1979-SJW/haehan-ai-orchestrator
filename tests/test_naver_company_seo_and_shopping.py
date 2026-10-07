from __future__ import annotations

import json

from scripts.naver import company_seo
from scripts.naver.shopping import competitor_report as shopping_competitor


def test_company_seo_plan_includes_searchadvisor_and_approval_gate(tmp_path):
    plan = company_seo.build_company_seo_plan(
        "haehan-ai.kr",
        company_name="haehan-ai",
        keywords=["AI 업무 자동화", "네이버 SEO"],
    )

    assert plan["site_url"] == "https://haehan-ai.kr"
    assert plan["derived_urls"]["sitemap"] == "https://haehan-ai.kr/sitemap.xml"
    assert "search_advisor" in plan["official_entrypoints"]
    assert any(p.get("confirm_text") == "NAVER_APPROVED_SEO_SUBMIT" for p in plan["phases"])

    path = company_seo.save_plan(plan, tmp_path / "plan.json")
    assert json.loads(path.read_text(encoding="utf-8"))["workflow"] == "naver_company_homepage_seo"


def test_analyze_html_scores_common_homepage_metadata():
    html = """
    <html>
      <head>
        <title>해한 AI 업무 자동화</title>
        <meta name="description" content="기업 업무 자동화와 운영 대시보드">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="canonical" href="https://haehan-ai.kr/">
        <meta property="og:title" content="해한 AI">
        <script type="application/ld+json">{"@context":"https://schema.org"}</script>
      </head>
      <body><h1>해한 AI</h1><p>업무 자동화</p></body>
    </html>
    """

    diagnosis = company_seo.analyze_html("https://haehan-ai.kr", html)

    assert diagnosis["score"] == 100
    assert diagnosis["issues"] == []
    assert diagnosis["snapshot"]["json_ld_count"] == 1


def test_analyze_html_flags_noindex_and_missing_description():
    diagnosis = company_seo.analyze_html(
        "https://haehan-ai.kr",
        "<html><head><meta name='robots' content='noindex'></head><body></body></html>",
    )

    codes = {item["code"] for item in diagnosis["issues"]}
    assert "missing_title" in codes
    assert "missing_description" in codes
    assert "robots_noindex" in codes


def test_asset_audit_checks_home_robots_and_sitemap():
    def transport(url: str):
        if url.endswith("/robots.txt"):
            return {
                "ok": True,
                "status_code": 200,
                "content_type": "text/plain",
                "text": "User-agent: *\nAllow: /\nSitemap: https://haehan-ai.kr/sitemap.xml",
                "size": 70,
                "final_url": url,
            }
        if url.endswith("/sitemap.xml"):
            return {
                "ok": True,
                "status_code": 200,
                "content_type": "application/xml",
                "text": "<urlset><url><loc>https://haehan-ai.kr/</loc></url></urlset>",
                "size": 64,
                "final_url": url,
            }
        return {
            "ok": True,
            "status_code": 200,
            "content_type": "text/html",
            "text": """
            <html><head><title>haehan-ai</title>
            <meta name="description" content="AI automation">
            <meta name="viewport" content="width=device-width">
            <link rel="canonical" href="https://haehan-ai.kr/">
            <meta property="og:title" content="haehan-ai"></head>
            <body><h1>haehan-ai</h1></body></html>
            """,
            "size": 300,
            "final_url": url,
        }

    audit = company_seo.audit_site_assets("https://haehan-ai.kr", transport=transport)

    assert audit["homepage"]["reachable"] is True
    assert audit["robots"]["sitemaps"] == ["https://haehan-ai.kr/sitemap.xml"]
    assert audit["sitemap"]["loc_count"] == 1
    assert audit["score"] == 100


def test_ownership_exposure_submit_and_monitor_plans():
    ownership = company_seo.build_ownership_plan("haehan-ai.kr")
    exposure = company_seo.build_exposure_plan("haehan-ai.kr", keywords=["AI 업무 자동화"])
    submit = company_seo.build_submit_plan("haehan-ai.kr")
    monitor = company_seo.build_monitor_report(
        "haehan-ai.kr",
        assets={"score": 80, "robots": {"reachable": True}, "sitemap": {"reachable": True}},
        exposure=exposure,
        submit_plan=submit,
    )

    assert {m["id"] for m in ownership["methods"]} == {"html_file", "html_meta_tag", "dns_txt"}
    assert exposure["queries"][0]["query"] == "site:haehan-ai.kr"
    assert submit["confirm_text"] == "NAVER_APPROVED_SEO_SUBMIT"
    assert monitor["status"] == "ok"


def test_shopping_competitor_analysis_price_distribution():
    report = shopping_competitor.analyze_competitors(
        "업무 자동화",
        [
            {"title": "A", "lprice": 10000, "mall_name": "mall-a", "brand": "brand-a"},
            {"title": "B", "lprice": 15000, "mall_name": "mall-a", "brand": "brand-b"},
            {"title": "C", "lprice": 20000, "mall_name": "mall-c", "brand": "brand-a"},
        ],
        my_price=16000,
        my_mall="haehan",
    )

    assert report["stats"]["min_price"] == 10000
    assert report["stats"]["avg_price"] == 15000
    assert report["stats"]["max_price"] == 20000
    assert report["stats"]["price_rank_estimate"] == 3
    assert report["top_malls"][0] == {"mall": "mall-a", "count": 2}


def test_shopping_competitor_openapi_dry_run(monkeypatch):
    monkeypatch.delenv("NAVER_OPENAPI_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_OPENAPI_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("NAVER_OPENAPI_DRY_RUN", raising=False)

    report = shopping_competitor.collect_openapi_competitors("keyboard", display=5)

    assert report["collection_status"] == "dry_run"
    assert report["item_count"] >= 1
    assert report["stats"]["min_price"] is not None
