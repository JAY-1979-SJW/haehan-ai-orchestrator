from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AttachmentResult:
    """Downloaded or locally discovered notice attachment."""

    filename: str
    path: str
    source_url: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    parser: str | None = None
    text: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NoticeCandidate:
    """A public notice page before attachment parsing."""

    title: str
    source: str
    url: str
    posted_at: str | None = None
    deadline: str | None = None
    page_text: str = ""
    attachment_urls: list[str] = field(default_factory=list)

    def safe_folder_name(self) -> str:
        raw = f"{self.posted_at or 'undated'}_{self.title or self.source}".strip()
        safe = "".join(ch if ch.isalnum() or ch in "._- 가-힣" else "_" for ch in raw)
        safe = "_".join(safe.split())
        return safe[:120] or "notice"


@dataclass
class NoticeDocument:
    """A notice page and all text extracted from its attachments."""

    candidate: NoticeCandidate
    attachments: list[AttachmentResult] = field(default_factory=list)

    @property
    def combined_text(self) -> str:
        parts = [self.candidate.title, self.candidate.page_text]
        for attachment in self.attachments:
            if attachment.text:
                parts.append(f"\n[첨부파일: {attachment.filename}]\n{attachment.text}")
        return "\n".join(part for part in parts if part)

    def attachment_paths(self) -> list[str]:
        return [str(Path(item.path)) for item in self.attachments]


@dataclass
class NoticeAnalysis:
    """Representative-focused business analysis result."""

    title: str
    source: str
    url: str
    posted_at: str | None
    deadline: str | None
    fit_score: int
    urgency: str
    action_required: bool
    summary: str
    business_fit: list[str] = field(default_factory=list)
    required_documents: list[str] = field(default_factory=list)
    eligibility_flags: dict[str, str] = field(default_factory=dict)
    risks: list[str] = field(default_factory=list)
    immediate_actions: list[str] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        def lines(title: str, items: list[str]) -> list[str]:
            if not items:
                return [f"## {title}", "- 해당 없음"]
            return [f"## {title}", *[f"- {item}" for item in items]]

        output: list[str] = [
            f"# {self.title}",
            "",
            f"- 출처: {self.source}",
            f"- URL: {self.url}",
            f"- 등록일: {self.posted_at or '미확인'}",
            f"- 마감: {self.deadline or '미확인'}",
            f"- 적합도: {self.fit_score}/100",
            f"- 긴급도: {self.urgency}",
            f"- 즉시 조치 필요: {'예' if self.action_required else '아니오'}",
            "",
            "## 핵심 요약",
            self.summary or "요약 없음",
            "",
        ]
        output.extend(lines("대표님 사업 적합 사유", self.business_fit))
        output.append("")
        output.extend(lines("제출서류", self.required_documents))
        output.append("")
        output.append("## 신청자격 판단")
        if self.eligibility_flags:
            output.extend([f"- {key}: {value}" for key, value in self.eligibility_flags.items()])
        else:
            output.append("- 미확인")
        output.append("")
        output.extend(lines("위험·주의사항", self.risks))
        output.append("")
        output.extend(lines("오늘 즉시 할 일", self.immediate_actions))
        return "\n".join(output).strip() + "\n"
