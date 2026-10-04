from __future__ import annotations

import json

from scripts.naver import excel_reports


def test_build_excel_report_from_latest_json_sources(tmp_path):
    seo = tmp_path / "seo.json"
    shopping = tmp_path / "shopping.json"
    seo.write_text(
        json.dumps({"site_url": "https://haehan-ai.kr", "phases": [{"id": "p1", "actions": ["a"]}]}),
        encoding="utf-8",
    )
    shopping.write_text(
        json.dumps({"query": "AI 업무 자동화", "items": [{"title": "A", "lprice": 10000}]}),
        encoding="utf-8",
    )
    out = tmp_path / "report.xlsx"

    result = excel_reports.build_excel_report(
        output=out,
        sources={
            "seo_plan": seo,
            "seo_assets": shopping,
            "seo_ownership": seo,
            "seo_exposure": shopping,
            "seo_submit_plan": seo,
            "seo_monitor": shopping,
            "shopping": shopping,
        },
    )

    assert result["ok"] is True
    assert out.exists()
    assert "summary" in result["sheets"]
    assert "seo_plan" in result["sheets"]
    assert "seo_assets" in result["sheets"]
    assert "seo_ownership" in result["sheets"]
    assert "seo_exposure" in result["sheets"]
    assert "seo_submit_plan" in result["sheets"]
    assert "seo_monitor" in result["sheets"]
    assert "shopping" in result["sheets"]


# test_attach_files_requires_existing_files_and_compose_page · test_parse_attach_files_accepts_semicolon_list 는
# cb9d0ea3("코드맵 S1 미도달 파일 삭제")로 scripts/naver/mail_write.py(attach_files·_parse_attach_files)가 삭제돼 2026-10-05 제거
