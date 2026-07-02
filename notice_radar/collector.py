from __future__ import annotations

import mimetypes
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from .models import AttachmentResult, NoticeCandidate

ATTACHMENT_EXTENSIONS = {".pdf", ".hwp", ".hwpx", ".xlsx", ".xlsm", ".zip", ".docx"}


class AttachmentLinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() != "a":
            return
        attrs_dict = {key.lower(): value for key, value in attrs if value}
        href = attrs_dict.get("href")
        if not href:
            return
        url = urljoin(self.base_url, href)
        parsed_path = urlparse(url).path.lower()
        if any(parsed_path.endswith(ext) for ext in ATTACHMENT_EXTENSIONS) or "download" in href.lower():
            if url not in self.links:
                self.links.append(url)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data.strip()


def collect_notice_page(url: str, source: str = "public-notice", title: str | None = None) -> NoticeCandidate:
    """Collect a notice page with Playwright when available, otherwise HTTP."""
    html = _fetch_rendered_html(url)
    parser = AttachmentLinkParser(url)
    parser.feed(html)
    text = _html_to_text(html)
    return NoticeCandidate(
        title=title or parser.title or _guess_title(text) or url,
        source=source,
        url=url,
        posted_at=_find_near_date(text, ["등록", "공고", "게시"]),
        deadline=_find_near_date(text, ["마감", "신청기간", "접수기간", "까지"]),
        page_text=text,
        attachment_urls=parser.links,
    )


def download_attachments(candidate: NoticeCandidate, output_dir: str | Path) -> list[AttachmentResult]:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    results: list[AttachmentResult] = []

    with httpx.Client(follow_redirects=True, timeout=45.0) as client:
        for idx, url in enumerate(candidate.attachment_urls, start=1):
            try:
                response = client.get(url)
                response.raise_for_status()
                filename = _filename_from_response(url, response.headers.get("content-disposition"), idx)
                file_path = target_dir / filename
                file_path.write_bytes(response.content)
                results.append(
                    AttachmentResult(
                        filename=filename,
                        path=str(file_path),
                        source_url=url,
                        content_type=response.headers.get("content-type"),
                        size_bytes=len(response.content),
                    )
                )
            except Exception as exc:
                results.append(
                    AttachmentResult(
                        filename=f"download_failed_{idx}",
                        path="",
                        source_url=url,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
    return results


def _fetch_rendered_html(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=45_000)
            html = page.content()
            browser.close()
            return html
    except Exception:
        with httpx.Client(follow_redirects=True, timeout=45.0) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text


def _html_to_text(html: str) -> str:
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:300_000]


def _guess_title(text: str) -> str | None:
    if not text:
        return None
    return text[:120]


def _filename_from_response(url: str, content_disposition: str | None, idx: int) -> str:
    if content_disposition:
        match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", content_disposition, flags=re.I)
        if match:
            return _safe_filename(match.group(1))
    path_name = Path(urlparse(url).path).name
    if path_name:
        return _safe_filename(path_name)
    ext = mimetypes.guess_extension("application/octet-stream") or ".bin"
    return f"attachment_{idx}{ext}"


def _safe_filename(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._- 가-힣()[]" else "_" for ch in name)
    return cleaned[:160] or "attachment.bin"


def _find_near_date(text: str, markers: list[str]) -> str | None:
    date_re = re.compile(r"(20\d{2})[.\-/년 ]\s*(\d{1,2})[.\-/월 ]\s*(\d{1,2})")
    candidates: list[tuple[int, str]] = []
    for match in date_re.finditer(text):
        window = text[max(0, match.start() - 80): min(len(text), match.end() + 80)]
        score = sum(1 for marker in markers if marker in window)
        y, m, d = match.groups()
        candidates.append((score, f"{int(y):04d}-{int(m):02d}-{int(d):02d}"))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][1]
