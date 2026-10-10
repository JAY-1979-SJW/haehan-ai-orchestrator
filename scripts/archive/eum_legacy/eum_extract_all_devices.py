"""EUM 단말기설치현황 완전 추출 - 모든 페이지
핵심 발견:
- 테이블#1이 실제 데이터 (tbody 아닌 table.querySelectorAll('tr') 사용)
- 각 단말기 = 2행 (행1: 14열 주정보 / 행2: 13열 보조정보)
- 헤더도 2행 (행0: 14열 / 행1: 13열)
- 페이지네이션 존재 (1, 2 페이지)

2026-08-16: 당시 scripts/ 최상위 eum_extract_all_devices.py(현 scripts/eum/extract_all_devices.py) 의 re-export 대상 파일이
누락돼(dfa06bfa 모듈화 리팩토링 중 아카이브 파일 생성 누락) 깨져 있던 것을
git 이력(6e08aec2)에서 복원. 저장 경로만 get_app_dir("eum") 기준으로 보정.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.browser.cdp.connection import get_page  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402
from scripts.common.op_log import op_context  # noqa: E402

_log = get_logger(__name__)

# 헤더 매핑 (2026-08-16 실측: 행0 15열, 행1 14열 — "지정일"/"만료일" 컬럼 추가됨)
HEADER_ROW1 = [
    "NO",
    "고유번호",
    "단말기번호",
    "공제가입번호",
    "공사명",
    "발주기관",
    "전자카드구분",
    "지정업체",
    "단말기유형",
    "지정일",
    "운용상태",
    "설치일",
    "처리건수",
    "계약유형",
    "총비용",
]
HEADER_ROW2 = [
    "단말기ID",
    "공사번호",
    "공사상태",
    "공사업체",
    "관할지사",
    "설치예외",
    "유통업체",
    "지정단말기명",
    "만료일",
    "통신상태",
    "철거일",
    "설치일수",
    "설치유형",
    "잔존가치",
]


def extract_page_devices(page) -> list[dict]:
    """현재 페이지에서 단말기 데이터 추출"""
    raw_rows = page.evaluate("""
    (() => {
        const table = document.querySelectorAll('table')[1];
        if (!table) return [];

        const allTR = table.querySelectorAll('tr');
        const rows = [];

        allTR.forEach((tr, i) => {
            const tds = tr.querySelectorAll('td');
            if (tds.length === 0) return;  // 헤더 행 스킵

            const cells = Array.from(tds).map(td => td.innerText?.trim() || '');
            rows.push({ row_i: i, td_count: tds.length, cells: cells });
        });

        return rows;
    })();
    """)

    devices = []
    # 2행씩 묶어서 단말기 1개로 처리
    i = 0
    while i < len(raw_rows) - 1:
        r1 = raw_rows[i]
        r2 = raw_rows[i + 1]

        # 첫 번째 행이 14열, 두 번째가 13열인지 확인
        if r1["td_count"] == len(HEADER_ROW1) and r2["td_count"] == len(HEADER_ROW2):
            c1 = r1["cells"]
            c2 = r2["cells"]

            device = {}
            # 주정보 매핑
            for j, h in enumerate(HEADER_ROW1):
                device[h] = c1[j] if j < len(c1) else ""
            # 보조정보 매핑
            for j, h in enumerate(HEADER_ROW2):
                device[h] = c2[j] if j < len(c2) else ""

            devices.append(device)
            i += 2
        else:
            i += 1

    return devices


def get_page_count(page) -> int:
    """페이지 수 확인"""
    return page.evaluate("""
    (() => {
        const btns = document.querySelectorAll('button.on, button[class=""], button');
        let maxPage = 1;

        // 페이지 버튼 찾기 (숫자만 있는 버튼)
        document.querySelectorAll('button').forEach(btn => {
            const txt = btn.innerText?.trim();
            if (/^\\d+$/.test(txt)) {
                const n = parseInt(txt);
                if (n > maxPage) maxPage = n;
            }
        });

        return maxPage;
    })();
    """)


def click_page(page, page_num: int) -> bool:
    """특정 페이지 버튼 클릭"""
    return page.evaluate(f"""
    (() => {{
        const target = '{page_num}';
        let clicked = false;

        document.querySelectorAll('button').forEach(btn => {{
            if (btn.innerText?.trim() === target && !clicked) {{
                btn.click();
                clicked = true;
            }}
        }});

        return clicked;
    }})();
    """)


def main():
    page = get_page()

    print("\n" + "=" * 100)
    print("🔍 EUM 단말기설치현황 완전 추출 (전 페이지)")
    print("=" * 100 + "\n")

    url = "https://eum.cw.or.kr/web/man/WEBMAN390M00"
    print(f"[접속] {url}")
    page.goto(url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    # 팝업 처리
    try:
        from scripts.browser.popup.popup_detector import handle_page_popups

        handle_page_popups(page, timeout_s=2.0)
    except Exception:  # noqa: BLE001 - 페이지 팝업 처리 실패는 무시하고 계속 진행(팝업 없는 정상 케이스가 대부분)
        pass

    # 표시 개수 60으로 설정
    print("\n[설정] 표시 개수 60개로 변경...")
    set_ok = page.evaluate("""
    (() => {
        const selects = document.querySelectorAll('select');
        for (let sel of selects) {
            const opt60 = Array.from(sel.options).find(o => o.text.includes('60'));
            if (opt60) {
                sel.value = opt60.value;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }
        }
        return false;
    })();
    """)

    if set_ok:
        print("  ✓ 60개 설정 완료")
        time.sleep(2)

    # 조회 버튼 클릭 (필요 시)
    search_clicked = page.evaluate("""
    (() => {
        const btns = document.querySelectorAll('button');
        for (let btn of btns) {
            if (btn.innerText?.trim() === '조회') {
                btn.click();
                return true;
            }
        }
        return false;
    })();
    """)
    if search_clicked:
        print("  ✓ 조회 버튼 클릭")
        time.sleep(2)

    # 전체 페이지 수 확인
    total_pages = get_page_count(page)
    print(f"\n[페이지] 총 {total_pages}페이지 확인")

    all_devices = []

    for page_num in range(1, total_pages + 1):
        print(f"\n--- {page_num}페이지 추출 ---")

        if page_num > 1:
            clicked = click_page(page, page_num)
            if clicked:
                print(f"  {page_num}페이지 클릭 완료")
                time.sleep(1.5)
            else:
                print(f"  ⚠️ {page_num}페이지 버튼 클릭 실패")
                continue

        devices = extract_page_devices(page)
        print(f"  추출된 단말기: {len(devices)}개")

        for d in devices:
            print(
                f"    [{d['NO']}] {d['공사명'][:30]} | 임차인:{d['지정업체']} | 계약:{d['계약유형']} | 상태:{d['운용상태']} | 철거일:{d['철거일']}"
            )

        all_devices.extend(devices)

    # 집계
    print("\n" + "=" * 100)
    print(f"[최종 집계] 총 {len(all_devices)}대 단말기")
    print("=" * 100)

    rental_active = [d for d in all_devices if d["계약유형"] == "임대" and not d["철거일"]]
    rental_ended = [d for d in all_devices if d["계약유형"] == "임대" and d["철거일"]]
    purchased = [d for d in all_devices if d["계약유형"] == "구매"]
    others = [d for d in all_devices if d["계약유형"] not in ("임대", "구매")]

    print(f"\n  임대 중 (철거일 없음): {len(rental_active)}대")
    print(f"  임대 종료 (철거일 있음): {len(rental_ended)}대")
    print(f"  구매: {len(purchased)}대")
    print(f"  기타: {len(others)}대")

    print("\n[임대 현장 상세]")
    for i, d in enumerate(rental_active, 1):
        print(f"  [{i}] NO={d['NO']} | {d['공사명'][:40]}")
        print(f"       임차인: {d['지정업체']} | 관할: {d['관할지사']} | 상태: {d['운용상태']}")

    print("\n[임대 종료 - 서류정리필요]")
    for i, d in enumerate(rental_ended, 1):
        print(f"  [{i}] NO={d['NO']} | {d['공사명'][:40]}")
        print(f"       임차인: {d['지정업체']} | 철거일: {d['철거일']} | 상태: {d['운용상태']}")

    # JSON 저장
    output = {
        "timestamp": datetime.now().isoformat(),
        "source_url": url,
        "total_devices": len(all_devices),
        "summary": {
            "임대중": len(rental_active),
            "임대종료_서류정리필요": len(rental_ended),
            "구매": len(purchased),
            "기타": len(others),
        },
        "rental_active": rental_active,
        "rental_ended": rental_ended,
        "purchased": purchased,
        "all_devices": all_devices,
    }

    from scripts.common.data_paths import get_app_dir

    out_file = get_app_dir("eum") / "eum_all_devices_complete.json"
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ 저장 완료: {out_file}")
    print("=" * 100 + "\n")


if __name__ == "__main__":
    with op_context("eum_extract_all_devices", site="eum.cw.or.kr") as _ctx:
        try:
            main()
        except Exception as e:  # noqa: BLE001 - EUM 단말기 전체 추출 스크립트(archive 보존) -- 최상위 실행 실패는 로깅 후 op_context 결과를 실패로 기록
            _log.error(f"실패: {e}")
            import traceback

            traceback.print_exc()
            _ctx.set_result(ok=False, message=str(e))
        sys.exit(1)
