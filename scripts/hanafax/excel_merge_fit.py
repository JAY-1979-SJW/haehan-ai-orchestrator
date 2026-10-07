"""Excel(COM) 병합+줄바꿈 셀 높이 맞춤 공용 함수 — KRAS 팩스 공문 PDF 내보내기용.

export_kras_fax_pdf.py 와 send_kras_final_campaign.py 가 똑같이 복사해 두던
_calibrate_col_width_for_points·_fit_merged_wrap_rows 본문을 한 곳으로 모았다(win32com 등 무거운 import 없음 —
워크시트 객체만 받아 다룬다).
"""

from __future__ import annotations

SCRATCH_ROW = 500  # 콘텐츠(최대 60행)보다 훨씬 아래, 인쇄영역 밖 — 계산용 임시 행
SCRATCH_COL = 100  # 콘텐츠(최대 39열)보다 훨씬 오른쪽 — 계산용 임시 열


def calibrate_col_width_for_points(ws, col: int, target_pts: float) -> None:
    """지정 열의 ColumnWidth(문자단위)를 목표 폭(포인트)에 최대한 맞춘다.

    ColumnWidth(문자단위)→Width(포인트) 변환은 폰트에 따라 비선형이 아니라
    선형(오프셋+기울기)이라, 두 점을 찍어 직선 보정한다.
    """
    ws.Columns(col).ColumnWidth = 10
    w1 = ws.Cells(1, col).Width
    ws.Columns(col).ColumnWidth = 100
    w2 = ws.Cells(1, col).Width
    slope = (w2 - w1) / (100 - 10)
    intercept = w1 - slope * 10
    if slope == 0:
        return
    cw = (target_pts - intercept) / slope
    ws.Columns(col).ColumnWidth = max(1, cw)


def fit_merged_wrap_rows(ws) -> None:
    """세로 병합 + 줄바꿈 셀의 실제 필요 높이를 계산해서 적용.

    실측 확인된 결론: Excel Range.AutoFit()/Rows.AutoFit() 은 **병합된
    범위 자체에서는 병합 여부와 무관하게 줄바꿈 높이를 계산하지 못한다**
    (스크래치를 병합해서 측정해도 항상 1줄 높이만 나옴 — 병합이 계산을
    막는 것 자체가 원인). 반면 병합하지 않은 단일 셀은 정상 계산된다
    (실측: 동일 텍스트가 병합 스크래치에서는 15pt, 비병합 단일 셀에서는
    올바르게 43.5pt). 그래서 병합을 절대 쓰지 않고, 목표 폭에 맞춰 열
    너비를 보정한 단일 셀로 필요 높이를 구한다.

    주의: **병합을 유지한 채** 하위 행 높이만 늘리면 텍스트가 겹쳐 보이는
    렌더링 결함이 실측 확인됐다(재병합 없이 RowHeight만 조정한 1차 시도).
    그래서 대상은 먼저 병합을 해제하고, 행 높이를 맞춘 뒤, 값·서식을
    보존한 채 다시 병합하는 순서로 처리한다.
    """
    used = ws.UsedRange
    r0, nrows = used.Row, used.Rows.Count

    # 1) 처리 대상 병합 영역을 먼저 전부 수집(순회 중 UnMerge 하면 인덱스가
    #    바뀌므로 목록을 확정한 뒤 별도로 처리한다).
    targets = []
    handled: set[str] = set()
    for r in range(r0, r0 + nrows):
        for c in range(used.Column, used.Column + used.Columns.Count):
            cell = ws.Cells(r, c)
            if not cell.MergeCells:
                continue
            ma = cell.MergeArea
            addr = ma.Address
            if addr in handled:
                continue
            handled.add(addr)
            if not ma.WrapText:
                continue
            # 실측: Rows.AutoFit()은 1행 병합에도 제대로 안 먹는다(문단7
            # 사례 — 3줄 텍스트가 기본 행높이에서 그대로 잘림). 병합이면
            # 행 수와 무관하게 전부 아래 로직으로 처리한다.
            targets.append(
                {
                    "row0": ma.Row,
                    "rows": ma.Rows.Count,
                    "col0": ma.Column,
                    "cols": ma.Columns.Count,
                    # ma.Value(다중셀 Range)는 2D 튜플을 반환해 그대로 스크래치에
                    # 넣으면 잘못 채워진다(실측 버그 원인) — 병합 실제 텍스트는
                    # 항상 좌상단 셀 1개에만 들어있으므로 단일 셀 값을 쓴다.
                    "value": ws.Cells(ma.Row, ma.Column).Value,
                    "font_name": ma.Font.Name,
                    "font_size": ma.Font.Size,
                    "font_bold": ma.Font.Bold,
                    "h_align": ma.HorizontalAlignment,
                    "v_align": ma.VerticalAlignment,
                }
            )

    for t in targets:
        m_row0, m_rows, m_col0, m_ncols = t["row0"], t["rows"], t["col0"], t["cols"]

        # 필요 높이 계산 — 병합을 전혀 쓰지 않는 단일 셀로 측정한다.
        target_width_pts = ws.Range(ws.Cells(1, m_col0), ws.Cells(1, m_col0 + m_ncols - 1)).Width
        calibrate_col_width_for_points(ws, SCRATCH_COL, target_width_pts)
        scratch = ws.Cells(SCRATCH_ROW, SCRATCH_COL)
        scratch.WrapText = True
        scratch.Font.Name = t["font_name"]
        scratch.Font.Size = t["font_size"]
        scratch.Font.Bold = t["font_bold"]
        scratch.Value = t["value"]
        ws.Rows(SCRATCH_ROW).AutoFit()
        required_h = ws.Rows(SCRATCH_ROW).RowHeight
        scratch.ClearContents()
        ws.Columns(SCRATCH_COL).ColumnWidth = 8.43  # Excel 기본값으로 원복

        # 2) 병합 해제 → 행 높이 조정 → 재병합 (병합 유지 상태 리사이즈는
        #    텍스트 중복 렌더링 결함이 있어 사용하지 않는다).
        target_range = ws.Range(ws.Cells(m_row0, m_col0), ws.Cells(m_row0 + m_rows - 1, m_col0 + m_ncols - 1))
        target_range.UnMerge()

        current_total = sum(ws.Rows(rr).RowHeight for rr in range(m_row0, m_row0 + m_rows))
        if current_total < required_h:
            deficit = required_h - current_total
            last_row = m_row0 + m_rows - 1
            ws.Rows(last_row).RowHeight = ws.Rows(last_row).RowHeight + deficit

        target_range.Merge()
        target_range.Value = t["value"]
        target_range.WrapText = True
        target_range.HorizontalAlignment = t["h_align"]
        target_range.VerticalAlignment = t["v_align"]
        target_range.Font.Name = t["font_name"]
        target_range.Font.Size = t["font_size"]
        target_range.Font.Bold = t["font_bold"]
