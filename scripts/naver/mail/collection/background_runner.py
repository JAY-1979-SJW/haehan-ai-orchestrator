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
from typing import Any

from scripts.common.app_paths import repo_root

ROOT = repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.browser.session.browser_cdp_selection_gate import (  # noqa: E402 - sys.path 조정 뒤 import (이 파일의 기존 구조)
    create_isolated_target,
    select_naver_session,
)
from scripts.naver.mail import folder_discovery as fd
from scripts.naver.mail.read import cdp, list_collector  # noqa: E402 - sys.path 조정 뒤 import (이 파일의 기존 구조)
from scripts.naver.mail.utilities import settings_panel  # noqa: E402 - sys.path 조정 뒤 import (이 파일의 기존 구조)


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


def create_isolated_mail_target(*, port: int) -> tuple[str, dict[str, Any]]:
    report = create_isolated_target(
        task="naver",
        work="mail:background",
        port=port,
        start_url="https://mail.naver.com/",
    )
    if not report.ok or not report.target_id:
        return "", {}
    cdp.wait_dom(report.target_id, "location.href.includes('mail.naver.com')", timeout=15.0, port=port)
    return report.target_id, report.page


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

    target_id, page = create_isolated_mail_target(port=session.port)
    if not target_id:
        return BackgroundReport(
            ok=False,
            code="no_mail_target",
            port=session.port,
            messages=["Could not create an isolated Naver Mail CDP target tab."],
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
        messages=[
            "Created an isolated tab in the existing Naver CDP session; no browser launch, restart, close, or state-changing action."
        ],
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
