"""Company homepage SEO workflow for Naver Search Advisor."""
from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts.common.json_report import save_json_report

DATA_DIR = Path("data")
LATEST_PLAN_PATH = DATA_DIR / "naver_company_seo_plan_latest.json"
LATEST_DIAGNOSIS_PATH = DATA_DIR / "naver_company_seo_diagnosis_latest.json"
LATEST_ENTRYPOINTS_PATH = DATA_DIR / "naver_company_seo_entrypoints_latest.json"
LATEST_ASSETS_PATH = DATA_DIR / "naver_company_seo_assets_latest.json"
LATEST_OWNERSHIP_PATH = DATA_DIR / "naver_company_seo_ownership_latest.json"
LATEST_EXPOSURE_PATH = DATA_DIR / "naver_company_seo_exposure_latest.json"
LATEST_SUBMIT_PLAN_PATH = DATA_DIR / "naver_company_seo_submit_plan_latest.json"
LATEST_MONITOR_PATH = DATA_DIR / "naver_company_seo_monitor_latest.json"


OFFICIAL_ENTRYPOINTS: dict[str, dict[str, Any]] = {
    "search_advisor": {
        "label": "Naver Search Advisor",
        "url": "https://searchadvisor.naver.com/",
        "purpose": "homepage ownership verification, robots/sitemap checks, and search exposure diagnostics",
        "state_changing_actions": ["site_add", "ownership_verify", "sitemap_submit", "robots_request"],
    },
    "search_advisor_webmaster": {
        "label": "Naver Search Advisor Webmaster Tools",
        "url": "https://searchadvisor.naver.com/console/board",
        "purpose": "registered-site management after login",
        "state_changing_actions": ["site_add", "sitemap_submit", "diagnostic_request"],
    },
    "developers": {
        "label": "NAVER Developers",
        "url": "https://developers.naver.com/",
        "purpose": "OpenAPI app registration and API credential management",
        "state_changing_actions": ["app_register", "api_scope_change", "credential_issue"],
    },
    "developers_apps": {
        "label": "NAVER Developers Applications",
        "url": "https://developers.naver.com/apps/",
        "purpose": "application registration and Client ID/Secret management",
        "state_changing_actions": ["app_register", "app_update", "delete_app"],
    },
    "shopping_partner": {
        "label": "Naver Shopping Partner Center",
        "url": "https://center.shopping.naver.com/",
        "purpose": "shopping product feed, partner account, reports, and shopping ad management",
        "state_changing_actions": ["partner_apply", "product_feed_change", "ad_change"],
    },
    "smartstore": {
        "label": "Naver SmartStore Center",
        "url": "https://sell.smartstore.naver.com/",
        "purpose": "store products, orders, reviews, settlement, and product SEO",
        "state_changing_actions": ["product_save", "order_action", "review_reply"],
    },
    "search_ad": {
        "label": "Naver Search Ad",
        "url": "https://searchad.naver.com/",
        "purpose": "search and shopping ad campaigns",
        "state_changing_actions": ["campaign_create", "budget_change", "ad_submit"],
    },
}


@dataclass
class PageSeoSnapshot:
    url: str
    status: str
    title: str = ""
    description: str = ""
    canonical: str = ""
    robots: str = ""
    viewport: str = ""
    h1: list[str] | None = None
    og: dict[str, str] | None = None
    json_ld_count: int = 0
    body_text_length: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status": self.status,
            "title": self.title,
            "description": self.description,
            "canonical": self.canonical,
            "robots": self.robots,
            "viewport": self.viewport,
            "h1": self.h1 or [],
            "og": self.og or {},
            "json_ld_count": self.json_ld_count,
            "body_text_length": self.body_text_length,
        }


