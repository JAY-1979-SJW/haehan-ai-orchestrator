from __future__ import annotations

import contextlib
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from .collector import _find_near_date
from .models import AttachmentResult, NoticeCandidate

ATTACHMENT_EXTENSIONS = {".pdf", ".hwp", ".hwpx", ".xlsx", ".xlsm", ".zip", ".docx"}
DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DOWNLOAD_TEXT_TOKENS = [
    "download",
    "file",
    "attach",
    "attachment",
    "첨부",
    "다운로드",
    "내려받기",
    "공고문",
    "신청서",
    "서식",
    "양식",
    "붙임",
]


def collect_current_browser_page(
    *,
    cdp_url: str = DEFAULT_CDP_URL,
    title: str | None = None,
    source: str = "current-browser",
    target_url_contains: str | None = None,
) -> tuple[NoticeCandidate, Any]:
    """Attach to the user's already-open browser and collect the current notice tab."""
    from playwright.sync_api import sync_playwright

    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(cdp_url)
    page = _pick_current_page(browser, target_url_contains=target_url_contains)
    if page is None:
        browser.close()
        p.stop()
        raise RuntimeError("No usable browser tab found through CDP")

    # 공고 페이지 첨부파일/본문 읽기전용 수집기 - 실패시 빈 결과 또는 continue 로 안전 폴백, 쓰기 동작 없음
    with contextlib.suppress(Exception):
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
    # keep page/browser/playwright alive for browser-context downloads; caller closes.
    page._notice_radar_playwright = p  # type: ignore[attr-defined]
    return candidate, page


def download_current_browser_attachments(
    candidate: NoticeCandidate,
    page: Any,
    output_dir: str | Path,
    *,
    click_downloads: bool = True,
    max_clicks: int = 20,
) -> list[AttachmentResult]:
    """Download discovered attachments with current browser cookies and fallback clicks.

    Order:
    1. request.get() for href-based links using current browser context.
    2. click buttons/links that look like attachments and capture Playwright downloads.
    """
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    results: list[AttachmentResult] = []
    seen_paths: set[str] = set()

    for idx, url in enumerate(candidate.attachment_urls, start=1):
        item = _download_href_attachment(page, url, target_dir, idx)
        if item.path:
            seen_paths.add(item.path)
        results.append(item)

    if click_downloads:
        click_results = _download_by_clicking_candidates(
            page, target_dir, start_idx=len(results) + 1, max_clicks=max_clicks
        )
        for item in click_results:
            if item.path and item.path in seen_paths:
                continue
            if item.path:
                seen_paths.add(item.path)
            results.append(item)

    return results


def close_current_browser_collection(page: Any) -> None:
    """Close only the CDP connection, not the user's actual browser process."""
    try:
        browser = page.context.browser
        if browser:
            browser.close()
    except Exception:  # noqa: S110, BLE001 - 공고 페이지 첨부파일/본문 읽기전용 수집기 - 실패시 빈 결과 또는 continue 로 안전 폴백, 쓰기 동작 없음
        pass
    try:
        p = getattr(page, "_notice_radar_playwright", None)
        if p:
            p.stop()
    except Exception:  # noqa: S110, BLE001 - 공고 페이지 첨부파일/본문 읽기전용 수집기 - 실패시 빈 결과 또는 continue 로 안전 폴백, 쓰기 동작 없음
        pass


def _download_href_attachment(page: Any, url: str, target_dir: Path, idx: int) -> AttachmentResult:
    context = page.context
    try:
        response = context.request.get(url, timeout=45_000)
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status}")
        body = response.body()
        filename = _safe_filename(_filename_from_headers(url, response.headers, idx))
        file_path = _unique_path(target_dir / filename)
        file_path.write_bytes(body)
        return AttachmentResult(
            filename=file_path.name,
            path=str(file_path),
            source_url=url,
            content_type=response.headers.get("content-type"),
            size_bytes=len(body),
        )
    except Exception as exc:  # noqa: BLE001 - 공고 페이지 첨부파일/본문 읽기전용 수집기 - 실패시 빈 결과 또는 continue 로 안전 폴백, 쓰기 동작 없음
        return AttachmentResult(
            filename=f"browser_href_download_failed_{idx}",
            path="",
            source_url=url,
            error=f"{type(exc).__name__}: {exc}",
        )


