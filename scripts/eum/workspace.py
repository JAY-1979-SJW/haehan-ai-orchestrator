"""Read-only EUM work index builder.

This module turns the live EUM UI plus known WEBMAN targets into a compact
business map. It does not click buttons or submit forms.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
EUM_BASE = "https://eum.cw.or.kr"
WEBMAN_RE = re.compile(r"WEBMAN\d{3}M\d{2}", re.IGNORECASE)


WORKFLOWS: list[dict[str, Any]] = [
    {
        "key": "device_inventory",
        "aliases": ["extract", "inventory", "devices", "WEBMAN390M00"],
        "title": "Device install inventory",
        "code": "WEBMAN390M00",
        "risk": "read",
        "command": "python scripts/cdp_client.py eum extract",
        "auto_execute": True,
    },
    {
        "key": "new_sites",
        "aliases": ["new-sites", "newsites", "WEBMAN380M00"],
        "title": "New site discovery",
        "code": "WEBMAN380M00",
        "risk": "read",
        "command": "python scripts/cdp_client.py eum new-sites",
        "auto_execute": True,
    },
    {
        "key": "sales_mail",
        "aliases": ["sales-mail", "mail", "promo-mail"],
        "title": "Sales mail draft and queue preparation",
        "code": "WEBMAN370M00",
        "risk": "read",
        "command": "python scripts/cdp_client.py eum sales-mail",
        "auto_execute": True,
    },
    {
        "key": "device_history",
        "aliases": ["history", "device-history", "WEBMAN400M00"],
        "title": "Device history lookup",
        "code": "WEBMAN400M00",
        "risk": "read",
        "command": "python scripts/cdp_client.py eum history <device_id>",
        "auto_execute": True,
    },
    {
        "key": "demolition_lookup",
        "aliases": ["demolition", "remove-lookup", "WEBMAN382M00"],
        "title": "Removal/demolition lookup",
        "code": "WEBMAN382M00",
        "risk": "read",
        "command": "python scripts/cdp_client.py eum demolition",
        "auto_execute": True,
    },
    {
        "key": "device_registration",
        "aliases": ["registration", "register", "WEBMAN381M00"],
        "title": "Device registration",
        "code": "WEBMAN381M00",
        "risk": "approval",
        "command": "python scripts/cdp_client.py eum registration <project_code> <device_id> [location]",
        "auto_execute": False,
    },
    {
        "key": "device_deregistration",
        "aliases": ["deregistration", "deregister", "remove", "WEBMAN382M00"],
        "title": "Device deregistration/removal request",
        "code": "WEBMAN382M00",
        "risk": "approval",
        "command": "python scripts/cdp_client.py eum deregistration <device_id> [date]",
        "auto_execute": False,
    },
    {
        "key": "monitor",
        "aliases": ["monitor", "health"],
        "title": "Device usage monitor",
        "code": None,
        "risk": "read",
        "command": "python scripts/cdp_client.py eum monitor",
        "auto_execute": True,
    },
]

_APPROVAL_WORDS = (
    "apply",
    "register",
    "registration",
    "deregister",
    "remove",
    "delete",
    "cancel",
    "approve",
    "request",
    "WEBMAN381M00",
    "WEBMAN382M00",
)


def extract_webman_code(*values: Any) -> str | None:
    """Return the first WEBMAN page code found in arbitrary text values."""
    text = " ".join(str(v or "") for v in values)
    match = WEBMAN_RE.search(text)
    return match.group(0).upper() if match else None


def classify_work_risk(text: str = "", code: str | None = None) -> str:
    """Classify a UI item as read-only or approval/action risk."""
    haystack = f"{text or ''} {code or ''}".lower()
    for word in _APPROVAL_WORDS:
        if word.lower() in haystack:
            return "approval"
    return "read"


def known_webman_targets() -> list[dict[str, Any]]:
    """Load WEBMAN targets from the existing deep explorer without running it."""
    try:
        from scripts.eum.full_explorer import WEBMAN_TARGETS
    except Exception:
        WEBMAN_TARGETS = []

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for code, name in WEBMAN_TARGETS:
        code = str(code).upper()
        if code in seen:
            continue
        seen.add(code)
        rows.append(
            {
                "code": code,
                "name": str(name),
                "url": f"{EUM_BASE}/web/man/{code}",
                "risk": classify_work_risk(str(name), code),
            }
        )
    return rows


def workflow_for_alias(alias: str) -> dict[str, Any] | None:
    """Find a known workflow by key, alias, or WEBMAN code."""
    normalized = alias.strip().lower()
    for workflow in WORKFLOWS:
        values = [workflow["key"], *(workflow.get("aliases") or [])]
        if workflow.get("code"):
            values.append(workflow["code"])
        if normalized in {str(v).lower() for v in values}:
            return dict(workflow)
    return None


def print_workflow_help(alias: str) -> bool:
    """Print the command mapped to an EUM work alias."""
    workflow = workflow_for_alias(alias)
    if not workflow:
        print(f"No EUM workflow matched: {alias}")
        print("Known aliases:")
        for row in WORKFLOWS:
            aliases = ", ".join(str(v) for v in row.get("aliases", []))
            print(f"  - {row['key']}: {aliases}")
        return False

    print("=" * 60)
    print("EUM workflow")
    print("=" * 60)
    print(f"key: {workflow['key']}")
    print(f"title: {workflow['title']}")
    print(f"code: {workflow.get('code') or '-'}")
    print(f"risk: {workflow['risk']}")
    print(f"auto_execute: {bool(workflow.get('auto_execute'))}")
    print(f"command: {workflow['command']}")
    if workflow["risk"] != "read":
        print("note: approval/action workflow; gate confirmation is required before execution.")
    return True


def _visible_ui_snapshot(page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 &&
                    style.display !== 'none' && style.visibility !== 'hidden';
            };
            const textOf = (el) => (el.innerText || el.textContent || '')
                .replace(/\\s+/g, ' ').trim();
            const contextOf = (el) => {
                const parts = [];
                let node = el.parentElement;
                for (let i = 0; node && i < 5; i++, node = node.parentElement) {
                    const directHeads = Array.from(node.children || [])
                        .filter((child) => /^(H[1-6]|P)$/i.test(child.tagName) ||
                            /dep|title|menu|nav/i.test(child.className || ''))
                        .map(textOf)
                        .filter(Boolean);
                    for (const head of directHeads) parts.unshift(head);
                }
                return Array.from(new Set(parts)).join(' > ').slice(0, 160);
            };
            const items = [];
            document.querySelectorAll('a[href], button, input[type=button], input[type=submit], [onclick]')
                .forEach((el, index) => {
                    if (!visible(el)) return;
                    const text = textOf(el) || el.value || '';
                    const href = el.href || el.getAttribute('href') || '';
                    const onclick = el.getAttribute('onclick') || '';
                    if (!text && !href && !onclick) return;
                    items.push({
                        index,
                        tag: el.tagName.toLowerCase(),
                        text: String(text).slice(0, 160),
                        href: String(href).slice(0, 300),
                        onclick: String(onclick).slice(0, 300),
                        id: el.id || '',
                        className: String(el.className || '').slice(0, 120),
                        context: contextOf(el)
                    });
                });
            const tables = Array.from(document.querySelectorAll('table')).map((table, index) => ({
                index,
                rows: table.querySelectorAll('tr').length,
                headers: Array.from(table.querySelectorAll('th'))
                    .map(textOf).filter(Boolean).slice(0, 40)
            }));
            return {
                url: location.href,
                title: document.title,
                readyState: document.readyState,
                itemCount: items.length,
                items,
                tables
            };
        }"""
    )


