"""검색 버튼을 클릭해서 데이터 로드"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page
from scripts.logger import get_logger

_log = get_logger(__name__)


def main():
    page = get_page()

    url = "https://eum.cw.or.kr/web/man/WEBMAN380M00"
    _log.info(f"[접속] {url}")
    page.goto(url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    # 검색 관련 요소 찾기
    search_info = page.evaluate("""
    (() => {
        const info = {
            buttons: [],
            inputs: [],
            selects: []
        };

        // 버튼 찾기
        document.querySelectorAll('button, a[class*="btn"], input[type="button"]').forEach(el => {
            const text = el.innerText || el.value || el.title || '';
            if (text && text.length > 0 && text.length < 50) {
                info.buttons.push({
                    text: text.substring(0, 20),
                    element: el.tagName,
                    class: el.className?.substring(0, 30) || ''
                });
            }
        });

        // Select 찾기
        document.querySelectorAll('select').forEach((sel, idx) => {
            const opts = Array.from(sel.options).map(o => o.text);
            info.selects.push({
                index: idx,
                optionCount: sel.options.length,
                optionSample: opts.slice(0, 3)
            });
        });

        return info;
    })();
    """)

    print("\n" + "="*80)
    print("[페이지 요소 분석]")
    print("="*80)

    print(f"\n[버튼] ({len(search_info['buttons'])}개)")
    for i, btn in enumerate(search_info['buttons'][:10], 1):
        print(f"  {i}. {btn['text']:<20} ({btn['element']})")

    print(f"\n[Select] ({len(search_info['selects'])}개)")
    for sel in search_info['selects'][:5]:
        print(f"  Select #{sel['index']}: {sel['optionCount']}개 옵션 - {', '.join(sel['optionSample'])}")

    # 필터 초기값 확인 및 첫 검색 수행
    initial_state = page.evaluate("""
    (() => {
        const selects = document.querySelectorAll('select');
        const selectValues = [];

        selects.forEach((sel, idx) => {
            selectValues.push({
                index: idx,
                selectedValue: sel.value,
                selectedText: sel.options[sel.selectedIndex]?.text || ''
            });
        });

        return {
            selectValues: selectValues,
            hasSearchButton: !!document.querySelector('button[onclick*="search"], button[onclick*="조회"], button[onclick*="fn_search"]')
        };
    })();
    """)

    print(f"\n[필터 현재값]")
    for sel in initial_state['selectValues'][:5]:
        print(f"  Select #{sel['index']}: {sel['selectedText']}")

    # 검색/조회 버튼 클릭
    print(f"\n[검색 수행]")

    try:
        # 가능한 검색 버튼들 시도
        search_clicked = False

        # 1. onclick 속성이 있는 버튼
        buttons_with_onclick = page.locator('button[onclick]').all()
        for btn in buttons_with_onclick[:5]:
            try:
                btn_text = btn.text_content()
                if '조회' in btn_text or '검색' in btn_text or 'search' in btn_text.lower():
                    print(f"  → '{btn_text.strip()}' 버튼 클릭")
                    btn.click()
                    search_clicked = True
                    time.sleep(2)
                    break
            except:
                pass

        # 2. 제일 먼저 보이는 버튼 클릭 (조회/검색일 가능성)
        if not search_clicked:
            all_buttons = page.locator('button').all()
            for btn in all_buttons[:3]:
                try:
                    btn_text = btn.text_content()
                    if btn_text.strip() and len(btn_text.strip()) < 20:
                        print(f"  → '{btn_text.strip()}' 버튼 클릭 시도")
                        btn.click()
                        time.sleep(2)
                        search_clicked = True
                        break
                except:
                    pass

        if search_clicked:
            page.wait_for_load_state("load", timeout=5000)
            _log.info("✓ 검색 완료")
        else:
            print("  ⚠ 자동 버튼 클릭 실패, Enter 키로 검색 시도")
            page.keyboard.press("Enter")
            time.sleep(2)

    except Exception as e:
        _log.warning(f"검색 버튼 클릭 오류: {e}")

    # 다시 테이블 데이터 확인
    print(f"\n[테이블 데이터 조회]")

    table_data = page.evaluate("""
    (() => {
        const tables = document.querySelectorAll('table');

        // 모든 테이블 확인
        const results = [];
        tables.forEach((table, idx) => {
            const tbody = table.querySelector('tbody');
            const rows = tbody?.querySelectorAll('tr') || [];

            const devices = [];
            rows.forEach((row) => {
                const cells = row.querySelectorAll('td');
                const cellTexts = Array.from(cells).map(c => c.innerText?.trim() || '');

                // 데이터 판단: 첫 셀이 숫자이고 두 번째가 텍스트
                if (cellTexts.length > 1 && /^\\d+$/.test(cellTexts[0]) && cellTexts[1]?.length > 3) {
                    devices.push({
                        no: cellTexts[0],
                        project: cellTexts[1],
                        device_count: cellTexts[5] || '1',
                        cells: cellTexts
                    });
                }
            });

            if (devices.length > 0) {
                results.push({
                    tableIndex: idx,
                    deviceCount: devices.length,
                    devices: devices.slice(0, 5)
                });
            }
        });

        return results;
    })();
    """)

    if table_data:
        print(f"\n✓ 데이터 발견! ({len(table_data)}개 테이블)\n")
        for result in table_data:
            print(f"테이블 #{result['tableIndex']}: {result['deviceCount']}개 디바이스")
            for device in result['devices']:
                print(f"  NO:{device['no']} | {device['project'][:40]}... | {device['device_count']}대")
    else:
        print("\n✗ 테이블 데이터 없음")
        # 페이지 상태 확인
        page_check = page.evaluate("""
        document.body.innerText.substring(0, 500)
        """)
        print(f"페이지 내용: {page_check[:200]}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log.error(f"실행 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
