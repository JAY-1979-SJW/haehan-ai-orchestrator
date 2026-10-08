"""Read-only exploration for Hiworks business service surfaces."""

from __future__ import annotations

import json
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.hiworks.explorer import open_hiworks
from scripts.hiworks.schemas import DATA_DIR, SERVICE_TARGETS
from scripts.site_engine.catalog_helpers import select_named_targets


def selected_targets(name: str | None = None) -> dict[str, dict[str, str]]:
    return select_named_targets(SERVICE_TARGETS, name, "Hiworks service")


def extract_service_surface(page, *, limit: int = 120) -> dict[str, Any]:
    """Extract visible structure only. No clicks or form submission."""
    return page.evaluate(
        """(limit) => {
          const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
          const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
          const links = Array.from(document.querySelectorAll('a[href]')).map((el) => ({
            text: clean(el.innerText || el.textContent).slice(0, 160),
            href: el.href || '',
            visible: visible(el)
          })).filter((x) => x.visible && (x.text || x.href)).slice(0, limit);
          const buttons = Array.from(document.querySelectorAll('button, [role=button]')).map((el) => ({
            text: clean(el.innerText || el.textContent || el.getAttribute('aria-label')).slice(0, 120),
            type: el.getAttribute('type') || '',
            visible: visible(el),
            disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true'
          })).filter((x) => x.visible && x.text).slice(0, limit);
          const inputs = Array.from(document.querySelectorAll('input, textarea, select')).map((el) => ({
            tag: el.tagName.toLowerCase(),
            type: el.type || '',
            name: el.name || '',
            id: el.id || '',
            placeholder: el.placeholder || '',
            aria: el.getAttribute('aria-label') || '',
            visible: visible(el),
            disabled: !!el.disabled,
            readonly: !!el.readOnly
          })).filter((x) => x.visible).slice(0, limit);
          const headings = Array.from(document.querySelectorAll('h1,h2,h3,[role=heading]')).map((el) => (
            clean(el.innerText || el.textContent).slice(0, 120)
          )).filter(Boolean).slice(0, 40);
          return {
            url: location.href,
            title: document.title,
            headings,
            counts: {
              links: document.querySelectorAll('a[href]').length,
              buttons: document.querySelectorAll('button, [role=button]').length,
              inputs: document.querySelectorAll('input, textarea, select').length,
              tables: document.querySelectorAll('table').length,
              forms: document.querySelectorAll('form').length
            },
            links,
            buttons,
            inputs
          };
        }""",
        limit,
    )


def scan_service(key: str, target: dict[str, str], *, limit: int = 120) -> dict[str, Any]:
    page = open_hiworks(target["url"])
    with suppress(Exception):
        page.wait_for_timeout(1200)
    surface = extract_service_surface(page, limit=limit)
    return {
        "key": key,
        "label": target["label"],
        "target_url": target["url"],
        "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "surface": surface,
    }


def save_service_report(results: list[dict[str, Any]], output: str | Path | None = None) -> Path:
    path = Path(output) if output else DATA_DIR / "hiworks_service_surfaces_latest.json"
    path.write_text(
        json.dumps(
            {"generated_at": datetime.now().isoformat(timespec="seconds"), "services": results},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def print_service_summary(results: list[dict[str, Any]], path: Path | None = None) -> None:
    print("=" * 60)
    print("Hiworks service surfaces")
    print("=" * 60)
    for result in results:
        surface = result.get("surface") or {}
        counts = surface.get("counts") or {}
        print(f"- {result['key']} ({result['label']})")
        print(f"  url: {surface.get('url')}")
        print(f"  title: {surface.get('title')}")
        print(
            "  counts: "
            f"links={counts.get('links', 0)} "
            f"buttons={counts.get('buttons', 0)} "
            f"inputs={counts.get('inputs', 0)} "
            f"tables={counts.get('tables', 0)}"
        )
    if path:
        print(f"saved: {path}")
