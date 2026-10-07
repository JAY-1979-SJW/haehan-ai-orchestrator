"""WEBMAN400M00 단말기별 이력 조회.

단말기 번호로 이력을 조회하고 날짜·이벤트·상태를 추출한다.

사용:
    python scripts/eum/history.py                   # 전체 목록
    python scripts/eum/history.py --device 12345    # 특정 단말기
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from scripts.common.logger import get_logger  # noqa: E402
from scripts.common.op_log import op_context  # noqa: E402

log = get_logger(__name__)

EUM_BASE = "https://eum.cw.or.kr"
HISTORY_URL = f"{EUM_BASE}/web/man/WEBMAN400M00"


def _eum_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("eum")


DATA_DIR = _eum_dir()


def _extract_history_table(page) -> list[dict]:
    """현재 페이지의 이력 테이블 추출."""
    try:
        rows = page.evaluate("""
            () => {
                // 이력 테이블 전체 tr 추출
                const tables = document.querySelectorAll('table');
                let targetTable = null;
                for (const t of tables) {
                    const ths = t.querySelectorAll('th');
                    const thTexts = Array.from(ths).map(th => th.innerText.trim());
                    // 이력 관련 헤더 키워드 확인
                    if (thTexts.some(t => ['날짜','일자','이벤트','상태','이력','처리'].includes(t))) {
                        targetTable = t;
                        break;
                    }
                }
                if (!targetTable) {
                    // 첫 번째 테이블 사용
                    targetTable = tables[0];
                }
                if (!targetTable) return [];

                const trs = targetTable.querySelectorAll('tr');
                const headers = [];
                const result = [];

                for (let i = 0; i < trs.length; i++) {
                    const cells = trs[i].querySelectorAll('th, td');
                    const vals = Array.from(cells).map(c => c.innerText.trim());
                    if (i === 0) {
                        headers.push(...vals);
                    } else if (vals.some(v => v !== '')) {
                        const row = {};
                        vals.forEach((v, j) => {
                            row[headers[j] || `col${j}`] = v;
                        });
                        result.push(row);
                    }
                }
                return result;
            }
        """)
        return rows or []
    except Exception as e:  # noqa: BLE001 - EUM 단말기 이력 조회 읽기전용 자동화 - 실패 시 빈 목록 반환
        log.debug("이력 테이블 추출 실패: %s", e)
        return []


def _search_device(page, device_id: str) -> list[dict]:
    """단말기 번호로 이력 검색.

    Args:
        page: Playwright Page 객체
        device_id: 단말기 번호 (고유번호 또는 단말기번호)

    Returns:
        이력 행 목록
    """
    log.info("단말기 이력 검색: device_id=%s", device_id)

    # 검색 입력 필드 후보
    search_selectors = [
        "input[name='deviceId']",
        "input[name='terminalId']",
        "input[name='devId']",
        "input[placeholder*='단말기']",
        "input[placeholder*='번호']",
        "input[type='text']",
        "#deviceId",
        "#terminalId",
        "#searchVal",
    ]

    input_sel = None
    for sel in search_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                input_sel = sel
                break
        except Exception:  # noqa: BLE001 - EUM 단말기 이력 조회 읽기전용 자동화 - 실패 시 빈 목록 반환
            pass

    if input_sel:
        page.fill(input_sel, device_id)
        # 검색 버튼
        search_btn_selectors = [
            "button:has-text('검색')",
            "button[type='submit']",
            "input[type='submit']",
            ".btn-search",
            "#btnSearch",
        ]
        for sel in search_btn_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    page.wait_for_load_state("networkidle", timeout=10000)
                    break
            except Exception:  # noqa: BLE001 - EUM 단말기 이력 조회 읽기전용 자동화 - 실패 시 빈 목록 반환
                pass
    else:
        log.warning("검색 입력 필드를 찾을 수 없음 — 현재 페이지 이력 추출")

    return _extract_history_table(page)


def fetch_history(page, device_id: str | None = None) -> list[dict]:
    """WEBMAN400M00에서 단말기 이력 조회.

    Args:
        page: Playwright Page 객체 (로그인 상태)
        device_id: 특정 단말기 번호. None이면 전체 첫 페이지 이력

    Returns:
        이력 행 목록
    """
    with op_context("eum_history_fetch", device_id=device_id or "all") as ctx:
        try:
            page.goto(HISTORY_URL, timeout=15000)
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:  # noqa: BLE001 - EUM 단말기 이력 조회 읽기전용 자동화 - 실패 시 빈 목록 반환
            msg = f"이력 페이지 이동 실패: {e}"
            log.error(msg)
            ctx.set_result(msg=msg, ok=False)
            return []

        # 접근 제한 확인
        try:
            body = page.inner_text("body")
            if any(kw in body for kw in ["접근", "권한 없", "로그인", "403"]) and "로그아웃" not in body:
                msg = "WEBMAN400M00 접근 제한"
                log.warning(msg)
                ctx.set_result(msg=msg, ok=False)
                return []
        except Exception:  # noqa: BLE001 - EUM 단말기 이력 조회 읽기전용 자동화 - 실패 시 빈 목록 반환
            pass

        if device_id:
            rows = _search_device(page, device_id)
        else:
            rows = _extract_history_table(page)

        log.info("이력 추출 완료: %d행", len(rows))
        ctx.set_result(msg="이력 추출 완료", count=len(rows))
        return rows


def main(device_id: str | None = None) -> None:
    """CLI 실행."""
    from scripts.eum.auth import is_logged_in, login
    from scripts.browser.cdp.connection import get_page

    # CLI 인자 파싱
    if device_id is None:
        args = sys.argv[1:]
        if "--device" in args:
            idx = args.index("--device")
            if idx + 1 < len(args):
                device_id = args[idx + 1]
        elif "-d" in args:
            idx = args.index("-d")
            if idx + 1 < len(args):
                device_id = args[idx + 1]

    print("=" * 60)
    print("EUM 단말기 이력 조회 (WEBMAN400M00)")
    if device_id:
        print(f"단말기: {device_id}")
    print("=" * 60)

    page = get_page()

    # 로그인 확인
    if not is_logged_in(page):
        print("자동 로그인 중...")
        res = login(page)
        if not res["ok"]:
            print(f"✘ 로그인 실패: {res['reason']}")
            return
        print(f"✔ 로그인 성공: {res['user']}")

    # 이력 조회
    rows = fetch_history(page, device_id)

    if not rows:
        print("이력 데이터가 없습니다.")
        return

    _print_and_save_history(rows, device_id)


def _print_and_save_history(rows: list, device_id: str | None) -> None:
    """이력 목록을 출력하고 JSON 으로 저장."""
    print(f"\n이력 {len(rows)}건:")
    for i, row in enumerate(rows[:50], 1):  # 최대 50건 출력
        line = " | ".join(f"{k}: {v}" for k, v in row.items() if v)
        print(f"  {i:3d}. {line}")

    if len(rows) > 50:
        print(f"  ... (총 {len(rows)}건, 처음 50건만 표시)")

    # JSON 저장
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{device_id}" if device_id else "_all"
    out_path = DATA_DIR / f"eum_history{suffix}.json"
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장 완료: {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
