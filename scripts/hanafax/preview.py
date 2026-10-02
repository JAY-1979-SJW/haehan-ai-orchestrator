"""하나팩스 접수 화면 미리보기 — 수신번호·제목·첨부를 실제 화면에 채우고 **전송 없이** 스크린샷만 찍는다.

기준서: docs/specs/2026-10-02_hanafax_auto_send.md §12
- 엔진(`sender.py`)은 수정하지 않는다. 같은 화면 요소(셀렉터)를 입력 용도로만 쓴다.
- **"팩스보내기" 버튼은 누르지 않는다**(이 파일에 그 버튼의 셀렉터 문자열이 없어야 하며 테스트가 확인한다).
  추가 안전장치: 결과 페이지(`submit_Result`) 이동 요청은 브라우저에서 차단하고, 사이트 대화상자는 모두 취소한다.
- 엔진과 같은 락을 써서 발송과 미리보기가 동시에 사이트를 쓰지 않게 한다.
- 스크린샷에는 수신번호가 나오므로 호출자가 로컬 저장소에만 둔다(커밋 금지).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("hanafax.preview")

_BASE_URL = "https://www.hanafax.com"
MAX_PREVIEW_NUMBERS = 30  # 화면에 채워 보여 줄 수신번호 상한(대량이면 처음 N곳만)


def capture_preview(fax_nos: list[str], subject: str, attach_file: str, out_path: Path) -> dict[str, Any]:
    """접수 화면을 채우고 `out_path` 에 스크린샷을 저장한다. 반환: {ok, message, shown, total, missing}."""
    from scripts.hanafax import sender as engine
    from scripts.hanafax.auth import get_credentials

    err = engine._validate_attach_file(attach_file)
    if err:
        return {"ok": False, "message": err}
    uid, pwd = get_credentials()
    if not uid or not pwd:
        return {"ok": False, "message": "자격증명 없음 — 하나팩스 계정이 저장돼 있지 않습니다"}
    shown = fax_nos[:MAX_PREVIEW_NUMBERS]
    with engine._LOCK:
        return _run_preview((uid, pwd), shown, len(fax_nos), subject, attach_file, out_path)


def _run_preview(
    creds: tuple[str, str], fax_nos: list[str], total: int, subject: str, attach_file: str, out_path: Path
) -> dict[str, Any]:
    uid, pwd = creds
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            locale="ko-KR",
            viewport={"width": 1280, "height": 1000},
        )
        page = context.new_page()
        page.on("dialog", lambda d: d.dismiss())  # 사이트 확인창은 전부 취소한다(무엇도 승낙하지 않는다)
        page.route("**/*submit_Result*", lambda route: route.abort())  # 결과(=전송) 페이지 이동 차단
        try:
            page.goto(_BASE_URL, wait_until="domcontentloaded", timeout=20_000)
            page.fill('input[name="struid"]', uid)
            page.fill('input[name="strpwd"]', pwd)
            page.evaluate("document.querySelector('form').submit()")
            page.wait_for_load_state("domcontentloaded", timeout=15_000)
            page.wait_for_timeout(1_500)
            if not any(c["name"] == "Login" for c in context.cookies()):
                return {"ok": False, "message": "하나팩스 로그인 실패"}

            page.click('a[href*="tHanaFax_country"]')
            page.wait_for_load_state("domcontentloaded", timeout=15_000)
            page.wait_for_timeout(2_000)
            if "tHanaFax_country" not in page.url:
                return {"ok": False, "message": "팩스 접수 페이지로 이동하지 못했습니다"}

            for fax_no in fax_nos:
                page.fill('input[name="inputfaxnumber"]', fax_no)
                page.click('button[onclick*="addPhoneNumber"]')
                page.wait_for_timeout(300)
            added = page.evaluate(
                "() => Array.from(document.querySelector('select[name=\"faddList\"]')?.options || [])"
                ".map(o => (o.value + ' ' + o.text)).filter(v => !v.startsWith('none'))"
            )
            added_digits = [re.sub(r"\D", "", v) for v in added]  # 사이트 표기(하이픈 등)와 무관하게 숫자로 비교
            missing = [n for n in fax_nos if not any(n in d for d in added_digits)]

            page.fill('input[name="fax_title"]', subject[:80])

            with page.expect_file_chooser(timeout=8_000) as chooser:
                page.click('button[onclick*="pop_addfile"]')
            chooser.value.set_files(attach_file)
            converted = False
            for _ in range(15):  # TIF 변환 대기
                page.wait_for_timeout(2_000)
                converted = bool(
                    page.evaluate(
                        "() => { const s = document.getElementById('dropZone');"
                        " const v = s && s.options.length > 1 ? s.options[1].value : '';"
                        " return !!v && v.toLowerCase().endsWith('.tif'); }"
                    )
                )
                if converted:
                    break

            out_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out_path), full_page=True, timeout=30_000)
            return {
                "ok": True,
                "message": "미리보기 완료 — 전송하지 않았습니다"
                + ("" if converted else " (첨부 변환이 끝나지 않았을 수 있음)"),
                "shown": len(fax_nos),
                "total": total,
                "missing": missing,
                "converted": converted,
            }
        except PWTimeout as exc:
            return {"ok": False, "message": f"타임아웃: {exc}"}
        except Exception as exc:  # noqa: BLE001 - 미리보기 실패는 사유만 화면에 알린다(전송과 무관)
            log.error("미리보기 오류: %s", type(exc).__name__)
            return {"ok": False, "message": f"미리보기 실패: {type(exc).__name__}"}
        finally:
            browser.close()