class _SeoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.description = ""
        self.canonical = ""
        self.robots = ""
        self.viewport = ""
        self.og: dict[str, str] = {}
        self.h1: list[str] = []
        self.json_ld_count = 0
        self._in_title = False
        self._in_h1 = False
        self._h1_buffer: list[str] = []
        self._body_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = {k.lower(): v or "" for k, v in attrs}
        tag_l = tag.lower()
        if tag_l == "title":
            self._in_title = True
        elif tag_l == "meta":
            name = attrs_d.get("name", "").lower()
            prop = attrs_d.get("property", "").lower()
            content = attrs_d.get("content", "").strip()
            if name == "description":
                self.description = content
            elif name == "robots":
                self.robots = content
            elif name == "viewport":
                self.viewport = content
            elif prop.startswith("og:"):
                self.og[prop] = content
        elif tag_l == "link" and attrs_d.get("rel", "").lower() == "canonical":
            self.canonical = attrs_d.get("href", "").strip()
        elif tag_l == "h1":
            self._in_h1 = True
            self._h1_buffer = []
        elif tag_l == "script" and attrs_d.get("type", "").lower() == "application/ld+json":
            self.json_ld_count += 1

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l == "title":
            self._in_title = False
        elif tag_l == "h1":
            self._in_h1 = False
            text = _squash(" ".join(self._h1_buffer))
            if text:
                self.h1.append(text[:120])

    def handle_data(self, data: str) -> None:
        text = _squash(data)
        if not text:
            return
        self._body_chunks.append(text)
        if self._in_title:
            self.title += text
        if self._in_h1:
            self._h1_buffer.append(text)

    @property
    def body_text_length(self) -> int:
        return len(" ".join(self._body_chunks))


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_site_url(site_url: str) -> str:
    text = (site_url or "").strip()
    if not text:
        raise ValueError("site_url is required")
    if not re.match(r"^https?://", text, flags=re.I):
        text = "https://" + text
    parsed = urlparse(text)
    if not parsed.netloc:
        raise ValueError("site_url must include host")
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path or ''}".rstrip("/")


def build_entrypoints() -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "site": "naver",
        "homepage_seo_primary": "search_advisor",
        "shopping_competitor_primary": "shopping_search",
        "entrypoints": OFFICIAL_ENTRYPOINTS,
    }


def save_entrypoints(output: str | Path | None = None) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(output) if output else LATEST_ENTRYPOINTS_PATH
    path.write_text(json.dumps(build_entrypoints(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def analyze_html(site_url: str, html: str, *, status: str = "ok") -> dict[str, Any]:
    parser = _SeoHTMLParser()
    parser.feed(html or "")
    snapshot = PageSeoSnapshot(
        url=normalize_site_url(site_url),
        status=status,
        title=_squash(parser.title),
        description=parser.description,
        canonical=parser.canonical,
        robots=parser.robots,
        viewport=parser.viewport,
        h1=parser.h1,
        og=parser.og,
        json_ld_count=parser.json_ld_count,
        body_text_length=parser.body_text_length,
    )
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not snapshot.title:
        issues.append({"code": "missing_title", "message": "HTML title is missing"})
    elif len(snapshot.title) > 70:
        warnings.append({"code": "long_title", "message": "Title is longer than 70 characters"})
    if not snapshot.description:
        issues.append({"code": "missing_description", "message": "Meta description is missing"})
    elif len(snapshot.description) > 160:
        warnings.append({"code": "long_description", "message": "Meta description is longer than 160 characters"})
    if not snapshot.canonical:
        warnings.append({"code": "missing_canonical", "message": "Canonical URL is missing"})
    if not snapshot.viewport:
        warnings.append({"code": "missing_viewport", "message": "Viewport meta is missing"})
    if not snapshot.h1:
        warnings.append({"code": "missing_h1", "message": "H1 heading is missing"})
    if "noindex" in snapshot.robots.lower():
        issues.append({"code": "robots_noindex", "message": "Robots meta contains noindex"})
    if not snapshot.og:
        warnings.append({"code": "missing_open_graph", "message": "Open Graph metadata is missing"})

    score = max(0, 100 - len(issues) * 20 - len(warnings) * 5)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "snapshot": snapshot.to_dict(),
        "score": score,
        "issues": issues,
        "warnings": warnings,
        "naver_search_advisor_targets": {
            "site_url": snapshot.url,
            "robots_url": snapshot.url.rstrip("/") + "/robots.txt",
            "sitemap_url": snapshot.url.rstrip("/") + "/sitemap.xml",
        },
    }


def _default_transport(url: str, timeout: int = 12) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "haehan-ai-orchestrator/naver-seo-audit",
            "Accept": "text/html,application/xhtml+xml,application/xml,text/plain,*/*",
        },
    )
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:  # noqa: S310 - user-supplied SEO audit URL
            raw = response.read(2_000_000)
            content_type = response.headers.get("Content-Type", "")
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                text = raw.decode(charset, errors="replace")
            except LookupError:
                text = raw.decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status_code": int(response.status),
                "content_type": content_type,
                "text": text,
                "size": len(raw),
                "final_url": response.url,
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status_code": int(exc.code),
            "content_type": exc.headers.get("Content-Type", "") if exc.headers else "",
            "text": "",
            "size": 0,
            "final_url": url,
            "error": f"HTTP_{exc.code}",
        }
    except Exception as exc:  # noqa: BLE001
        fallback = _curl_transport(url, timeout=timeout)
        if fallback.get("ok"):
            fallback["transport_fallback"] = "curl"
            fallback["primary_error"] = type(exc).__name__
            return fallback
        fallback["primary_error"] = type(exc).__name__
        return fallback


