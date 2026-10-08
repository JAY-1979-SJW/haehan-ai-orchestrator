"""견적서 Excel 실시간 완전 연동 (win32com).

GetActiveObject 로 이미 열려 있는 Excel 인스턴스에 직접 접근.
서식·값·행높이·열너비·A4 인쇄 설정 모두 layout_engine 에 위임.

사용법:
    python scripts/eum/excel_live.py
    python scripts/eum/excel_live.py --recipient "(주)아람정보통신 박원서 대표님" --months 24
    python scripts/eum/excel_live.py --watch
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import win32com.client as win32

from ai_orchestrator.audit.audit_logger import log_event
from scripts.eum.shared.layout_engine import (
    print_verify,
    render,
    update_values,
    verify_layout,
)
from scripts.eum.shared.layout_schema import ITEM_START, OUTPUT_DIR

# ── Excel 연결 ────────────────────────────────────────────────────────────────


def _connect(hint: str = "견적서"):
    try:
        xl = win32.GetActiveObject("Excel.Application")
    except Exception:  # noqa: BLE001 - 엑셀 실시간 연동 스크립트(로컬 PC 작업, 견적서 갱신) -- Excel 미실행 시 RuntimeError 발생시켜 상위로 전파(무시 아님), 라이브 루프 중 개별 계산 오류는 콘솔 출력 후 다음 주기에 계속
        raise RuntimeError("Excel이 실행 중이지 않습니다.")
    for i in range(1, xl.Workbooks.Count + 1):
        wb = xl.Workbooks(i)
        if hint in wb.Name:
            return xl, wb.Sheets(1)
    return xl, xl.ActiveWorkbook.ActiveSheet


# ── 서식 전체 적용 (layout_engine 위임) ──────────────────────────────────────


def apply_full_format(ws, xl_app) -> None:
    print("[format] 서식 적용 시작...")
    render(ws, xl_app)
    result = verify_layout(ws)
    print_verify(result)
    if not result.passed:
        raise RuntimeError("서식 자가검증 실패 — 위 오류를 확인하세요.")


# ── 감시 모드 ─────────────────────────────────────────────────────────────────


def watch_mode(interval: float, recipient: str) -> None:
    xl, ws = _connect()
    apply_full_format(ws, xl)
    update_values(ws, recipient)
    print("\n[live] 감시 시작 (Ctrl+C 종료) — 수량/개월 셀 변경 시 자동 재계산")

    prev = None
    mo1 = mo2 = 24
    while True:
        try:
            qty1 = int(ws.Cells(ITEM_START, 4).Value or 1)
            qty2 = int(ws.Cells(ITEM_START + 1, 4).Value or 1)
            qty3 = int(ws.Cells(ITEM_START + 2, 4).Value or 1)
            v6_r1 = ws.Cells(ITEM_START, 6).Value or ""
            v6_r2 = ws.Cells(ITEM_START + 1, 6).Value or ""
            if "개월" in str(v6_r1):
                mo1 = int(str(v6_r1).replace("개월", "").strip())
            if "개월" in str(v6_r2):
                mo2 = int(str(v6_r2).replace("개월", "").strip())
            rec = ws.Cells(4, 2).Value or recipient

            cur = (qty1, mo1, qty2, mo2, qty3, rec)
            if cur != prev:
                print("\n[live] 변경 감지 → 재계산")
                update_values(ws, rec, qty1, mo1, qty2, mo2, qty3)
                prev = cur
        except Exception as e:  # noqa: BLE001 - 엑셀 실시간 연동 스크립트(로컬 PC 작업, 견적서 갱신) -- Excel 미실행 시 RuntimeError 발생시켜 상위로 전파(무시 아님), 라이브 루프 중 개별 계산 오류는 콘솔 출력 후 다음 주기에 계속
            print(f"[live] 오류: {e}")
        time.sleep(interval)


# ── 1회 적용 ─────────────────────────────────────────────────────────────────


def one_shot(args) -> None:
    xl, ws = _connect()
    apply_full_format(ws, xl)
    print("\n[값 갱신]")
    update_values(
        ws,
        args.recipient,
        qty1=args.qty1,
        mo1=args.months,
        qty2=args.qty2,
        mo2=args.months,
        qty3=args.qty3,
    )

    # 단말기 견적서 폴더에 저장
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe = args.recipient.replace(" ", "_").replace("/", "_")[:30]
    from datetime import date

    fname = f"견적서_{safe}_{date.today().strftime('%Y%m%d')}.xlsx"
    out = OUTPUT_DIR / fname
    ws.Parent.SaveAs(str(out))
    print(f"\n[저장] {out}")
    log_event(
        "EUM_QUOTE_GENERATE",
        task_id="-",
        actor="excel_live",
        decision="ok",
        note=f"recipient={args.recipient} qty1={args.qty1} mo1={args.months} qty2={args.qty2} mo2={args.months} qty3={args.qty3} saved={fname}",
    )
    print(f"[done] '{ws.Parent.Name}' — 서식 + 값 + A4 설정 + 저장 완료")


# ── 진입점 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="견적서 Excel 실시간 완전 연동")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--recipient", type=str, default="(주)아람정보통신  박원서  대표님")
    p.add_argument("--months", type=int, default=24)
    p.add_argument("--qty1", type=int, default=1)
    p.add_argument("--qty2", type=int, default=1)
    p.add_argument("--qty3", type=int, default=1)
    args = p.parse_args()

    if args.watch:
        watch_mode(args.interval, args.recipient)
    else:
        one_shot(args)
