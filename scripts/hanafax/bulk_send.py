"""하나팩스 대량팩스 자동화 스크립트.

fax_common_v3.xlsx 단일 파일을 배치JSON의 팩스번호 목록에 대량 발송.

배치 파일: C:/work/05. g2b/exports/개별팩스/batches/batch_01.json ~ batch_05.json
팩스 파일: C:/work/05. g2b/exports/개별팩스/fax_common_v3.xlsx

실행:
    python scripts/hanafax/bulk_send.py [--batch 1] [--dry-run]
    python scripts/hanafax/bulk_send.py --all       # 전체 5배치 순차 발송
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger("hanafax.bulk_send")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # 단독 실행 시에도 scripts 패키지를 import 할 수 있게
    sys.path.insert(0, str(ROOT))
from scripts.common.app_paths import resolve_external, sibling_project  # noqa: E402

G2B_BASE = resolve_external("HAEHAN_FAX_EXPORT_DIR", "exports", "개별팩스", base=sibling_project("05. g2b"))
FAX_FILE = G2B_BASE / "fax_common_v3.xlsx"
BATCH_DIR = G2B_BASE / "batches"
RESULT_DIR = ROOT / "data" / "hanafax_bulk_results"
BASE_URL = "https://www.hanafax.com"
BULK_PAGE = f"{BASE_URL}/HanaFax/tHanaFax_manysenddata.asp"


# ── 자격증명 ──────────────────────────────────────────────────────────────────


def _get_creds() -> tuple[str, str]:
    from scripts.hanafax.auth import get_credentials

    return get_credentials()


# ── 배치 로드 ─────────────────────────────────────────────────────────────────


def load_batch(batch_num: int) -> dict:
    path = BATCH_DIR / f"batch_{batch_num:02d}.json"
    if not path.exists():
        raise FileNotFoundError(f"배치 파일 없음: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


# ── 결과 저장 ─────────────────────────────────────────────────────────────────


def save_result(batch_num: int, result: dict) -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULT_DIR / f"bulk_batch_{batch_num:02d}_{stamp}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("결과 저장: %s", path)


# ── Playwright 대량발송 ────────────────────────────────────────────────────────


def send_bulk_batch(
    batch_num: int,
    fax_numbers: list[str],
    dry_run: bool = False,
    uid: str = "",
    pwd: str = "",
) -> dict:
    """단일 배치를 하나팩스 대량발송 페이지로 발송."""

    if not FAX_FILE.exists():
        return {"ok": False, "error": f"팩스 파일 없음: {FAX_FILE}"}

    if dry_run:
        log.info("[DRY-RUN] 배치%d %d건 발송 시뮬레이션", batch_num, len(fax_numbers))
        return {
            "ok": True,
            "dry_run": True,
            "batch": batch_num,
            "count": len(fax_numbers),
            "message": "dry-run 완료 (실제 발송 없음)",
        }

    try:
        from playwright.sync_api import TimeoutError as PWTimeout
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "error": "playwright 미설치. pip install playwright && playwright install chromium"}

    log.info("배치%d 발송 시작: %d건", batch_num, len(fax_numbers))
    start_t = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # 문제 디버깅을 위해 유두 모드로 실행
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            locale="ko-KR",
        )
        page = context.new_page()
        dialogs: list[str] = []

        def _handle_dialog(d):
            msg = d.message
            dialogs.append(msg)
            log.info("[DIALOG] %s", msg[:200])
            d.dismiss()  # 모든 다이얼로그 dismiss (재시도 흐름에서 처리)

        page.on("dialog", _handle_dialog)

        try:
            # ── STEP 1: 로그인 ──────────────────────────────────────────────
            log.info("로그인 중...")
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20_000)
            page.fill('input[name="struid"]', uid)
            page.fill('input[name="strpwd"]', pwd)
            page.evaluate("document.querySelector('form').submit()")
            page.wait_for_load_state("domcontentloaded", timeout=15_000)
            page.wait_for_timeout(1_500)

            if not any(c["name"] == "Login" for c in context.cookies()):
                return {"ok": False, "error": f"로그인 실패. URL: {page.url}"}
            log.info("로그인 성공")

            # ── STEP 2: 대량팩스 페이지로 이동 ────────────────────────────
            log.info("대량팩스 페이지 이동...")
            page.evaluate(f"location.href='{BULK_PAGE}'")
            page.wait_for_load_state("domcontentloaded", timeout=15_000)
            page.wait_for_timeout(2_000)

            if "manysenddata" not in page.url:
                return {"ok": False, "error": f"대량팩스 페이지 이동 실패: {page.url}"}
            log.info("대량팩스 페이지 도달: %s", page.url)

            # ── STEP 3: 파일 업로드 ────────────────────────────────────────
            log.info("파일 업로드: %s", FAX_FILE)
            _fax_file_str = str(FAX_FILE).replace("\\", "/")

            # file input에 직접 파일 설정 (onchange 트리거됨)
            file_input = page.locator("#file_search_multi")
            file_input.set_input_files(str(FAX_FILE))
            log.info("파일 선택 완료, TIF 변환 대기...")

            # ── STEP 4: TIF 변환 완료 대기 (file_convert_finish == 1) ──────
            converted = False
            for attempt in range(30):  # 최대 60초 대기
                page.wait_for_timeout(2_000)
                state = page.evaluate("""
                    () => ({
                        finish: window.file_convert_finish,
                        pcnt: document.faxsubmit ? document.faxsubmit.pcnt.value : null,
                        attafiles: document.faxsubmit ? document.faxsubmit.attafiles.value : null,
                    })
                """)
                log.info("변환상태 [%d/30]: finish=%s pcnt=%s", attempt + 1, state.get("finish"), state.get("pcnt"))
                if state.get("finish") == 1 and state.get("pcnt") and int(state.get("pcnt") or 0) > 0:
                    converted = True
                    page_count = int(state["pcnt"])
                    log.info("TIF 변환 완료: %d페이지", page_count)
                    break

            if not converted:
                return {"ok": False, "error": "TIF 변환 타임아웃 (60초)"}

            # ── STEP 5: 팩스번호 주입 ──────────────────────────────────────
            log.info("팩스번호 주입 중: %d건", len(fax_numbers))

            # faddList에 번호 주입 (p| 접두사 포함)
            # personCntArr도 함께 설정
            inject_js = """
                (nums) => {
                    var sel = document.faxsubmit.faddList;
                    sel.options.length = 0;
                    window.personCntArr = [];
                    for (var i = 0; i < nums.length; i++) {
                        var n = nums[i].replace(/[^0-9]/g, '');
                        sel.options[i] = new Option(n, 'p|' + n);
                        window.personCntArr[i] = 1;
                    }
                    // refreshRcvList() 대신 직접 설정 (pcount + submitfaxnumber)
                    var sfaxNum = nums.map(function(n){ return 'p|' + n.replace(/[^0-9]/g,''); }).join(',');
                    document.faxsubmit.submitfaxnumber.value = sfaxNum;
                    document.faxsubmit.pcount.value = nums.length;
                    return {
                        faddLen: sel.options.length,
                        pcount: document.faxsubmit.pcount.value,
                        submitfaxnumber_len: document.faxsubmit.submitfaxnumber.value.split(',').length
                    };
                }
            """
            inject_result = page.evaluate(inject_js, fax_numbers)
            log.info("번호 주입 결과: faddLen=%s pcount=%s", inject_result.get("faddLen"), inject_result.get("pcount"))

            if inject_result.get("faddLen") != len(fax_numbers):
                return {
                    "ok": False,
                    "error": f"팩스번호 주입 불일치: {inject_result}",
                }

            # ── STEP 6: 발송 버튼 클릭 (e_money_chk → submitrepeatdel → form submit) ──
            log.info("발송 버튼 클릭...")
            dialogs.clear()

            # attafiles 설정 확인 (파일명이 set되어 있어야 함)
            att_check = page.evaluate("""
                () => {
                    var fform = document.faxsubmit.att_file;
                    var files = "";
                    for(var i = 1; i < fform.length; i++){
                        if(fform[i].value != "") files += (fform[i].value+",");
                        else break;
                    }
                    document.faxsubmit.attafiles.value = files;
                    return files;
                }
            """)
            log.info("attafiles: %s...", att_check[:100] if att_check else "EMPTY")

            if not att_check:
                return {"ok": False, "error": "파일 변환 결과 없음 (attafiles 비어있음)"}

            # 발송버튼 = <a href="javascript:e_money_chk();">
            send_btn = page.locator('a[href*="e_money_chk"]')
            send_btn.click()
            log.info("발송버튼 클릭됨. AJAX 처리 대기...")

            # ── STEP 7: 발송 결과 확인 ──────────────────────────────────────
            # AJAX 중복/ARS거부 체크 후 form이 HanaFax_country_exe.asp 로 submit됨
            # 혹은 confirm 다이얼로그 처리 필요
            SUCCESS_URLS = (
                "submit_Result",
                "HanaFax_SendList_combin",
                "HanaFax_country_exe",
                "confirm",
            )
            result_url = ""
            for tick in range(30):
                page.wait_for_timeout(2_000)
                cur_url = page.url
                if any(s in cur_url for s in SUCCESS_URLS):
                    result_url = cur_url
                    log.info("결과 페이지 도달: %s", cur_url)
                    break
                if dialogs:
                    last_dlg = dialogs[-1]
                    log.warning("DIALOG 감지: %s", last_dlg[:200])
                    if "전송예상금" in last_dlg or "전송완료 후" in last_dlg:
                        # 이전 배치가 처리 중 → 재시도 가능 신호
                        return {
                            "ok": False,
                            "retry": True,
                            "error": f"이전 배치 처리 중 ({last_dlg.strip()[:120]})",
                        }
                    if "초과" in last_dlg or "충전" in last_dlg:
                        return {
                            "ok": False,
                            "error": f"잔액 부족: {last_dlg[:200]}",
                        }
                log.info("결과 대기 [%d/30] url=%s", tick + 1, cur_url[:80])

            if not result_url:
                # 현재 페이지 상태 확인
                cur_url = page.url
                body_text = page.inner_text("body")[:300]
                return {
                    "ok": False,
                    "error": f"결과 페이지 미도달. url={cur_url} body={body_text}",
                }

            page.wait_for_load_state("domcontentloaded", timeout=20_000)
            result_text = page.inner_text("body")
            elapsed = time.time() - start_t

            # 접수번호 추출
            job_id = None
            m = re.search(r"접수번호[\s:：]*([A-Z0-9\-]{5,})", result_text)
            if m:
                job_id = m.group(1)
            else:
                nums = re.findall(r"\b(\d{8,})\b", result_text)
                if nums:
                    job_id = nums[0]

            is_ok = "완료" in result_text or "접수" in result_text or job_id is not None
            log.info(
                "배치%d 발송 %s: job_id=%s elapsed=%.1fs", batch_num, "성공" if is_ok else "불명확", job_id, elapsed
            )

            return {
                "ok": is_ok,
                "batch": batch_num,
                "count": len(fax_numbers),
                "job_id": job_id,
                "result_url": result_url,
                "result_text": result_text[:500],
                "elapsed_sec": round(elapsed, 1),
                "dialogs": dialogs,
            }

        except PWTimeout as e:
            return {"ok": False, "error": f"타임아웃: {e}"}
        except Exception as e:
            log.exception("Playwright 오류")
            return {"ok": False, "error": str(e)}
        finally:
            browser.close()


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="하나팩스 대량팩스 발송")
    parser.add_argument("--batch", type=int, help="발송할 배치 번호 (1~5)")
    parser.add_argument("--all", action="store_true", help="전체 5배치 순차 발송")
    parser.add_argument("--dry-run", action="store_true", help="실제 발송 없이 시뮬레이션")
    args = parser.parse_args()

    uid, pwd = _get_creds()
    if not uid or not pwd:
        print("ERROR: 하나팩스 자격증명 없음. python scripts/entry/cdp_cli.py cred set hanafax")
        sys.exit(1)

    batches_to_run: list[int] = []
    if args.all:
        batches_to_run = [1, 2, 3, 4, 5]
    elif args.batch:
        batches_to_run = [args.batch]
    else:
        parser.print_help()
        sys.exit(1)

    total_sent = 0
    total_failed = 0

    for batch_num in batches_to_run:
        log.info("=" * 60)
        log.info("배치 %d / %d 시작", batch_num, len(batches_to_run))

        try:
            batch_data = load_batch(batch_num)
        except FileNotFoundError as e:
            log.error("%s", e)
            total_failed += 1
            continue

        fax_numbers = batch_data["fax_numbers"]
        log.info("배치%d: %d건", batch_num, len(fax_numbers))

        # 이전 배치 처리 중이면 최대 2시간 대기 후 재시도
        MAX_RETRY = 24  # 5분 × 24 = 2시간
        RETRY_WAIT = 300  # 5분
        # fail-closed: 발송 루프가 한 번도 돌지 않으면 '실패'로 기록 (성공으로 보이는 기본값 금지)
        result: dict = {"ok": False, "error": "not_attempted"}
        for attempt in range(MAX_RETRY + 1):
            result = send_bulk_batch(
                batch_num=batch_num,
                fax_numbers=fax_numbers,
                dry_run=args.dry_run,
                uid=uid,
                pwd=pwd,
            )
            if result.get("ok") or not result.get("retry"):
                break
            log.info("배치%d 재시도 대기 %d분... [%d/%d]", batch_num, RETRY_WAIT // 60, attempt + 1, MAX_RETRY)
            time.sleep(RETRY_WAIT)

        save_result(batch_num, result)

        if result.get("ok"):
            total_sent += len(fax_numbers)
            log.info("배치%d 완료: job_id=%s", batch_num, result.get("job_id"))
        else:
            total_failed += 1
            log.error("배치%d 실패: %s", batch_num, result.get("error"))

        if batch_num < batches_to_run[-1]:
            wait_sec = 10
            log.info("다음 배치 전 %d초 대기...", wait_sec)
            time.sleep(wait_sec)

    log.info("=" * 60)
    log.info(
        "전체 완료: 성공배치=%d 실패배치=%d 총발송=%d건", len(batches_to_run) - total_failed, total_failed, total_sent
    )


if __name__ == "__main__":
    main()