def _download_by_clicking_candidates(
    page: Any, target_dir: Path, *, start_idx: int, max_clicks: int
) -> list[AttachmentResult]:
    locators = _candidate_download_locators(page)
    results: list[AttachmentResult] = []
    clicked = 0
    for locator in locators:
        if clicked >= max_clicks:
            break
        try:
            if not locator.is_visible(timeout=500):
                continue
        except Exception:  # noqa: BLE001, S112 - 공고 페이지 첨부파일/본문 읽기전용 수집기 - 실패시 빈 결과 또는 continue 로 안전 폴백, 쓰기 동작 없음
            continue
        clicked += 1
        try:
            with page.expect_download(timeout=8_000) as download_info:
                locator.click(timeout=3_000, force=False)
            download = download_info.value
            suggested = _safe_filename(download.suggested_filename or f"attachment_{start_idx + clicked - 1}.bin")
            file_path = _unique_path(target_dir / suggested)
            download.save_as(str(file_path))
            results.append(
                AttachmentResult(
                    filename=file_path.name,
                    path=str(file_path),
                    source_url="browser-click",
                    content_type=None,
                    size_bytes=file_path.stat().st_size if file_path.exists() else None,
                )
            )
            time.sleep(0.2)
        except Exception as exc:  # noqa: BLE001 - 공고 페이지 첨부파일/본문 읽기전용 수집기 - 실패시 빈 결과 또는 continue 로 안전 폴백, 쓰기 동작 없음
            results.append(
                AttachmentResult(
                    filename=f"browser_click_download_failed_{start_idx + clicked - 1}",
                    path="",
                    source_url="browser-click",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return results


def _candidate_download_locators(page: Any) -> list[Any]:
    selectors = [
        "a[download]",
        "a[href*='download' i]",
        "a[href*='file' i]",
        "a[href*='attach' i]",
        "a[href$='.pdf' i]",
        "a[href$='.hwp' i]",
        "a[href$='.hwpx' i]",
        "a[href$='.xlsx' i]",
        "a[href$='.zip' i]",
        "button",
        "input[type='button']",
        "input[type='submit']",
        "[role='button']",
    ]
    locators: list[Any] = []
    seen_keys: set[str] = set()
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 80)
        except Exception:  # noqa: BLE001, S112 - 공고 페이지 첨부파일/본문 읽기전용 수집기 - 실패시 빈 결과 또는 continue 로 안전 폴백, 쓰기 동작 없음
            continue
        for index in range(count):
            item = locator.nth(index)
            try:
                text = " ".join(
                    filter(
                        None,
                        [
                            item.inner_text(timeout=300)
                            if selector not in {"input[type='button']", "input[type='submit']"}
                            else "",
                            item.get_attribute("value", timeout=300) or "",
                            item.get_attribute("title", timeout=300) or "",
                            item.get_attribute("href", timeout=300) or "",
                            item.get_attribute("onclick", timeout=300) or "",
                            item.get_attribute("download", timeout=300) or "",
                            item.get_attribute("aria-label", timeout=300) or "",
                        ],
                    )
                )
            except Exception:  # noqa: BLE001, S112 - 공고 페이지 첨부파일/본문 읽기전용 수집기 - 실패시 빈 결과 또는 continue 로 안전 폴백, 쓰기 동작 없음
                continue
            haystack = text.lower()
            if not any(token in haystack for token in DOWNLOAD_TEXT_TOKENS) and not _has_attachment_extension(haystack):
                continue
            key = re.sub(r"\s+", " ", haystack).strip()[:300]
            if key in seen_keys:
                continue
            seen_keys.add(key)
            locators.append(item)
    return locators


def _pick_current_page(browser: Any, target_url_contains: str | None = None):
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
        except Exception:  # noqa: BLE001, S112 - 공고 페이지 첨부파일/본문 읽기전용 수집기 - 실패시 빈 결과 또는 continue 로 안전 폴백, 쓰기 동작 없음
            continue
    if focused:
        return focused[-1]
    return usable[-1] if usable else None


def _visible_text(page: Any) -> str:
    try:
        text = page.locator("body").inner_text(timeout=5_000)
    except Exception:  # noqa: BLE001 - 공고 페이지 첨부파일/본문 읽기전용 수집기 - 실패시 빈 결과 또는 continue 로 안전 폴백, 쓰기 동작 없음
        text = ""
    return re.sub(r"\s+", " ", text).strip()[:300_000]


def _extract_attachment_links(page: Any, base_url: str) -> list[str]:
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
    return any(token in haystack for token in DOWNLOAD_TEXT_TOKENS)


def _has_attachment_extension(text: str) -> bool:
    return any(ext in text.lower() for ext in ATTACHMENT_EXTENSIONS)


def _html_to_text(html: str) -> str:
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()[:300_000]


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


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{stem}_{int(time.time())}{suffix}")
