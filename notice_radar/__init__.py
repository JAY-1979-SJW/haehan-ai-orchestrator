"""
Government notice radar for haehan-ai-orchestrator.

This package collects public notice pages, downloads attachments, extracts
text from common government file formats, and produces a representative-fit
analysis for CAD/AI/construction/fire-safety business opportunities.
"""

from .models import AttachmentResult, NoticeAnalysis, NoticeCandidate, NoticeDocument
from .pipeline import analyze_notice_folder, analyze_notice_url

__all__ = [
    "AttachmentResult",
    "NoticeAnalysis",
    "NoticeCandidate",
    "NoticeDocument",
    "analyze_notice_folder",
    "analyze_notice_url",
]