def _curl_transport(url: str, timeout: int = 12) -> dict[str, Any]:
    marker = "__HAEHAN_CURL_STATUS__"
    try:
        result = subprocess.run(
            [
                "curl",
                "-L",
                "--silent",
                "--show-error",
                "--max-time",
                str(timeout),
                "--noproxy",
                "*",
                "--user-agent",
                "haehan-ai-orchestrator/naver-seo-audit",
                "--header",
                "Accept: text/html,application/xhtml+xml,application/xml,text/plain,*/*",
                "--write-out",
                f"\n{marker}%{{http_code}}\t%{{url_effective}}\t%{{content_type}}",
                url,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status_code": None,
            "content_type": "",
            "text": "",
            "size": 0,
            "final_url": url,
            "error": type(exc).__name__,
        }

    stdout = result.stdout or ""
    body, sep, meta = stdout.rpartition(marker)
    if not sep:
        return {
            "ok": False,
            "status_code": None,
            "content_type": "",
            "text": "",
            "size": 0,
            "final_url": url,
            "error": "CurlError",
            "stderr": (result.stderr or "").strip()[:300],
        }
    status_text, final_url, content_type = (meta.strip().split("\t") + ["", "", ""])[:3]
    try:
        status_code = int(status_text)
    except ValueError:
        status_code = None
    return {
        "ok": result.returncode == 0 and status_code is not None and 200 <= status_code < 400,
        "status_code": status_code,
        "content_type": content_type,
        "text": body,
        "size": len(body.encode("utf-8", errors="replace")),
        "final_url": final_url or url,
        "error": "" if result.returncode == 0 else "CurlError",
        "stderr": (result.stderr or "").strip()[:300],
    }


def fetch_url(url: str, *, transport=None) -> dict[str, Any]:
    return (transport or _default_transport)(url)


def analyze_robots(site_url: str, text: str, status: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_site_url(site_url)
    sitemap_lines = []
    disallow_all = False
    allow_root = False
    for line in (text or "").splitlines():
        clean = line.strip()
        if clean.lower().startswith("sitemap:"):
            sitemap_lines.append(clean.split(":", 1)[1].strip())
        if clean.lower() == "disallow: /":
            disallow_all = True
        if clean.lower() in {"allow: /", "disallow:"}:
            allow_root = True
    return {
        "url": normalized.rstrip("/") + "/robots.txt",
        "reachable": bool(status.get("ok")),
        "status_code": status.get("status_code"),
        "content_type": status.get("content_type"),
        "size": status.get("size", 0),
        "sitemaps": sitemap_lines,
        "disallow_all": disallow_all,
        "allow_root": allow_root,
        "warnings": [
            warning
            for warning in [
                "robots_not_reachable" if not status.get("ok") else "",
                "robots_disallow_all" if disallow_all else "",
                "robots_no_sitemap_hint" if not sitemap_lines else "",
            ]
            if warning
        ],
    }


def analyze_sitemap(site_url: str, text: str, status: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_site_url(site_url)
    loc_count = len(re.findall(r"<loc>\s*[^<]+\s*</loc>", text or "", flags=re.I))
    sitemap_index = bool(re.search(r"<sitemapindex\b", text or "", flags=re.I))
    urlset = bool(re.search(r"<urlset\b", text or "", flags=re.I))
    return {
        "url": normalized.rstrip("/") + "/sitemap.xml",
        "reachable": bool(status.get("ok")),
        "status_code": status.get("status_code"),
        "content_type": status.get("content_type"),
        "size": status.get("size", 0),
        "loc_count": loc_count,
        "sitemap_index": sitemap_index,
        "urlset": urlset,
        "warnings": [
            warning
            for warning in [
                "sitemap_not_reachable" if not status.get("ok") else "",
                "sitemap_no_loc_entries" if status.get("ok") and loc_count == 0 else "",
            ]
            if warning
        ],
    }


def audit_site_assets(site_url: str, *, transport=None) -> dict[str, Any]:
    normalized = normalize_site_url(site_url)
    home = fetch_url(normalized, transport=transport)
    robots = fetch_url(normalized.rstrip("/") + "/robots.txt", transport=transport)
    sitemap = fetch_url(normalized.rstrip("/") + "/sitemap.xml", transport=transport)
    diagnosis = analyze_html(normalized, home.get("text", ""), status="ok" if home.get("ok") else "fetch_failed")
    robots_report = analyze_robots(normalized, robots.get("text", ""), robots)
    sitemap_report = analyze_sitemap(normalized, sitemap.get("text", ""), sitemap)
    issues = []
    issues.extend(diagnosis.get("issues", []))
    issues.extend({"code": code, "message": code} for code in robots_report.get("warnings", []))
    issues.extend({"code": code, "message": code} for code in sitemap_report.get("warnings", []))
    score = max(0, min(100, diagnosis.get("score", 0) - len(robots_report.get("warnings", [])) * 5 - len(sitemap_report.get("warnings", [])) * 5))
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "naver_company_seo_asset_audit",
        "site_url": normalized,
        "score": score,
        "homepage": {
            "reachable": bool(home.get("ok")),
            "status_code": home.get("status_code"),
            "content_type": home.get("content_type"),
            "final_url": home.get("final_url"),
            "size": home.get("size", 0),
            "error": home.get("error"),
        },
        "diagnosis": diagnosis,
        "robots": robots_report,
        "sitemap": sitemap_report,
        "issues": issues,
    }


def build_ownership_plan(site_url: str, *, company_name: str = "haehan-ai") -> dict[str, Any]:
    normalized = normalize_site_url(site_url)
    host = urlparse(normalized).netloc
    token_placeholder = "NAVER_SITE_VERIFICATION_TOKEN"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "naver_searchadvisor_ownership_prepare",
        "company_name": company_name,
        "site_url": normalized,
        "methods": [
            {
                "id": "html_file",
                "state_change": True,
                "approval_required": True,
                "file_name": f"naver{token_placeholder}.html",
                "target_url": f"{normalized.rstrip('/')}/naver{token_placeholder}.html",
                "required_content": f"naver-site-verification: {token_placeholder}",
            },
            {
                "id": "html_meta_tag",
                "state_change": True,
                "approval_required": True,
                "tag": f'<meta name="naver-site-verification" content="{token_placeholder}">',
                "target": "homepage <head>",
            },
            {
                "id": "dns_txt",
                "state_change": True,
                "approval_required": True,
                "host": host,
                "record_type": "TXT",
                "record_value": f"naver-site-verification={token_placeholder}",
            },
        ],
        "confirm_text": "NAVER_APPROVED_SEO_SUBMIT",
    }


def build_exposure_plan(site_url: str, *, keywords: list[str] | None = None) -> dict[str, Any]:
    normalized = normalize_site_url(site_url)
    host = urlparse(normalized).netloc
    keywords = [k.strip() for k in (keywords or []) if k and k.strip()]
    queries = [f"site:{host}", *keywords]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "naver_search_exposure_check",
        "site_url": normalized,
        "queries": [
            {
                "query": query,
                "url": "https://search.naver.com/search.naver?query=" + query.replace(" ", "+"),
                "state_change": False,
            }
            for query in queries
        ],
        "note": "Use browser or official/public search result observation only; no CAPTCHA bypass or result manipulation.",
    }


