"""카페 상세 수집 결과(collector.py 산출물) → 시트별 분석 Excel 출력.

scripts/ops/export_cafe_keywords_excel.py 의 스타일 컨벤션(헤더 색상, 테두리,
하이퍼링크 처리)을 재사용한다. 입력 스키마가 달라(matched_kw/category 없음,
대신 view_count/like_count/comment_count/body/comments) 컬럼 구성은 새로 짰다.

시트 구성:
    전체요약      — 기간, 총계, 월별 분포, 조회수 TOP15, 댓글수 TOP15
    게시글목록    — 전체 게시글 1행 1건(제목 하이퍼링크 포함)
    댓글상세      — 상세 수집된 게시글의 댓글을 1행 1댓글로 펼친 목록(원글 하이퍼링크 포함)
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

# ── 스타일 (export_cafe_keywords_excel.py 와 동일 팔레트) ────────────────
H1_FILL = PatternFill("solid", fgColor="1F4E79")
H1_FONT = Font(color="FFFFFF", bold=True, size=10)
H2_FILL = PatternFill("solid", fgColor="2E75B6")
H2_FONT = Font(color="FFFFFF", bold=True, size=10)
THIN = Side(style="thin", color="BFBFBF")
BDR = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HLNK = Font(color="0563C1", underline="single", size=10)
BASE_FONT = Font(size=10)
YELLOW = PatternFill("solid", fgColor="FFFACD")
GREEN = PatternFill("solid", fgColor="E8F5E9")
ORANGE = PatternFill("solid", fgColor="FFF3E0")

_Q_WORDS = ["?", "질문", "궁금", "어떻게", "어디서", "얼마", "어떤", "가능한가요", "되나요", "맞나요", "인가요", "부탁"]
_AD_WORDS = ["홍보", "모집", "강의", "학원", "교육", "무료", "안내드립니다", "알려드립니다", "구인", "구합니다"]


def _classify_type(title: str) -> str:
    if any(w in title for w in _Q_WORDS):
        return "질문"
    if any(w in title for w in _AD_WORDS):
        return "홍보/구인"
    return "정보/경험"


def _num(value: Any) -> int:
    try:
        return int(str(value or "0").replace(",", ""))
    except ValueError:
        return 0


def _hdr(ws: Worksheet, row: int, cols: list[str], fill: PatternFill, font: Font, height: int = 22) -> None:
    for ci, val in enumerate(cols, 1):
        c = ws.cell(row=row, column=ci, value=val)
        c.fill, c.font = fill, font
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BDR
    ws.row_dimensions[row].height = height


def _article_row(ws: Worksheet, row: int, rank: Any, a: dict[str, Any]) -> None:
    title = a.get("title", "")
    body = (a.get("body") or "").replace("\n", " ").strip()
    href = a.get("href", "")
    vals = [
        rank,
        a.get("date", ""),
        _classify_type(title),
        title,
        _num(a.get("view_count")),
        _num(a.get("like_count")),
        _num(a.get("comment_count")),
        len(a.get("comments") or []),
        body[:200],
        "링크" if href else "",
    ]
    for ci, val in enumerate(vals, 1):
        c = ws.cell(row=row, column=ci, value=val)
        c.border = BDR
        c.font = BASE_FONT
        c.alignment = Alignment(vertical="center", wrap_text=(ci in (4, 9)))
    type_cell = ws.cell(row=row, column=3)
    fill = YELLOW if type_cell.value == "질문" else (ORANGE if type_cell.value == "홍보/구인" else GREEN)
    type_cell.fill = fill
    if href:
        lc = ws.cell(row=row, column=10, value="링크")
        lc.hyperlink, lc.font = href, HLNK


def _write_article_list_sheet(ws: Worksheet, articles: list[dict[str, Any]]) -> None:
    cols = ["No", "날짜", "유형", "제목", "조회수", "좋아요", "댓글수", "댓글로드", "본문요약", "링크"]
    _hdr(ws, 1, cols, H2_FILL, H2_FONT)
    ordered = sorted(articles, key=lambda a: a.get("date", ""), reverse=True)
    for i, a in enumerate(ordered, 1):
        _article_row(ws, i + 1, i, a)
    widths = [5, 12, 10, 50, 9, 8, 8, 9, 46, 6]
    for ci, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.freeze_panes = "A2"


def _write_comment_detail_sheet(ws: Worksheet, articles: list[dict[str, Any]]) -> None:
    cols = ["게시글날짜", "게시글제목", "게시글링크", "댓글작성자", "댓글날짜", "댓글내용"]
    _hdr(ws, 1, cols, H2_FILL, H2_FONT)
    row = 2
    for a in sorted(articles, key=lambda x: x.get("date", ""), reverse=True):
        comments = a.get("comments") or []
        href = a.get("href", "")
        for cm in comments:
            vals = [
                a.get("date", ""),
                a.get("title", ""),
                "링크" if href else "",
                cm.get("author", ""),
                cm.get("date", ""),
                cm.get("text", ""),
            ]
            for ci, val in enumerate(vals, 1):
                c = ws.cell(row=row, column=ci, value=val)
                c.border = BDR
                c.font = BASE_FONT
                c.alignment = Alignment(vertical="center", wrap_text=(ci in (2, 6)))
            if href:
                lc = ws.cell(row=row, column=3, value="링크")
                lc.hyperlink, lc.font = href, HLNK
            row += 1
    widths = [12, 46, 6, 14, 16, 60]
    for ci, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.freeze_panes = "A2"


def _write_summary_sheet(ws: Worksheet, articles: list[dict[str, Any]], cafe_label: str) -> None:
    ws.merge_cells("A1:J1")
    c = ws["A1"]
    c.value = f"{cafe_label} — 게시글 분석 요약"
    c.font = Font(bold=True, size=15, color="1F4E79")
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32

    dates = [a.get("date", "") for a in articles if a.get("date")]
    period = f"{min(dates)} ~ {max(dates)}" if dates else "N/A"
    with_detail = [a for a in articles if a.get("comments") is not None]
    total_comments_loaded = sum(len(a.get("comments") or []) for a in articles)
    ws["A2"] = (
        f"수집 기간: {period}  |  총 {len(articles)}건  |  상세조사 완료 {len(with_detail)}건  |  로드된 댓글 {total_comments_loaded}건"
    )
    ws.merge_cells("A2:J2")
    ws["A2"].font = Font(italic=True, color="595959", size=10)
    ws["A2"].alignment = Alignment(horizontal="center")

    type_c = Counter(_classify_type(a.get("title", "")) for a in articles)
    r = 4
    _hdr(ws, r, ["유형", "건수", "비율"], H1_FILL, H1_FONT)
    r += 1
    for t, cnt in type_c.most_common():
        ws.cell(row=r, column=1, value=t).border = BDR
        ws.cell(row=r, column=2, value=cnt).border = BDR
        pct = ws.cell(row=r, column=3, value=f"{cnt / len(articles) * 100:.1f}%")
        pct.border = BDR
        pct.alignment = Alignment(horizontal="center")
        r += 1
    r += 1

    def _write_ranked_block(title: str, key: str, top_n: int, start_row: int) -> int:
        ws.merge_cells(f"A{start_row}:J{start_row}")
        ws.cell(row=start_row, column=1, value=title).font = Font(bold=True, size=12, color="C00000")
        ws.row_dimensions[start_row].height = 24
        row = start_row + 1
        _hdr(
            ws,
            row,
            ["No", "날짜", "유형", "제목", "조회수", "좋아요", "댓글수", "댓글로드", "본문요약", "링크"],
            H1_FILL,
            H1_FONT,
        )
        row += 1
        ranked = sorted(articles, key=lambda a: _num(a.get(key)), reverse=True)[:top_n]
        for i, a in enumerate(ranked, 1):
            _article_row(ws, row, i, a)
            row += 1
        return row + 1

    r = _write_ranked_block("🔥  조회수 TOP 15", "view_count", 15, r)
    r = _write_ranked_block("💬  댓글수 TOP 15", "comment_count", 15, r)

    widths = [5, 12, 10, 50, 9, 8, 8, 9, 46, 6]
    for ci, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.freeze_panes = "A5"


def build_cafe_excel_report(
    articles: list[dict[str, Any]],
    out_path: str | Path,
    *,
    cafe_label: str = "카페",
) -> Path:
    """articles(collector.py 산출 dict 목록) → 시트별 분석 Excel 파일 생성.

    시트: 전체요약 / 게시글목록 / 댓글상세(상세조사로 댓글이 로드된 글만).
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws_summary = wb.active
    ws_summary.title = "전체요약"
    _write_summary_sheet(ws_summary, articles, cafe_label)

    ws_list = wb.create_sheet("게시글목록")
    _write_article_list_sheet(ws_list, articles)

    ws_comments = wb.create_sheet("댓글상세")
    detailed = [a for a in articles if a.get("comments")]
    _write_comment_detail_sheet(ws_comments, detailed)

    wb.save(out)
    return out
