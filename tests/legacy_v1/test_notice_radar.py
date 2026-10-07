from __future__ import annotations

import zipfile
from pathlib import Path

from openpyxl import Workbook

from orchestrator_v1.inbox.notice_radar.analyzer import analyze_document
from orchestrator_v1.inbox.notice_radar.models import NoticeCandidate, NoticeDocument
from orchestrator_v1.inbox.notice_radar.parsers import parse_attachment
from orchestrator_v1.inbox.notice_radar.pipeline import analyze_notice_folder


def test_xlsx_parser_extracts_application_terms(tmp_path: Path):
    path = tmp_path / "공고서식.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "제출서류"
    ws.append(["사업계획서", "신청서", "국세", "지방세"])
    wb.save(path)

    parsed = parse_attachment(path)

    assert parsed.error is None
    assert "사업계획서" in parsed.text
    assert "국세" in parsed.text


def test_hwpx_parser_extracts_xml_text(tmp_path: Path):
    path = tmp_path / "공고문.hwpx"
    xml = "<root><p>스마트도시 실증 구매 사업</p><p>CAD 도면 AI 자동화</p></root>"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Contents/section0.xml", xml)

    parsed = parse_attachment(path)

    assert parsed.error is None
    assert "스마트도시" in parsed.text
    assert "CAD" in parsed.text


def test_analyzer_scores_representative_business_fit():
    candidate = NoticeCandidate(
        title="스마트도시 실증 구매 프로젝트",
        source="K-Startup",
        url="https://example.test/notice",
        page_text="2026년 7월 22일까지 신청. 스마트도시 실증 구매 공공기관 수요처 AI CAD 도면 소방 안전 자동화 사업계획서 신청서 개인사업자 법인 기술자료 성과물",
    )
    document = NoticeDocument(candidate=candidate, attachments=[])

    analysis = analyze_document(document)

    assert analysis.fit_score >= 70
    assert analysis.action_required is True
    assert any("스마트도시" in item for item in analysis.business_fit)
    assert "사업계획서" in analysis.required_documents
    assert any("기술" in item for item in analysis.risks)


def test_folder_pipeline_writes_outputs(tmp_path: Path):
    notice = tmp_path / "notice_page.txt"
    notice.write_text("스마트도시 실증 구매 공고 2026.07.22까지 AI CAD 도면 자동화 사업계획서", encoding="utf-8")

    analysis = analyze_notice_folder(tmp_path, title="스마트도시 공고")

    assert analysis.title == "스마트도시 공고"
    assert (tmp_path / "analysis.json").exists()
    assert (tmp_path / "summary.md").exists()