def build_submit_plan(site_url: str, *, keywords: list[str] | None = None, company_name: str = "haehan-ai") -> dict[str, Any]:
    normalized = normalize_site_url(site_url)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "naver_searchadvisor_submit_prepare",
        "company_name": company_name,
        "site_url": normalized,
        "approval_required": True,
        "confirm_text": "NAVER_APPROVED_SEO_SUBMIT",
        "submit_steps": [
            {"id": "open_webmaster_tools", "url": OFFICIAL_ENTRYPOINTS["search_advisor_webmaster"]["url"]},
            {"id": "add_site", "value": normalized},
            {"id": "verify_ownership", "allowed_methods": ["html_file", "html_meta_tag", "dns_txt"]},
            {"id": "submit_sitemap", "value": normalized.rstrip("/") + "/sitemap.xml"},
            {"id": "request_diagnostics", "value": normalized},
        ],
        "prechecks": ["asset_audit_pass", "ownership_method_selected", "user_approval_present"],
        "keywords": [k.strip() for k in (keywords or []) if k and k.strip()],
    }


def build_monitor_report(
    site_url: str,
    *,
    assets: dict[str, Any] | None = None,
    exposure: dict[str, Any] | None = None,
    submit_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_site_url(site_url)
    checks = []
    if assets:
        checks.append({"name": "assets", "ok": assets.get("score", 0) >= 70, "score": assets.get("score")})
        checks.append({"name": "robots", "ok": assets.get("robots", {}).get("reachable") is True})
        checks.append({"name": "sitemap", "ok": assets.get("sitemap", {}).get("reachable") is True})
    if exposure:
        checks.append({"name": "exposure_plan", "ok": bool(exposure.get("queries"))})
    if submit_plan:
        checks.append({"name": "submit_plan", "ok": submit_plan.get("approval_required") is True})
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "naver_company_seo_monitor",
        "site_url": normalized,
        "status": "ok" if checks and all(c.get("ok") for c in checks) else "degraded",
        "checks": checks,
        "next_actions": [
            "Fix homepage metadata issues before Search Advisor submission",
            "Confirm ownership method and apply approved verification asset",
            "Submit sitemap after approval",
            "Track Naver search exposure and shopping competitor keywords regularly",
        ],
    }


