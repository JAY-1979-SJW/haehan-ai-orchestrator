"""전체 사이트 완전 탐색 - 40대 모든 단말기 현황 파악"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page
from scripts.logger import get_logger

_log = get_logger(__name__)


def extract_table_data(page, table_selector: str = 'table:has(tbody)') -> list:
    """테이블에서 모든 데이터 추출"""
    return page.evaluate(f"""
    (() => {{
        const table = document.querySelector('{table_selector}');
        if (!table) return [];

        const tbody = table.querySelector('tbody');
        if (!tbody) return [];

        const rows = tbody.querySelectorAll('tr');
        const data = [];

        rows.forEach((row) => {{
            const cells = row.querySelectorAll('td');
            if (cells.length > 0) {{
                const cellTexts = Array.from(cells).map(c => c.innerText?.trim() || '');

                // 첫 셀이 데이터인 경우만 수집
                if (cellTexts[0]?.length > 0 && !/^(전체|선택|-|당일)/.test(cellTexts[0])) {{
                    data.push(cellTexts);
                }}
            }}
        }});

        return data;
    }})();
    """)


def explore_webman380_comprehensive(page) -> dict:
    """WEBMAN380M00 - 현장별 단말기 목록 완전 탐색"""
    print("\n" + "="*80)
    print("[1] WEBMAN380M00 - 현장별 단말기 목록")
    print("="*80)

    url = "https://eum.cw.or.kr/web/man/WEBMAN380M00"
    page.goto(url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    # 필터 정보 파악
    filter_info = page.evaluate("""
    (() => {
        const selects = document.querySelectorAll('select');
        return Array.from(selects).map((sel, idx) => ({
            index: idx,
            name: sel.name || sel.id || `filter_${idx}`,
            selectedValue: sel.value,
            selectedText: sel.options[sel.selectedIndex]?.text || '',
            options: Array.from(sel.options).map(o => ({
                value: o.value,
                text: o.text
            }))
        }));
    })();
    """)

    print(f"\n필터 {len(filter_info)}개 발견:\n")
    for filt in filter_info[:6]:
        print(f"  [{filt['index']}] {filt['name']}")
        print(f"      현재: {filt['selectedText']}")
        print(f"      옵션: {', '.join(o['text'] for o in filt['options'][:3])}")

    # 상태별로 여러 번 조회하기
    all_devices = []
    status_filters = ["전체", "진행", "준공"]

    for status in status_filters:
        print(f"\n[상태 필터: {status}로 설정]")

        # 상태 필터 찾아서 변경
        status_set = page.evaluate(f"""
        (() => {{
            const selects = document.querySelectorAll('select');
            let found = false;

            for (let sel of selects) {{
                const opts = Array.from(sel.options).map(o => o.text);
                // 상태 필터 찾기 (진행, 준공 옵션 있는 select)
                if (opts.some(t => t.includes('진행')) && opts.some(t => t.includes('준공'))) {{
                    const targetOpt = Array.from(sel.options).find(o => o.text.trim() === '{status}');
                    if (targetOpt) {{
                        sel.value = targetOpt.value;
                        sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        found = true;
                        break;
                    }}
                }}
            }}

            return found;
        }})();
        """)

        if status_set:
            time.sleep(2)
            page.wait_for_load_state("load", timeout=5000)

            # 조회 버튼 찾아서 클릭
            search_clicked = False
            try:
                buttons = page.locator('button').all()
                for btn in buttons[:10]:
                    text = btn.text_content().strip()
                    if '조회' in text or '검색' in text:
                        btn.click()
                        search_clicked = True
                        time.sleep(2)
                        page.wait_for_load_state("load", timeout=5000)
                        break
            except:
                pass

            # 데이터 추출
            status_devices = extract_table_data(page)
            print(f"  추출: {len(status_devices)}개")

            for device in status_devices[:3]:
                print(f"    • {device[0]:<3} | {device[1][:40] if len(device) > 1 else ''}")

            all_devices.extend(status_devices)

    print(f"\n✓ WEBMAN380M00 총 추출: {len(all_devices)}개 항목")

    return {
        'page_id': 'WEBMAN380M00',
        'devices': all_devices,
        'total': len(all_devices)
    }


def explore_webman390_comprehensive(page) -> dict:
    """WEBMAN390M00 - 단말기설치현황 완전 탐색"""
    print("\n" + "="*80)
    print("[2] WEBMAN390M00 - 단말기설치현황")
    print("="*80)

    url = "https://eum.cw.or.kr/web/man/WEBMAN390M00"
    page.goto(url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    # 디스플레이 개수 설정을 60개로 변경
    display_set = page.evaluate("""
    (() => {
        const selects = document.querySelectorAll('select');
        for (let sel of selects) {
            const opts = Array.from(sel.options).map(o => o.text);
            if (opts.some(t => t.includes('개'))) {
                const opt60 = Array.from(sel.options).find(o => o.text.includes('60'));
                if (opt60) {
                    sel.value = opt60.value;
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
            }
        }
        return false;
    })();
    """)

    if display_set:
        print("✓ 디스플레이 60개로 설정")
        time.sleep(2)
        page.wait_for_load_state("load", timeout=5000)

    # 모든 필터를 "전체"로 설정
    page.evaluate("""
    (() => {
        const selects = document.querySelectorAll('select');
        selects.forEach(sel => {
            const allOpt = Array.from(sel.options).find(o => o.text.trim() === '전체');
            if (allOpt) {
                sel.value = allOpt.value;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    })();
    """)

    time.sleep(2)
    page.wait_for_load_state("load", timeout=5000)

    # 데이터 추출 (모든 테이블)
    all_tables_data = page.evaluate("""
    (() => {
        const results = [];

        document.querySelectorAll('table').forEach((table, idx) => {
            const tbody = table.querySelector('tbody');
            if (!tbody) return;

            const rows = tbody.querySelectorAll('tr');
            const data = [];

            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length > 0) {
                    const cellTexts = Array.from(cells).map(c => c.innerText?.trim() || '');
                    if (cellTexts[0]?.length > 0 && !/^(전체|선택|-|당일)/.test(cellTexts[0])) {
                        data.push(cellTexts);
                    }
                }
            });

            if (data.length > 0) {
                results.push({ table_index: idx, row_count: data.length, data: data });
            }
        });

        return results;
    })();
    """)

    total_items = sum(t['row_count'] for t in all_tables_data)
    print(f"✓ 테이블 {len(all_tables_data)}개에서 총 {total_items}개 항목 추출\n")

    for tbl in all_tables_data:
        print(f"  테이블 #{tbl['table_index']}: {tbl['row_count']}행")
        for item in tbl['data'][:2]:
            print(f"    • {item[0][:50]}")

    return {
        'page_id': 'WEBMAN390M00',
        'total': total_items,
        'tables_data': all_tables_data
    }


def explore_webman400_comprehensive(page) -> dict:
    """WEBMAN400M00 - 단말기별 이력관리"""
    print("\n" + "="*80)
    print("[3] WEBMAN400M00 - 단말기별 이력관리")
    print("="*80)

    url = "https://eum.cw.or.kr/web/man/WEBMAN400M00"
    page.goto(url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    # 필터 정보
    filter_data = page.evaluate("""
    (() => {
        const selects = document.querySelectorAll('select');
        return Array.from(selects).map(sel => ({
            options: Array.from(sel.options).map(o => o.text)
        }));
    })();
    """)

    print(f"✓ 필터 {len(filter_data)}개")
    for i, f in enumerate(filter_data, 1):
        print(f"  [{i}] {', '.join(f['options'][:3])}")

    # 필터를 "전체"로 모두 설정
    page.evaluate("""
    (() => {
        document.querySelectorAll('select').forEach(sel => {
            const allOpt = Array.from(sel.options).find(o => o.text.trim() === '전체');
            if (allOpt) {
                sel.value = allOpt.value;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    })();
    """)

    time.sleep(2)
    page.wait_for_load_state("load", timeout=5000)

    devices = extract_table_data(page)
    print(f"\n✓ 추출: {len(devices)}개 항목")

    for device in devices[:5]:
        print(f"  • {device[0][:50]}")

    return {
        'page_id': 'WEBMAN400M00',
        'total': len(devices),
        'devices': devices
    }


def main():
    page = get_page()

    print("\n" + "="*80)
    print("🔍 건설근로자공제회 단말기 전체 현황 완전 탐색")
    print("="*80)
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"목표: 40대 단말기 전체 현황 파악\n")

    results = {}

    try:
        # 1. WEBMAN380M00 탐색
        result1 = explore_webman380_comprehensive(page)
        results['webman380'] = result1
        time.sleep(1)

        # 2. WEBMAN390M00 탐색
        result2 = explore_webman390_comprehensive(page)
        results['webman390'] = result2
        time.sleep(1)

        # 3. WEBMAN400M00 탐색
        result3 = explore_webman400_comprehensive(page)
        results['webman400'] = result3

    except Exception as e:
        _log.error(f"탐색 중 오류: {e}")
        import traceback
        traceback.print_exc()

    # 최종 요약
    print("\n" + "="*80)
    print("📊 최종 요약")
    print("="*80)

    total_found = 0
    for page_id, result in results.items():
        total = result.get('total', 0)
        total_found += total
        print(f"{page_id}: {total}개")

    print(f"\n{'─'*40}")
    print(f"전체 발견: {total_found}개")

    if total_found >= 40:
        print(f"✅ 40대 이상 확인됨!")
    else:
        print(f"⚠️  {total_found}개 (부족: {40 - total_found}대)")

    # JSON 저장
    output_file = Path("data") / "full_comprehensive_exploration.json"
    output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"\n✓ 결과 저장: {output_file}")
    print(f"완료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log.error(f"실행 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
