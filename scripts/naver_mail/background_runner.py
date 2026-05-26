"""Attach-only background runner for Naver Mail.

The runner never launches, restarts, or closes a browser. It discovers a
running CDP endpoint, attaches to a Naver Mail tab, and performs read/prepare
work only. State-changing actions remain behind the existing gates.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.browser_cdp_selection_gate import (
    CODE_MIXED_DOMAIN_SESSION,
    CdpSession,
    SelectionReport,
    discover_sessions,
    evaluate_sessions,
)
from scripts.naver.mail_read import cdp
from scripts.naver.mail_read import list_collector
from scripts.naver_mail import folder_discovery as fd
from scripts.naver_mail import settings_panel


@dataclass
class BackgroundReport:
    ok: bool
    code: str
    port: int | None = None
    target_id: str = ""
    url: str = ""
    title: str = ""
    mail_count: int = 0
    folder_kind_counts: dict[str, int] = field(default_factory=dict)
    settings_menus: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CdpActions:
    def __init__(self, target_id: str, *, port: int):
        self.target_id = target_id
        self.port = int(port)

    def evaluate(self, expr: str) -> Any:
        return cdp.evaluate(self.target_id, expr, timeout=8.0, port=self.port)

    def navigate(self, url: str) -> None:
        cdp.navigate(self.target_id, url, port=self.port)

    def wait_dom(self, expr_truthy: str, timeout_s: float = 8.0) -> bool:
        return cdp.wait_dom(self.target_id, expr_truthy, timeout=timeout_s, port=self.port)


def _pick_naver_session_when_readonly_mixed(
    selection: SelectionReport,
    sessions: Iterable[CdpSession],
) -> CdpSession | None:
    if selection.code != CODE_MIXED_DOMAIN_SESSION:
        return None
    for session in sessions:
        if any("naver.com" in page.host for page in session.pages):
            return session
    return None


def select_naver_session(
    *,
    sessions: Iterable[CdpSession] | None = None,
    allow_mixed_readonly: bool = False,
) -> tuple[CdpSession | None, SelectionReport]:
    discovered = list(sessions) if sessions is not None else discover_sessions()
    selection = evaluate_sessions("naver", discovered)
    if selection.ok and selection.selected_port is not None:
        for session in discovered:
            if session.port == selection.selected_port:
                return session, selection
    if allow_mixed_readonly:
        mixed_session = _pick_naver_session_when_readonly_mixed(selection, discovered)
        if mixed_session is not None:
            return mixed_session, selection
    return None, selection


def find_mail_target_id(*, port: int) -> tuple[str, dict[str, Any]]:
    pages = cdp.list_pages(port=port)
    for page in pages:
        url = str(page.get("url") or "")
        if "mail.naver.com" in url:
            return str(page.get("id") or ""), page
    for page in pages:
        url = str(page.get("url") or "")
        if "naver.com" in url:
            target_id = str(page.get("id") or "")
            if target_id:
                cdp.navigate(target_id, "https://mail.naver.com/", port=port)
                cdp.wait_dom(target_id, "location.href.includes('mail.naver.com')", timeout=15.0, port=port)
                return target_id, page
    return "", {}


def inspect_background(
    *,
    allow_mixed_readonly: bool = False,
    max_items: int = 30,
) -> BackgroundReport:
    session, selection = select_naver_session(allow_mixed_readonly=allow_mixed_readonly)
    if session is None:
        return BackgroundReport(
            ok=False,
            code=selection.code,
            messages=list(selection.messages),
            selection=selection.to_dict(),
        )

    target_id, page = find_mail_target_id(port=session.port)
    if not target_id:
        return BackgroundReport(
            ok=False,
            code="no_mail_target",
            port=session.port,
            messages=["No Naver Mail target tab was found."],
            selection=selection.to_dict(),
        )

    actions = CdpActions(target_id, port=session.port)
    folder_rows = actions.evaluate(fd.LNB_FOLDERS_EXPR) or []
    kind_counts: dict[str, int] = {}
    if isinstance(folder_rows, list):
        for row in folder_rows:
            kind = str((row or {}).get("kind") or "unknown")
            kind_counts[kind] = kind_counts.get(kind, 0) + 1

    items, meta = list_collector.collect_all_pages(target_id, max_pages=1, max_items=max_items)
    menus = [asdict(menu) for menu in settings_panel.list_settings_menus(actions)]
    return BackgroundReport(
        ok=True,
        code="ok",
        port=session.port,
        target_id=target_id,
        url=str(meta.get("href") or page.get("url") or ""),
        title=str(meta.get("title") or page.get("title") or ""),
        mail_count=len(items),
        folder_kind_counts=kind_counts,
        settings_menus=menus,
        messages=["Attached to existing Naver Mail CDP target; no browser launch or state-changing action."],
        selection=selection.to_dict(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run attach-only Naver Mail background inspection.")
    parser.add_argument("--allow-mixed-readonly", action="store_true")
    parser.add_argument("--max-items", type=int, default=30)
    args = parser.parse_args(argv)

    report = inspect_background(
        allow_mixed_readonly=args.allow_mixed_readonly,
        max_items=args.max_items,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
