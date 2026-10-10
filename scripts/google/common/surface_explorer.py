"""Read-only live explorer for Google service surfaces."""

from __future__ import annotations

import contextlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.google.common import surfaces

ROOT = Path(__file__).resolve().parents[3]
EXPLORATION_DIR = ROOT / "data" / "google_surface_explorations"
LATEST_EXPLORATION = ROOT / "data" / "google_surface_exploration_latest.json"

LOGIN_HINTS = (
    "Sign in",
    "\ub85c\uadf8\uc778",
    "Use your Google Account",
)

RISK_CONTROL_KEYWORDS = (
    "Send",
    "Publish",
    "Submit",
    "Save",
    "Create",
    "Grant",
    "Add",
    "Delete",
    "Remove",
    "Release",
    "Deploy",
    "Upload",
    "Request indexing",
    "API key",
    "Credential",
    "Billing",
    "Payment",
    "\ubcf4\ub0b4\uae30",
    "\uac8c\uc2dc",
    "\uc81c\ucd9c",
    "\uc800\uc7a5",
    "\ub9cc\ub4e4\uae30",
    "\uc0ad\uc81c",
    "\ucd9c\uc2dc",
    "\ubc30\ud3ec",
    "\uc5c5\ub85c\ub4dc",
)

EMAIL_RE = re.compile(r"(?i)[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")


def explore_google_surfaces(
    *,
    keys: list[str] | None = None,
    limit: int | None = None,
    timeout_ms: int = 30000,
) -> tuple[dict, Path]:
    """Visit Google surfaces read-only and save structured exploration evidence."""
    catalog = surfaces.build_surface_catalog()
    selected = catalog["surfaces"]
    if keys:
        wanted = set(keys)
        selected = [item for item in selected if item["key"] in wanted]
    if limit is not None:
        selected = selected[:limit]

    report = {
        "site_id": "google",
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "read_only_no_click",
        "policy": {
            "no_click": True,
            "no_input": True,
            "no_submit": True,
            "privacy": "no_full_html_or_screenshots_saved_by_default",
            "risk_keywords": list(RISK_CONTROL_KEYWORDS),
        },
        "source_catalog_counts": catalog["counts"],
        "counts": {
            "planned": len(selected),
            "visited": 0,
            "accessible": 0,
            "login_required": 0,
            "failed": 0,
            "risk_controls_detected": 0,
        },
        "surfaces": [],
    }

    try:
        from scripts.browser.cdp.connection import get_page

        base_page = get_page()
    except Exception as exc:  # noqa: BLE001 - 구글 서비스 화면 읽기전용 탐색기(로그인 필요 여부/위험버튼 분류) - 실패시 status=failed 기록, 쓰기 없음
        report["status"] = "failed"
        report["warnings"] = [f"browser connection failed: {exc}"]
        report["counts"]["failed"] = len(selected)
        return save_surface_exploration(report)

    for item in selected:
        visit_page = _new_isolated_page(base_page)
        try:
            result = _visit_surface(visit_page, item, timeout_ms=timeout_ms)
        finally:
            if visit_page is not base_page:
                with contextlib.suppress(Exception):
                    visit_page.close()
        report["surfaces"].append(result)
        if result["status"] == "failed":
            report["counts"]["failed"] += 1
        else:
            report["counts"]["visited"] += 1
            if result["login_required"]:
                report["counts"]["login_required"] += 1
            else:
                report["counts"]["accessible"] += 1
        if result["risk_controls"]:
            report["counts"]["risk_controls_detected"] += 1

    report["status"] = "completed"
    return save_surface_exploration(report)


def save_surface_exploration(report: dict, path: Path | None = None) -> tuple[dict, Path]:
    EXPLORATION_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_EXPLORATION.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    target = path or EXPLORATION_DIR / f"google_surface_exploration_{timestamp}.json"
    report = _sanitize_obj(report)
    text = json.dumps(report, ensure_ascii=True, indent=2)
    target.write_text(text, encoding="utf-8")
    LATEST_EXPLORATION.write_text(text, encoding="utf-8")
    return report, target


