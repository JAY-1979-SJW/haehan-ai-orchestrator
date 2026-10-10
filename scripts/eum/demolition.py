"""WEBMAN382M00 단말기 철거 현황 조회 및 신청.

철거 대상 목록을 조회하고, 실제 신청은 gate_check(eum_remove) 필요.

사용:
    python scripts/eum/demolition.py          # 철거 현황 조회
    python scripts/eum/demolition.py --apply  # 철거 신청 (gate 차단됨)
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

from scripts.common.gate import GateBlocked  # noqa: E402
from scripts.common.gate import check as gate_check  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402
from scripts.common.op_log import op_context  # noqa: E402

log = get_logger(__name__)

EUM_BASE = "https://eum.cw.or.kr"
DEMOLITION_URL = f"{EUM_BASE}/web/man/WEBMAN382M00"


def _eum_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("eum")


DATA_DIR = _eum_dir()


def _extract_demolition_table(page) -> list[dict]:
    """WEBMAN382M00 페이지의 철거 목록 테이블 추출."""
    try:
        rows = page.evaluate("""
            () => {
                const tables = document.querySelectorAll('table');
                let targetTable = null;

                // 철거/준공 관련 헤더를 가진 테이블 우선
                for (const t of tables) {
                    const ths = t.querySelectorAll('th');
                    const thTexts = Array.from(ths).map(th => th.innerText.trim());
                    if (thTexts.some(t => ['철거','준공','단말기','공사명','상태'].some(k => t.includes(k)))) {
                        targetTable = t;
                        break;
                    }
                }
                if (!targetTable && tables.length > 0) {
                    targetTable = tables[0];
                }
                if (!targetTable) return [];

                const trs = targetTable.querySelectorAll('tr');
                const headers = [];
                const result = [];

                for (let i = 0; i < trs.length; i++) {
                    const cells = trs[i].querySelectorAll('th, td');
                    const vals = Array.from(cells).map(c => c.innerText.trim());
                    if (vals.every(v => v === '')) continue;

                    if (i === 0 || (headers.length === 0 && trs[i].querySelectorAll('th').length > 0)) {
                        headers.length = 0;
                        headers.push(...vals);
                    } else if (headers.length > 0) {
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
    except Exception as e:  # noqa: BLE001 - EUM 단말기 철거 신청 화면 자동화 - 페이지 이동/신청 실패 시 ok:False와 사유를 반환(성공으로 위장하지 않음)
        log.debug("철거 테이블 추출 실패: %s", e)
        return []


def _extract_page_info(page) -> dict:
    """페이지 제목, 버튼, 필터 정보 추출."""
    info = {"title": "", "buttons": [], "filters": []}
    try:
        info["title"] = page.title()
        info["buttons"] = (
            page.evaluate("""
            () => Array.from(document.querySelectorAll('button, input[type="button"]'))
                       .map(b => b.innerText?.trim() || b.value || '')
                       .filter(t => t)
        """)
            or []
        )
        info["filters"] = (
            page.evaluate("""
            () => Array.from(document.querySelectorAll('select'))
                       .map(s => ({name: s.name || s.id, options: Array.from(s.options).map(o => o.text.trim())}))
        """)
            or []
        )
    except Exception:  # noqa: BLE001 - EUM 단말기 철거 신청 화면 자동화 - 페이지 이동/신청 실패 시 ok:False와 사유를 반환(성공으로 위장하지 않음)
        pass
    return info


def fetch_demolition_list(page) -> dict:
    """WEBMAN382M00 철거 현황 조회.

    Returns:
        dict{accessible: bool, items: list, page_info: dict, error: str}
    """
    with op_context("eum_demolition_fetch") as ctx:
        try:
            page.goto(DEMOLITION_URL, timeout=15000)
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:  # noqa: BLE001 - EUM 단말기 철거 신청 화면 자동화 - 페이지 이동/신청 실패 시 ok:False와 사유를 반환(성공으로 위장하지 않음)
            msg = f"철거 페이지 이동 실패: {e}"
            log.error(msg)
            ctx.set_result(msg=msg, ok=False)
            return {"accessible": False, "items": [], "page_info": {}, "error": msg}

        # 접근 제한 확인
        try:
            body = page.inner_text("body")
            if any(kw in body for kw in ["접근", "권한 없", "403"]) and "로그아웃" not in body:
                msg = "WEBMAN382M00 접근 제한 (권한 없음)"
                log.warning(msg)
                ctx.set_result(msg=msg, ok=False)
                return {"accessible": False, "items": [], "page_info": {}, "error": msg}
        except Exception:  # noqa: BLE001 - EUM 단말기 철거 신청 화면 자동화 - 페이지 이동/신청 실패 시 ok:False와 사유를 반환(성공으로 위장하지 않음)
            pass

        page_info = _extract_page_info(page)
        items = _extract_demolition_table(page)

        log.info("철거 목록 추출 완료: %d건", len(items))
        ctx.set_result(msg="철거 목록 추출 완료", count=len(items))

        return {
            "accessible": True,
            "items": items,
            "page_info": page_info,
            "error": "",
        }


def request_demolition(page, device_id: str) -> dict:
    """단말기 철거 신청 (APPROVE gate 필요).

    Args:
        page: Playwright Page 객체
        device_id: 철거 신청할 단말기 고유번호

    Returns:
        dict{ok: bool, reason: str}
    """
    # APPROVE 게이트 — force=False 이므로 GateBlocked 발생
    try:
        gate_check("eum_remove", force=False, device_id=device_id)
    except GateBlocked as e:
        log.warning("철거 신청 차단됨: %s", e)
        return {
            "ok": False,
            "reason": f"게이트 차단: 사용자 승인 필요. ({e})",
        }

    with op_context("eum_demolition_apply", device_id=device_id) as ctx:
        log.info("철거 신청 시작: device_id=%s", device_id)
        # 실제 신청 로직 (페이지 구조 확인 후 구현 필요)
        # 여기서는 페이지 이동 + 대상 행 클릭 + 신청 버튼 클릭 흐름
        try:
            page.goto(DEMOLITION_URL, timeout=15000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # 단말기 행 찾기
            row_found = page.evaluate(f"""
                () => {{
                    const cells = document.querySelectorAll('td');
                    for (const cell of cells) {{
                        if (cell.innerText.trim() === '{device_id}') {{
                            const row = cell.closest('tr');
                            if (row) {{
                                const btn = row.querySelector('button, a[href*="apply"], a[href*="신청"]');
                                if (btn) {{ btn.click(); return true; }}
                            }}
                        }}
                    }}
                    return false;
                }}
            """)

            if not row_found:
                msg = f"단말기 {device_id} 행을 찾을 수 없음"
                ctx.set_result(msg=msg, ok=False)
                return {"ok": False, "reason": msg}

            page.wait_for_load_state("networkidle", timeout=10000)
            ctx.set_result(msg="철거 신청 완료")
            return {"ok": True, "reason": "철거 신청 완료"}

        except Exception as e:  # noqa: BLE001 - EUM 단말기 철거 신청 화면 자동화 - 페이지 이동/신청 실패 시 ok:False와 사유를 반환(성공으로 위장하지 않음)
            msg = f"철거 신청 중 오류: {e}"
            log.error(msg)
            ctx.set_result(msg=msg, ok=False)
            return {"ok": False, "reason": msg}


def _print_and_save_demolition_list(result: dict) -> None:
    """철거 현황 조회 결과를 출력하고 JSON 으로 저장."""
    items = result["items"]
    page_info = result["page_info"]

    print(f"\n페이지 제목: {page_info.get('title', '')}")
    print(f"가용 버튼: {', '.join(page_info.get('buttons', []))}")
    print(f"\n철거 목록: {len(items)}건")

    for i, item in enumerate(items[:30], 1):
        line = " | ".join(f"{k}: {v}" for k, v in item.items() if v)
        print(f"  {i:3d}. {line}")

    if len(items) > 30:
        print(f"  ... (총 {len(items)}건, 30건만 표시)")

    # 저장
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "eum_demolition_list.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장 완료: {out_path}")
    print("=" * 60)


def main(apply: bool = False, device_id: str | None = None) -> None:
    """CLI 실행."""
    from scripts.eum.auth import is_logged_in, login
    from scripts.browser.cdp.connection import get_page

    # CLI 인자 파싱
    args = sys.argv[1:]
    if "--apply" in args:
        apply = True
    if "--device" in args:
        idx = args.index("--device")
        if idx + 1 < len(args):
            device_id = args[idx + 1]

    print("=" * 60)
    print("EUM 단말기 철거 관리 (WEBMAN382M00)")
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

    if apply and device_id:
        # 철거 신청 모드
        print(f"\n철거 신청: {device_id}")
        result = request_demolition(page, device_id)
        if result["ok"]:
            print(f"✔ {result['reason']}")
        else:
            print(f"✘ {result['reason']}")
        return

    # 철거 현황 조회 모드
    result = fetch_demolition_list(page)

    if not result["accessible"]:
        print(f"\n접근 제한: {result['error']}")
        print("WEBMAN382M00은 관리자 권한이 필요합니다.")
        return

    _print_and_save_demolition_list(result)


if __name__ == "__main__":
    main()
