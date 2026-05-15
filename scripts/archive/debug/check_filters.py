"""단말기관리 페이지의 필터 상태 및 전체 뷰 확인"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page
from scripts.logger import get_logger

_log = get_logger(__name__)


def check_filters() -> dict:
    """페이지의 필터 옵션 확인 및 전체 데이터 조회"""
    page = get_page()

    search_page = "https://eum.cw.or.kr/web/man/WEBMAN380M00"
    _log.info(f"[단말기관리] {search_page} 접속")
    page.goto(search_page, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=10000)

    # 팝업 처리
    try:
        from scripts.popup_detector import handle_page_popups
        popup_result = handle_page_popups(page, timeout_s=2.0)
    except Exception as e:
        _log.debug(f"팝업 처리 오류: {e}")

    # 페이지 필터 및 검색 옵션 확인
    page_html = page.evaluate("""
    (() => {
        return {
            // 검색 폼 확인
            searchForm: document.querySelector('form')?.outerHTML.substring(0, 500) || 'N/A',

            // 상태 선택 옵션 찾기
            statusSelects: Array.from(document.querySelectorAll('select')).map(s => ({
                name: s.name || s.id,
                options: Array.from(s.options).map(o => ({
                    value: o.value,
                    text: o.text
                }))
            })),

            // 버튼 찾기
            buttons: Array.from(document.querySelectorAll('button, input[type="button"]')).map(b => ({
                text: b.innerText || b.value,
                type: b.type
            })),

            // 테이블 헤더
            tableHeaders: Array.from(document.querySelectorAll('table thead th')).map(h => h.innerText.trim()),

            // 현재 테이블 행 수
            tableRows: document.querySelectorAll('table tbody tr').length,

            // 검색 input들
            inputs: Array.from(document.querySelectorAll('input[type="text"], input[type="hidden"]')).map(i => ({
                name: i.name,
                value: i.value,
                type: i.type
            }))
        };
    })();
    """)

    print("\n" + "="*80)
    print("[현재 페이지 상태]")
    print("="*80)
    print(f"테이블 헤더: {', '.join(page_html['tableHeaders'])}")
    print(f"현재 테이블 행: {page_html['tableRows']}행\n")

    print("[필터 옵션]")
    for sel in page_html['statusSelects']:
        print(f"\n  {sel['name']}:")
        for opt in sel['options']:
            print(f"    - {opt['text']} (value: {opt['value']})")

    print(f"\n[입력 필드]")
    for inp in page_html['inputs']:
        if inp['value']:
            print(f"  {inp['name']}: '{inp['value']}'")

    print("\n[버튼]")
    for btn in page_html['buttons'][:5]:
        if btn['text'].strip():
            print(f"  - {btn['text'].strip()}")

    # 상태 드롭다운 찾아서 "전체" 선택
    status_select_result = page.evaluate("""
    (() => {
        const selects = document.querySelectorAll('select');
        let found = false;

        for (let sel of selects) {
            const name = sel.name || sel.id;
            // 상태 관련 select 찾기
            if (name.includes('status') || name.includes('상태') || name.includes('gubun')) {
                // 옵션 찾기
                const allOption = Array.from(sel.options).find(o =>
                    o.text.includes('전체') || o.value === ''
                );

                if (allOption) {
                    console.log(`선택: ${name} -> ${allOption.text}`);
                    sel.value = allOption.value;
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                    found = true;
                }
            }
        }

        return { changed: found };
    })();
    """)

    _log.info(f"필터 변경 결과: {status_select_result}")

    if status_select_result.get('changed'):
        # 페이지 새로고침 대기
        page.wait_for_load_state("networkidle", timeout=10000)

        # 변경 후 테이블 재확인
        new_count = page.evaluate("""
        document.querySelectorAll('table tbody tr').length
        """)

        print(f"\n[필터 변경 후]")
        print(f"테이블 행: {new_count}행")

    return page_html


if __name__ == "__main__":
    try:
        check_filters()
    except Exception as e:
        _log.error(f"필터 확인 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