def print_surface_exploration_summary(report: dict, path: Path) -> None:
    print("=" * 60)
    print("Google surface exploration")
    print("=" * 60)
    print(f"status: {report.get('status')}")
    print(f"mode: {report.get('mode')}")
    print(f"planned: {report['counts']['planned']}")
    print(f"visited: {report['counts']['visited']}")
    print(f"accessible: {report['counts']['accessible']}")
    print(f"login_required: {report['counts']['login_required']}")
    print(f"failed: {report['counts']['failed']}")
    print(f"risk_controls_detected: {report['counts']['risk_controls_detected']}")
    if report.get("warnings"):
        print("warnings:")
        for warning in report["warnings"]:
            print(f"- {warning}")
    for item in report["surfaces"]:
        marker = "login" if item["login_required"] else item["status"]
        print(f"- {item['key']}: {marker} controls={len(item['controls'])} risk={len(item['risk_controls'])}")
    print(f"saved: {path}")
    print(f"latest: {LATEST_EXPLORATION}")


def _visit_surface(page: Any, surface: dict, *, timeout_ms: int) -> dict:
    result = {
        "key": surface["key"],
        "label": surface["label"],
        "category": surface["category"],
        "catalog_url": surface["url"],
        "access_mode": surface["access_mode"],
        "catalog_risk": surface["risk"],
        "visited_at": datetime.now(UTC).isoformat(),
        "status": "started",
        "final_url": "",
        "title": "",
        "login_required": False,
        "headings": [],
        "inputs": [],
        "controls": [],
        "links": [],
        "risk_controls": [],
        "warnings": [],
    }
    try:
        _goto_readonly(page, surface["url"], timeout_ms=timeout_ms)
        page.wait_for_timeout(2000)
        result["final_url"] = page.url
        try:
            result["title"] = page.title()
        except Exception:  # noqa: BLE001 - 구글 서비스 화면 읽기전용 탐색기(로그인 필요 여부/위험버튼 분류) - 실패시 status=failed 기록, 쓰기 없음
            result["title"] = ""
        snapshot = _extract_surface_snapshot(page)
        result.update(snapshot)
        result["login_required"] = detect_login_required(
            result["final_url"],
            result["title"],
            snapshot.get("page_markers", []),
        )
        result["risk_controls"] = classify_risk_controls(snapshot.get("controls", []))
        result["status"] = "visited"
    except Exception as exc:  # noqa: BLE001 - 구글 서비스 화면 읽기전용 탐색기(로그인 필요 여부/위험버튼 분류) - 실패시 status=failed 기록, 쓰기 없음
        result["status"] = "failed"
        result["warnings"].append(str(exc))
    return result


def _new_isolated_page(base_page: Any) -> Any:
    try:
        return base_page.context.new_page()
    except Exception:  # noqa: BLE001 - 구글 서비스 화면 읽기전용 탐색기(로그인 필요 여부/위험버튼 분류) - 실패시 status=failed 기록, 쓰기 없음
        return base_page


def _goto_readonly(page: Any, url: str, *, timeout_ms: int) -> None:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            return
        except Exception as exc:  # noqa: BLE001 - 구글 서비스 화면 읽기전용 탐색기(로그인 필요 여부/위험버튼 분류) - 실패시 status=failed 기록, 쓰기 없음
            last_exc = exc
            if "interrupted by another navigation" not in str(exc) or attempt == 2:
                break
            with contextlib.suppress(Exception):
                page.wait_for_timeout(2500)
    if last_exc:
        raise last_exc