def build_company_seo_plan(
    site_url: str,
    *,
    company_name: str = "haehan-ai",
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    normalized = normalize_site_url(site_url)
    keywords = [k.strip() for k in (keywords or []) if k and k.strip()]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "naver_company_homepage_seo",
        "company_name": company_name,
        "site_url": normalized,
        "keywords": keywords,
        "official_entrypoints": OFFICIAL_ENTRYPOINTS,
        "phases": [
            {
                "id": "homepage_technical_diagnosis",
                "actions": ["title_meta_check", "canonical_check", "robots_check", "sitemap_check", "structured_data_check"],
                "state_change": False,
            },
            {
                "id": "search_advisor_registration_prepare",
                "actions": ["open_search_advisor", "prepare_site_add", "prepare_ownership_verification"],
                "state_change": False,
                "approval_required_for_submit": True,
            },
            {
                "id": "search_advisor_submit_after_approval",
                "actions": ["site_add", "ownership_verify", "sitemap_submit", "robots_request", "diagnostic_request"],
                "state_change": True,
                "approval_required": True,
                "confirm_text": "NAVER_APPROVED_SEO_SUBMIT",
            },
            {
                "id": "developer_center_openapi_setup",
                "actions": ["open_developers", "prepare_app_registration", "prepare_search_api_credentials"],
                "state_change": True,
                "approval_required": True,
                "confirm_text": "NAVER_APPROVED_DEV_APP",
            },
            {
                "id": "shopping_competitor_monitoring",
                "actions": ["collect_shopping_search", "price_distribution", "mall_distribution", "trend_store"],
                "state_change": False,
            },
            {
                "id": "recurring_monitoring_report",
                "actions": ["asset_audit", "exposure_check", "excel_report", "mail_attach_prepare"],
                "state_change": False,
            },
        ],
        "derived_urls": {
            "robots": normalized.rstrip("/") + "/robots.txt",
            "sitemap": normalized.rstrip("/") + "/sitemap.xml",
            "search_advisor": OFFICIAL_ENTRYPOINTS["search_advisor"]["url"],
            "developers": OFFICIAL_ENTRYPOINTS["developers"]["url"],
            "shopping_partner": OFFICIAL_ENTRYPOINTS["shopping_partner"]["url"],
        },
    }


