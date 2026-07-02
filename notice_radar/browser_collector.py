from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .models import AttachmentResult, NoticeCandidate

ATTACHMENT_EXTENSIONS = {".pdf", ".hwp", ".hwpx", ".xlsx", ".xlsm", ".zip", ".docx"}
DEFAULT_CDP_URL = "http://127.0.0.1:9222"


def collect_current_browser_page(
    *,
    cdp_url: str = DEFAULT_CDP_URL,
    title: str | None = None,
    source: str = "current-browser",
    target_url_contains: str | None = None,
) -> tuple[NoticeCandidate, object]:
    """Attach to the user's already-open browser and collect the current notice tab.

    The browser must be launched with remote debugging enabled, for example:
    chrome.exe --remote-debugging-port=9222 --user-data-dir=.../chrome-profile
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        try:
            page = _pick_current_page(browser, target_url_contains=target_url_contains)
            if page is None:
                raise RuntimeError("No usable browser tab found through CDP")
            page.wait_for_load_state("domcontentloaded", timeout=10_000)
            html = page.content()
            url = page.url
            page_title = title or page.title() or url
            text = _visible_text(page)
            links = _extract_attachment_links(page, url)
            candidate = NoticeCandidate(
                title=page_title,
                source=source,
                url=url,
                posted_at=_find_near_date(text, ["등록", "공고", "게시"]),
                deadline=_find_near_date(text, ["마감", "신청기간", "접수기간", "까지"]),
                page_text=text or _html_to_text(html),
                attachment_urls=links,
            )
            return candidate, page
        except Exception:
            browser.close()
            raise


def download_current_browser_attachments(candidate: NoticeCandidate, page: object, output_dir: str | Path) -> list[AttachmentResult]:
    """Download discovered attachment links using the current browser context cookies."""
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    results: list[AttachmentResult] = []
    context = page.context

    for idx, url in enumerate(candidate.attachment_urls, start=1):
        try:
            response = context.request.get(url, timeout=45_000)
            if not response.ok:
                raise RuntimeError(f"HTTP {response.status}")
            body = response.body()
            filename = _safe_filename(_filename_from_headers(url, response.headers, idx))
            file_path = target_dir / filename
            file_path.write_bytes(body)
            results.append(
                AttachmentResult(
                    filename=filename,
                    path=str(file_path),
                    source_url=url,
                    content_type=response.headers.get("content-type"),
                    size_bytes=len(body),
                )
            )
        except Exception as exc:
            results.append(
                AttachmentResult(
                    filename=f"browser_download_failed_{idx}",
                    path="",
                    source_url=url,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return results


def _pick_current_page(browser: object, target_url_contains: str | None = None):
    pages = []
    for context in browser.contexts:
        pages.extend(context.pages)
    usable = [page for page in pages if page.url and page.url != "about:blank"]
    if target_url_contains:
        matched = [page for page in usable if target_url_contains in page.url]
        if matched:
            return matched[-1]
    focused = []
    for page in usable:
        try:
            if page.evaluate("() => document.hasFocus()"):
                focused.append(page)
        except Exception:
            continue
    if focused:
        return focused[-1]
    return usable[-1] if usable else None


def _visible_text(page: object) -> str:
    try:
        text = page.locator("body").inner_text(timeout=5_000)
    except Exception:
        text = ""
    return re.sub(r"\s+", " ", text).strip()[:300_000]


def _extract_attachment_links(page: object, base_url: str) -> list[str]:
    raw_links = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('a[href], button, input[type="button"], input[type="submit"]')).map((el) => ({
          tag: el.tagName,
          href: el.getAttribute('href') || '',
          download: el.getAttribute('download') || '',
          onclick: el.getAttribute('onclick') || '',
          text: (el.innerText || el.value || el.title || '').trim()
        }))
        """
    )
    links: list[str] = []
    for item in raw_links:
        href = (item.get("href") or "").strip()
        text = " ".join(str(item.get(key) or "") for key in ("href", "download", "onclick", "text")).lower()
        if href and _looks_like_attachment(href, text):
            absolute = urljoin(base_url, href)
            if absolute not in links:
                links.append(absolute)
    return links


def _looks_like_attachment(href: str, haystack: str) -> bool:
    path = urlparse(href).path.lower()
    if any(path.endswith(ext) for ext in ATTACHMENT_EXTENSIONS):
        return True
    return any(token in haystack for token in ["download", "file", "attach", "첨부", "다운로드", "공고문", "신청서", "서식"])


def _html_to_text(html: str) -> str:
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()[:300_000]


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


def _filename_from_headers(url: str, headers: dict, idx: int) -> str:
    disposition = headers.get("content-disposition", "") or headers.get("Content-Disposition", "")
    if disposition:
        match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, flags=re.I)
        if match:
            return match.group(1)
    path_name = Path(urlparse(url).path).name
    return path_name or f"attachment_{idx}.bin"


def _safe_filename(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._- 가-힣()[]" else "_" for ch in name)
    return cleaned[:160] or "attachment.bin"