def _extract_surface_snapshot(page: Any) -> dict:
    script = """() => {
        const shown = (el) => {
          const s = getComputedStyle(el);
          const r = el.getBoundingClientRect();
          return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
        };
        const textOf = (el) => (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || '')
          .replace(/\\s+/g, ' ')
          .trim();
        const short = (value, n = 120) => (value || '').slice(0, n);
        const controls = Array.from(document.querySelectorAll(
          'button, [role="button"], input[type="button"], input[type="submit"], a[role="button"]'
        )).filter(shown).slice(0, 80).map((el) => ({
          text: short(textOf(el), 100),
          aria: short(el.getAttribute('aria-label'), 100),
          title: short(el.getAttribute('title'), 100),
          tag: el.tagName.toLowerCase(),
          role: short(el.getAttribute('role'), 40)
        }));
        const inputs = Array.from(document.querySelectorAll('input, textarea, select'))
          .filter(shown).slice(0, 60).map((el) => ({
            type: short(el.getAttribute('type') || el.tagName.toLowerCase(), 40),
            name: short(el.getAttribute('name'), 80),
            placeholder: short(el.getAttribute('placeholder'), 100),
            aria: short(el.getAttribute('aria-label'), 100)
          }));
        const links = Array.from(document.querySelectorAll('a[href]')).filter(shown).slice(0, 80).map((el) => ({
          text: short(textOf(el), 100),
          href: short(el.href, 180)
        }));
        const headings = Array.from(document.querySelectorAll('h1,h2,h3,[role="heading"]'))
          .filter(shown).slice(0, 30).map((el) => short(textOf(el), 120));
        const body = (document.body?.innerText || '').replace(/\\s+/g, ' ').trim();
        return {
          headings,
          inputs,
          controls,
          links,
          page_markers: [
            short(document.title, 120),
            short(location.href, 180),
            short(body, 300)
          ].filter(Boolean)
        };
    }"""
    merged = {"headings": [], "inputs": [], "controls": [], "links": [], "page_markers": []}
    for frame in page.frames:
        try:
            data = frame.evaluate(script)
        except Exception:  # noqa: BLE001 - 구글 서비스 화면 읽기전용 탐색기(로그인 필요 여부/위험버튼 분류) - 실패시 status=failed 기록, 쓰기 없음
            continue
        for key in merged:
            merged[key].extend(data.get(key, []))
    merged["headings"] = _dedupe(merged["headings"], limit=30)
    merged["inputs"] = _dedupe_dicts(merged["inputs"], limit=60)
    merged["controls"] = _dedupe_dicts(merged["controls"], limit=80)
    merged["links"] = _dedupe_dicts(merged["links"], limit=80)
    merged["page_markers"] = _dedupe(merged["page_markers"], limit=20)
    return merged


def detect_login_required(url: str, title: str, markers: list[str]) -> bool:
    url_l = (url or "").lower()
    title_l = (title or "").lower()
    marker_text = " ".join(markers).lower()
    if "accounts.google.com" in url_l and any(
        token in url_l for token in ("signin", "servicelogin", "/identifier", "/challenge")
    ):
        return True
    if title_l.startswith("sign in") or title_l.startswith("\ub85c\uadf8\uc778"):
        return True
    return any(hint.lower() in marker_text for hint in LOGIN_HINTS)


def classify_risk_controls(controls: list[dict]) -> list[dict]:
    risk_controls: list[dict] = []
    for control in controls:
        haystack = " ".join(str(control.get(name, "")) for name in ("text", "aria", "title", "role")).lower()
        matched = [keyword for keyword in RISK_CONTROL_KEYWORDS if keyword.lower() in haystack]
        if matched:
            item = dict(control)
            item["matched_keywords"] = matched
            risk_controls.append(item)
    return risk_controls


def _dedupe(values: list[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
        if len(out) >= limit:
            break
    return out


def _dedupe_dicts(values: list[dict], *, limit: int) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
        if len(out) >= limit:
            break
    return out


def _sanitize_obj(value: Any) -> Any:
    if isinstance(value, str):
        return EMAIL_RE.sub("[email-redacted]", value)
    if isinstance(value, list):
        return [_sanitize_obj(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_obj(item) for key, item in value.items()}
    return value