def save_plan(plan: dict[str, Any], output: str | Path | None = None) -> Path:
    return save_json_report(plan, DATA_DIR, LATEST_PLAN_PATH, output)


def save_diagnosis(diagnosis: dict[str, Any], output: str | Path | None = None) -> Path:
    return save_json_report(diagnosis, DATA_DIR, LATEST_DIAGNOSIS_PATH, output)


def _save_json(payload: dict[str, Any], default_path: Path, output: str | Path | None = None) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(output) if output else default_path
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_assets(assets: dict[str, Any], output: str | Path | None = None) -> Path:
    return _save_json(assets, LATEST_ASSETS_PATH, output)


def save_ownership_plan(plan: dict[str, Any], output: str | Path | None = None) -> Path:
    return _save_json(plan, LATEST_OWNERSHIP_PATH, output)


def save_exposure_plan(plan: dict[str, Any], output: str | Path | None = None) -> Path:
    return _save_json(plan, LATEST_EXPOSURE_PATH, output)


def save_submit_plan(plan: dict[str, Any], output: str | Path | None = None) -> Path:
    return _save_json(plan, LATEST_SUBMIT_PLAN_PATH, output)


def save_monitor_report(report: dict[str, Any], output: str | Path | None = None) -> Path:
    return _save_json(report, LATEST_MONITOR_PATH, output)


def print_plan_summary(plan: dict[str, Any], path: Path) -> None:
    print("Naver company homepage SEO plan")
    print(f"  site: {plan['site_url']}")
    print(f"  company: {plan['company_name']}")
    print(f"  phases: {len(plan['phases'])}")
    for phase in plan["phases"]:
        approval = " approval" if phase.get("approval_required") or phase.get("approval_required_for_submit") else ""
        print(f"  - {phase['id']}: actions={len(phase['actions'])}{approval}")
    print(f"saved: {path}")


def print_diagnosis_summary(diagnosis: dict[str, Any], path: Path) -> None:
    snap = diagnosis["snapshot"]
    print("Naver company homepage SEO diagnosis")
    print(f"  url: {snap['url']}")
    print(f"  score: {diagnosis['score']}")
    print(f"  title: {snap['title'][:80]}")
    print(f"  issues: {len(diagnosis['issues'])}")
    print(f"  warnings: {len(diagnosis['warnings'])}")
    print(f"saved: {path}")


def print_assets_summary(assets: dict[str, Any], path: Path) -> None:
    print("Naver company SEO asset audit")
    print(f"  site: {assets['site_url']}")
    print(f"  score: {assets['score']}")
    print(f"  homepage: {assets['homepage'].get('status_code')} reachable={assets['homepage'].get('reachable')}")
    print(f"  robots: {assets['robots'].get('status_code')} reachable={assets['robots'].get('reachable')}")
    print(f"  sitemap: {assets['sitemap'].get('status_code')} loc={assets['sitemap'].get('loc_count')}")
    print(f"saved: {path}")


__all__ = [
    "OFFICIAL_ENTRYPOINTS",
    "analyze_html",
    "audit_site_assets",
    "build_exposure_plan",
    "build_company_seo_plan",
    "build_entrypoints",
    "build_monitor_report",
    "build_ownership_plan",
    "build_submit_plan",
    "normalize_site_url",
    "print_assets_summary",
    "print_diagnosis_summary",
    "print_plan_summary",
    "save_assets",
    "save_diagnosis",
    "save_entrypoints",
    "save_exposure_plan",
    "save_monitor_report",
    "save_ownership_plan",
    "save_plan",
    "save_submit_plan",
]
