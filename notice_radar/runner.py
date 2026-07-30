from __future__ import annotations

from .pipeline import analyze_notice_folder, analyze_notice_url


def run_url(url: str, source: str = "public-notice", title: str | None = None):
    return analyze_notice_url(url, source=source, title=title)


def run_folder(folder: str, title: str, source: str = "local-folder"):
    return analyze_notice_folder(folder, title=title, source=source)
