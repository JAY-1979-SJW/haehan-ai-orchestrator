"""
scripts/hanafax/send_kras_final_campaign.py

최종 확정 PDF 양식(해한AI_AI안전관리시스템_영업공문_최종.xlsx, 2p A4)을
업체별로 개인화(수신/제목 셀 치환)해서 PDF로 뽑고 하나팩스로 실제 발송한다.

대상: g2b 스캔 결과 safety_doc_targets_*.json (bizno, corp_nm, contract_name, fax_no)

Excel 인스턴스를 한 번만 열어두고 셀 2개(B5 수신, B8 제목)만 매 건 갈아끼워
ExportAsFixedFormat 하는 방식 — 매번 새로 열면 1,840건 기준 감당 안 됨.

사용:
    python scripts/hanafax/send_kras_final_campaign.py --limit 2 --send   # 스모크테스트
    python scripts/hanafax/send_kras_final_campaign.py --send            # 전체 발송
    python scripts/hanafax/send_kras_final_campaign.py                   # dry-run (발송 없음, 목록만)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import shutil
import tempfile
import time
from pathlib import Path

import fitz
import win32com.client as win32

from scripts.common.app_paths import known_folder, repo_root
from scripts.hanafax.excel_merge_fit import fit_merged_wrap_rows as _fit_merged_wrap_rows
from scripts.hanafax.kst_date import now_kst, today_kr_str
from scripts.hanafax.sender import send_fax

log = logging.getLogger("hanafax.kras_final_campaign")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ROOT = repo_root()
SRC_XLSX = str(known_folder("downloads") / "해한AI_AI안전관리시스템_영업공문_최종.xlsx")
DATA_JSON = ROOT / "data" / "safety_doc_targets_20260907.json"
MASTER_SENT_LOG = ROOT / "data" / "kras_pdf_fax_sent_log.json"
SENT_LOG = MASTER_SENT_LOG
SUBJECT = "귀사만을 위한 AI 안전관리시스템 안내"

KEEP_SHEETS = ["1_제안공문", "2_법령참고"]
DROP_SHEETS = ["근거자료"]
XL_PAPER_A4 = 9
XL_PORTRAIT = 1
A4_WIDTH_PT = 595.32
A4_HEIGHT_PT = 841.92
A4_TOLERANCE_PT = 3.0


def _load_log() -> dict:
    return json.loads(SENT_LOG.read_text(encoding="utf-8")) if SENT_LOG.exists() else {}


def _save_log(d: dict) -> None:
    SENT_LOG.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_a4(src_pdf: str, out_pdf: str) -> None:
    doc = fitz.open(src_pdf)
    for page in doc:
        w, h = page.rect.width, page.rect.height
        if abs(w - A4_WIDTH_PT) <= A4_TOLERANCE_PT and abs(h - A4_HEIGHT_PT) <= A4_TOLERANCE_PT:
            continue
        max_x = max_y = 0.0
        for block in page.get_text("blocks"):
            _x0, _y0, x1, y1 = block[:4]
            max_x, max_y = max(max_x, x1), max(max_y, y1)
        if max_x > A4_WIDTH_PT + A4_TOLERANCE_PT or max_y > A4_HEIGHT_PT + A4_TOLERANCE_PT:
            raise RuntimeError(
                f"페이지 {page.number + 1}: {w:.1f}x{h:.1f}pt인데 콘텐츠가 "
                f"({max_x:.1f},{max_y:.1f})까지 있어 A4를 벗어남 — 프린터 기본값 확인 필요"
            )
        page.set_mediabox(fitz.Rect(0, 0, A4_WIDTH_PT, A4_HEIGHT_PT))
    doc.save(out_pdf)
    doc.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="처리 건수 상한 (0=전체, 워커 슬라이스 내에서)")
    ap.add_argument("--send", action="store_true", help="실제 발송 (없으면 dry-run)")
    ap.add_argument("--force", action="store_true", help="이미 성공 기록된 bizno도 재발송")
    ap.add_argument("--worker-id", type=int, default=0, help="병렬 워커 번호 (0부터)")
    ap.add_argument("--num-workers", type=int, default=1, help="병렬 워커 총 개수")
    args = ap.parse_args()

    global SENT_LOG
    if args.num_workers > 1:
        # 워커별로 로그 파일을 분리한다 — 여러 프로세스가 같은 json을
        # 동시에 읽고 쓰면(파일 락 없음) 서로의 기록을 덮어써 발송이력이
        # 유실될 수 있어서다. bizno % num_workers 로 대상 자체도
        # 겹치지 않게 나누므로 워커 간 조정(락)이 애초에 필요 없다.
        SENT_LOG = ROOT / "data" / f"kras_pdf_fax_sent_log_w{args.worker_id}.json"

    data = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    rows = [r for r in data["data"] if r.get("fax_no")]
    log.info("대상 %d개 업체 중 팩스번호 보유 %d개", len(data["data"]), len(rows))

    if args.num_workers > 1:
        rows = [r for i, r in enumerate(rows) if i % args.num_workers == args.worker_id]
        log.info("워커 %d/%d 담당 슬라이스: %d개", args.worker_id, args.num_workers, len(rows))

    if not args.send:
        log.info("dry-run — 실제 발송하지 않습니다.")
        for r in rows[: args.limit or 10]:
            print(f"  {r['corp_nm']} ({r['bizno']}) fax={r['fax_no']} 공사={r.get('contract_name')}")
        return

    sent_log = _load_log()
    if args.num_workers > 1 and MASTER_SENT_LOG.exists():
        # 워커 로그 분리 전(단일 프로세스 시절)에 이미 성공한 9건 등 마스터
        # 로그 이력은 워커별 로그에 없으므로, "이미 보냈나" 확인용으로만
        # 병합해 넣는다(저장은 여전히 워커 파일에만 — 마스터는 안 건드림).
        master = json.loads(MASTER_SENT_LOG.read_text(encoding="utf-8"))
        for k, v in master.items():
            sent_log.setdefault(k, v)

    targets = rows[: args.limit] if args.limit else rows

    tmp_dir = Path(tempfile.mkdtemp(prefix="kras_campaign_"))

    def _make_pdf(corp_nm: str, contract_name: str, bizno: str) -> str:
        """PDF 1건 생성 — 매 건마다 Excel을 새로 열고 닫는다.

        실측: Excel COM 인스턴스를 열어둔 채 Playwright(send_fax)를 여러 번
        반복 호출하니 "RPC 서버를 사용할 수 없습니다" 로 3건째에 Excel이
        죽었다(같은 프로세스 안에서 무거운 브라우저 자동화와 장시간 떠있는
        COM 서버가 충돌하는 것으로 추정). 매번 새로 열고 export 직후 바로
        닫아 Excel 수명을 Playwright 호출과 완전히 분리한다 — 건당
        3~5초 더 걸리지만(전체가 어차피 팩스 전송 시간이 지배적이라
        영향 적음) 훨씬 안정적이다.
        """
        tmp_xlsx = str(tmp_dir / f"{bizno}_work.xlsx")
        shutil.copy(SRC_XLSX, tmp_xlsx)
        excel = win32.gencache.EnsureDispatch("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        wb = excel.Workbooks.Open(tmp_xlsx)
        try:
            for name in DROP_SHEETS:
                # 임시 엑셀 시트 삭제 cleanup 단계 — 실패해도 실제 팩스발송(send_fax) 로직은 이 부분과 무관
                with contextlib.suppress(Exception):
                    wb.Sheets(name).Delete()

            content_addrs = {}
            for name in KEEP_SHEETS:
                ws = wb.Sheets(name)
                ws.ResetAllPageBreaks()
                content_addrs[name] = ws.UsedRange.Address
                ws.Rows.AutoFit()
                _fit_merged_wrap_rows(ws)
                ps = ws.PageSetup
                ps.Orientation = XL_PORTRAIT
                ps.PaperSize = XL_PAPER_A4
                ps.FitToPagesWide = 1
                ps.FitToPagesTall = 1
                ps.Zoom = False
                ps.TopMargin = excel.InchesToPoints(0.3)
                ps.BottomMargin = excel.InchesToPoints(0.3)
                ps.LeftMargin = excel.InchesToPoints(0.3)
                ps.RightMargin = excel.InchesToPoints(0.3)
                ps.HeaderMargin = excel.InchesToPoints(0.1)
                ps.FooterMargin = excel.InchesToPoints(0.1)
                ps.CenterHeader = ps.CenterFooter = ps.LeftHeader = ""
                ps.RightHeader = ps.LeftFooter = ps.RightFooter = ""
                ps.PrintGridlines = False
                ps.PrintHeadings = False
                ps.PrintArea = content_addrs[name]

            ws1 = wb.Sheets("1_제안공문")
            ws1.Cells(5, 2).Value = f"수신 : {corp_nm} 대표이사 귀하"
            ws1.Cells(8, 2).Value = f"제목 : 「{contract_name}」 관련 AI 안전관리시스템 구축 제안"
            # 캠페인이 하루 이상 걸려(약 30시간) 날짜가 바뀌므로, 소스 xlsx에
            # 박제된 날짜(AH1, 예: "2026. 09. 07.")를 쓰지 않고 매 건 발송
            # 시점의 실제 KST 날짜로 채운다 (scripts/hanafax/kst_date.py 정본).
            ws1.Cells(1, 34).Value = today_kr_str()

            tmp_pdf = str(tmp_dir / f"{bizno}_raw.pdf")
            wb.ExportAsFixedFormat(0, tmp_pdf)
        finally:
            wb.Close(SaveChanges=False)
            excel.Quit()
            Path(tmp_xlsx).unlink(missing_ok=True)

        final_pdf = str(tmp_dir / f"{bizno}.pdf")
        _ensure_a4(tmp_pdf, final_pdf)
        Path(tmp_pdf).unlink(missing_ok=True)
        return final_pdf

    n_ok = n_fail = n_skip = 0
    try:
        for i, r in enumerate(targets):
            bizno = r["bizno"]
            if not args.force and sent_log.get(bizno, {}).get("success"):
                n_skip += 1
                continue

            contract_name = r.get("contract_name") or "귀사 수주 현장"
            final_pdf = _make_pdf(r["corp_nm"], contract_name, bizno)

            result = send_fax(
                receiver_fax=r["fax_no"],
                subject=SUBJECT,
                body="",
                receiver_name=r["corp_nm"],
                bid_name=contract_name,
                attach_file=final_pdf,
            )

            sent_log[bizno] = {
                "corp_nm": r["corp_nm"],
                "fax_no": r["fax_no"],
                "contract_name": contract_name,
                "success": result.get("success", False),
                "message": result.get("message"),
                "job_id": result.get("job_id"),
                "sent_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S"),
            }
            _save_log(sent_log)

            if result.get("success"):
                n_ok += 1
                log.info(
                    "[%d/%d 성공] %s (%s) job_id=%s",
                    i + 1,
                    len(targets),
                    r["corp_nm"],
                    r["fax_no"],
                    result.get("job_id"),
                )
            else:
                n_fail += 1
                log.warning(
                    "[%d/%d 실패] %s (%s): %s", i + 1, len(targets), r["corp_nm"], r["fax_no"], result.get("message")
                )

            # 발송후 임시 PDF 삭제 cleanup 단계 — 실패해도 실제 팩스발송(send_fax) 로직은 이 부분과 무관
            with contextlib.suppress(Exception):
                Path(final_pdf).unlink(missing_ok=True)

            time.sleep(2)

        log.info("완료: 성공 %d건 / 실패 %d건 / 스킵(기발송) %d건", n_ok, n_fail, n_skip)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