def build_work_index(page) -> dict[str, Any]:
    """Build a read-only business map from the current logged-in EUM page."""
    from scripts.eum.navigation import available_webman_codes, extract_live_menu

    snapshot = _visible_ui_snapshot(page)
    live_menu = extract_live_menu(page)
    available_codes = available_webman_codes(live_menu)
    menu_items: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str, str]] = set()

    for item in snapshot.get("items", []):
        code = extract_webman_code(
            item.get("text"),
            item.get("href"),
            item.get("onclick"),
            item.get("context"),
        )
        label = item.get("text") or item.get("context") or item.get("href") or item.get("onclick")
        key = (code, str(label), str(item.get("href") or item.get("onclick") or ""))
        if key in seen:
            continue
        seen.add(key)
        menu_items.append(
            {
                "label": label,
                "code": code,
                "risk": classify_work_risk(str(label), code),
                "tag": item.get("tag"),
                "href": item.get("href"),
                "onclick": item.get("onclick"),
                "context": item.get("context"),
            }
        )

    workflows = []
    for workflow in WORKFLOWS:
        row = dict(workflow)
        code = row.get("code")
        if code:
            row["available"] = str(code).upper() in available_codes
        else:
            row["available"] = True
        workflows.append(row)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": EUM_BASE,
        "current_page": {
            "url": snapshot.get("url"),
            "title": snapshot.get("title"),
            "ready_state": snapshot.get("readyState"),
            "tables": snapshot.get("tables", []),
        },
        "known_workflows": workflows,
        "known_webman_targets": known_webman_targets(),
        "live_menu": live_menu,
        "available_webman_codes": sorted(available_codes),
        "menu_items": menu_items,
        "counts": {
            "known_workflows": len(WORKFLOWS),
            "known_webman_targets": len(known_webman_targets()),
            "live_menu": len(live_menu),
            "available_webman_codes": len(available_codes),
            "menu_items": len(menu_items),
            "approval_items": sum(1 for item in menu_items if item.get("risk") == "approval"),
        },
    }


def save_work_index(index: dict[str, Any], path: Path | None = None) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = path or (DATA_DIR / "eum_work_index.json")
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def print_summary(index: dict[str, Any], path: Path | None = None) -> None:
    counts = index.get("counts", {})
    print("=" * 60)
    print("EUM work index")
    print("=" * 60)
    print(f"current: {index.get('current_page', {}).get('url')}")
    print(f"workflows: {counts.get('known_workflows', 0)}")
    print(f"webman targets: {counts.get('known_webman_targets', 0)}")
    print(f"live menu items: {counts.get('live_menu', 0)}")
    print(f"available WEBMAN codes: {counts.get('available_webman_codes', 0)}")
    print(f"visible menu/action items: {counts.get('menu_items', 0)}")
    print(f"approval-risk items: {counts.get('approval_items', 0)}")
    if path:
        print(f"saved: {path}")
    print("\nKnown workflows:")
    for workflow in index.get("known_workflows", []):
        available = "available" if workflow.get("available", True) else "not-available"
        print(f"  - {workflow['key']:<22} {workflow['risk']:<8} {available:<13} {workflow['command']}")
