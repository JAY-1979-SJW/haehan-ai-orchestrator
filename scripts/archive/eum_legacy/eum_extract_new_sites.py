"""설치안내대상 (WEBMAN370M00) - 신규 단말기 미설치 현장 전체 추출
- 스크래핑: table.querySelectorAll('tr') 기반 2행씩 묶기
- 엑셀저장: 페이지 내 엑셀저장 버튼 클릭하여 다운로드
- 홍보 메일 발송용 담당자 연락처/이메일 포함
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.browser.cdp.connection import get_page  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402

_log = get_logger(__name__)


def get_real_page_count(page) -> int:
    """실제 페이지네이션 버튼에서 최대 페이지 수 파악
    공사번호 같은 큰 숫자를 페이지로 오인하지 않도록
    페이지네이션 영역(prev/next 주변)의 작은 숫자만 수집
    """
    return page.evaluate("""
    (() => {
        // 이전/다음 버튼 주변의 숫자 버튼만 탐색
        let max = 1;
        const allBtns = Array.from(document.querySelectorAll('button'));

        // prev/next 버튼 찾기
        const prevIdx = allBtns.findIndex(b => b.className?.includes('prev') || b.innerText?.trim() === '이전');
        const nextIdx = allBtns.findIndex(b => b.className?.includes('next') || b.innerText?.trim() === '다음');

        if (prevIdx >= 0 && nextIdx > prevIdx) {
            // prev와 next 사이 버튼만 확인
            for (let i = prevIdx + 1; i < nextIdx; i++) {
                const t = allBtns[i].innerText?.trim();
                if (/^\\d+$/.test(t)) {
                    const n = parseInt(t);
                    if (n < 1000 && n > max) max = n;  // 1000 미만의 숫자만 페이지로 인정
                }
            }
        } else {
            // fallback: 100 이하 숫자 버튼만
            allBtns.forEach(b => {
                const t = b.innerText?.trim();
                if (/^\\d+$/.test(t)) {
                    const n = parseInt(t);
                    if (n <= 100 && n > max) max = n;
                }
            });
        }

        return max;
    })();
    """)


def parse_current_page(page) -> list[dict]:
    """현재 페이지 테이블에서 신규 현장 데이터 파싱 (2행씩 묶기)"""
    rows = page.evaluate("""
    (() => {
        const table = document.querySelectorAll('table')[1];
        if (!table) return [];
        const out = [];
        table.querySelectorAll('tr').forEach((tr) => {
            const tds = tr.querySelectorAll('td');
            if (tds.length > 0)
                out.push(Array.from(tds).map(d => d.innerText?.trim() || ''));
        });
        return out;
    })();
    """)

    projects = []
    i = 0
    while i < len(rows) - 1:
        r1, r2 = rows[i], rows[i + 1]
        # NO가 숫자인 행만 (헤더/필터 행 제외)
        if len(r1) >= 6 and r1[0].isdigit():
            projects.append(
                {
                    "NO": r1[0],
                    "공사번호": r1[1] if len(r1) > 1 else "",
                    "공제가입번호": r1[2] if len(r1) > 2 else "",
                    "공사명": r1[3] if len(r1) > 3 else "",
                    "현장주소": r1[4] if len(r1) > 4 else "",
                    "업체명": r1[5] if len(r1) > 5 else "",
                    "설치예정일": r1[6] if len(r1) > 6 else "",
                    "설치예정대수": r1[7] if len(r1) > 7 else "",
                    "시범사업장": r1[8] if len(r1) > 8 else "",
                    "관할지사": r2[0] if len(r2) > 0 else "",
                    "담당자": r2[1] if len(r2) > 1 else "",
                    "연락처": r2[2] if len(r2) > 2 else "",
                    "이메일": r2[3] if len(r2) > 3 else "",
                    "등록일": r2[4] if len(r2) > 4 else "",
                    "공사시작일": r2[5] if len(r2) > 5 else "",
                    "공사종료일": r2[6] if len(r2) > 6 else "",
                }
            )
            i += 2
        else:
            i += 1

    return projects


def click_page_btn(page, page_num: int) -> bool:
    return page.evaluate(f"""
    (() => {{
        const allBtns = Array.from(document.querySelectorAll('button'));
        const prevIdx = allBtns.findIndex(b => b.className?.includes('prev') || b.innerText?.trim() === '이전');
        const nextIdx = allBtns.findIndex(b => b.className?.includes('next') || b.innerText?.trim() === '다음');

        let searchBtns = prevIdx >= 0 && nextIdx > prevIdx
            ? allBtns.slice(prevIdx+1, nextIdx)
            : allBtns;

        for (let b of searchBtns) {{
            if (b.innerText?.trim() === '{page_num}') {{
                b.click();
                return true;
            }}
        }}
        return false;
    }})();
    """)


def download_excel(page) -> bool:
    """엑셀저장 버튼 클릭"""
    return page.evaluate("""
    (() => {
        for (let btn of document.querySelectorAll('button')) {
            if (btn.innerText?.trim().includes('엑셀')) {
                btn.click();
                return true;
            }
        }
        return false;
    })();
    """)


def main():
    page = get_page()

    print("\n" + "=" * 80)
    print("🔍 설치안내대상 (WEBMAN370M00) - 신규 현장 추출")
    print("=" * 80 + "\n")

    page.goto("https://eum.cw.or.kr/web/man/WEBMAN370M00", timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    try:
        from scripts.browser.popup.popup_detector import handle_page_popups

        handle_page_popups(page, timeout_s=2.0)
    except Exception:  # noqa: BLE001 - 팝업 정리 best-effort, 읽기전용 탐색이라 실패해도 다음 단계 진행에 영향 없음
        pass

    # 100개씩 표시
    page.evaluate("""
    (() => {
        for (let sel of document.querySelectorAll('select')) {
            const o = Array.from(sel.options).find(o => o.text.includes('100'));
            if (o) { sel.value = o.value; sel.dispatchEvent(new Event('change', {bubbles:true})); }
        }
    })();
    """)
    time.sleep(0.5)

    # 조회 클릭
    page.evaluate("""
    (() => {
        for (let btn of document.querySelectorAll('button')) {
            if (btn.innerText?.trim() === '조회') { btn.click(); return; }
        }
    })();
    """)
    time.sleep(2)

    # 엑셀저장 시도
    print("[엑셀저장] 버튼 클릭 시도...")
    excel_ok = download_excel(page)
    if excel_ok:
        print("  ✓ 엑셀저장 버튼 클릭됨 (다운로드 폴더 확인)")
        time.sleep(3)
    else:
        print("  ⚠️ 엑셀저장 버튼 없음 - 스크래핑으로 진행")

    # 전체 페이지 수
    total_pages = get_real_page_count(page)
    print(f"\n[페이지] 총 {total_pages}페이지")

    # 1페이지 추출
    all_projects = parse_current_page(page)
    print(f"  1페이지: {len(all_projects)}개")

    # 나머지 페이지
    for pn in range(2, total_pages + 1):
        ok = click_page_btn(page, pn)
        if ok:
            time.sleep(1.5)
            more = parse_current_page(page)
            all_projects.extend(more)
            print(f"  {pn}페이지: {len(more)}개")

    print(f"\n총 신규 현장: {len(all_projects)}개\n")

    # 출력
    print("=" * 80)
    print("[신규 설치 대상 현장 목록]")
    print("=" * 80)
    for p in all_projects:
        email_mark = "📧" if p["이메일"].strip() else "📞"
        print(f"\n  {email_mark} [{p['NO']:>3}] {p['공사명'][:50]}")
        print(f"           업체: {p['업체명']} | 관할: {p['관할지사']}")
        print(f"           담당: {p['담당자']} | 연락처: {p['연락처']}")
        if p["이메일"]:
            print(f"           이메일: {p['이메일']}")
        print(f"           설치예정: {p['설치예정일']} | 공사종료: {p['공사종료일']}")

    # 저장
    out_file = ROOT / "data" / "eum_new_sites_install_targets.json"
    out_file.write_text(
        json.dumps(
            {
                "timestamp": datetime.now().isoformat(),
                "source": "WEBMAN370M00 - 설치안내대상",
                "total": len(all_projects),
                "with_email": len([p for p in all_projects if p["이메일"].strip()]),
                "without_email": len([p for p in all_projects if not p["이메일"].strip()]),
                "projects": all_projects,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with_email = [p for p in all_projects if p["이메일"].strip()]
    without_email = [p for p in all_projects if not p["이메일"].strip()]

    print(f"\n{'=' * 80}")
    print(f"✓ 저장: {out_file}")
    print(f"  📧 이메일 발송 가능: {len(with_email)}개")
    print(f"  📞 전화 필요 (이메일 없음): {len(without_email)}개")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 - 레거시 아카이브 스크립트 최상위 main() 예외 핸들러 - 로그 남기고 traceback 출력 후 sys.exit(1)로 명시적 실패 종료, 위험 조작 없음
        _log.error(f"실패: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
