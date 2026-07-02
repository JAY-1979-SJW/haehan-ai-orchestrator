from __future__ import annotations

import json
from pathlib import Path

from .analyzer import analyze_document
from .collector import collect_notice_page, download_attachments
from .models import NoticeAnalysis, NoticeCandidate, NoticeDocument
from .parsers import parse_attachment


def analyze_notice_url(
    url: str,
    *,
    source: str = "public-notice",
    title: str | None = None,
    output_root: str | Path = "storage/notices",
) -> NoticeAnalysis:
    """Collect a notice URL, download attachments, parse files, and save reports."""
    candidate = collect_notice_page(url, source=source, title=title)
    notice_dir = Path(output_root) / candidate.safe_folder_name()
    notice_dir.mkdir(parents=True, exist_ok=True)

    (notice_dir / "notice_page.txt").write_text(candidate.page_text, encoding="utf-8")
    (notice_dir / "candidate.json").write_text(
        json.dumps(candidate.__dict__, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    downloaded = download_attachments(candidate, notice_dir / "attachments")
    parsed = []
    for item in downloaded:
        if item.path:
            parsed_item = parse_attachment(item.path)
            parsed_item.source_url = item.source_url
            parsed_item.content_type = item.content_type
            parsed_item.size_bytes = item.size_bytes
            parsed.append(parsed_item)
        else:
            parsed.append(item)

    document = NoticeDocument(candidate=candidate, attachments=parsed)
    analysis = analyze_document(document)
    _write_outputs(notice_dir, analysis)
    return analysis


def analyze_notice_folder(
    folder: str | Path,
    *,
    title: str,
    source: str = "local-folder",
    url: str = "local://notice-folder",
) -> NoticeAnalysis:
    """Analyze attachments already downloaded into a local folder."""
    folder_path = Path(folder)
    attachments = []
    page_text_parts: list[str] = []

    for path in sorted(folder_path.rglob("*")):
        if not path.is_file():
            continue
        if path.name in {"analysis.json", "summary.md", "candidate.json"}:
            continue
        if path.suffix.lower() in {".txt", ".md"} and path.name.startswith("notice"):
            page_text_parts.append(path.read_text(encoding="utf-8", errors="ignore"))
            continue
        attachments.append(parse_attachment(path))

    candidate = NoticeCandidate(
        title=title,
        source=source,
        url=url,
        page_text="\n".join(page_text_parts),
        attachment_urls=[],
    )
    document = NoticeDocument(candidate=candidate, attachments=attachments)
    analysis = analyze_document(document)
    _write_outputs(folder_path, analysis)
    return analysis


def _write_outputs(notice_dir: Path, analysis: NoticeAnalysis) -> None:
    notice_dir.mkdir(parents=True, exist_ok=True)
    (notice_dir / "analysis.json").write_text(
        json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (notice_dir / "summary.md").write_text(analysis.to_markdown(), encoding="utf-8")
