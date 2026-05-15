"""단말기 보유 현황 최종 데이터 추출
- 접근 가능한 모든 페이지에서 단말기 통계 수집
- 테이블 데이터 추출
- 전체 인벤토리 규모 파악
"""
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


def extract_webman380_full_data(page) -> dict:
    """WEBMAN380M00 (단말기 관리) - 전체 필터 조합으로 데이터 추출"""
    print("\n" + "="*80)
    print("[1] WEBMAN380M00 - 단말기 관리 (임대 프로젝트)")
    print("="*80)

    url = "https://eum.cw.or.kr/web/man/WEBMAN380M00"
    page.goto(url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    # 상태 필터를 "전체"로 설정하고 모든 데이터 추출
    page.evaluate("""
    (() => {
        const selects = document.querySelectorAll('select');
        for (let sel of selects) {
            const opts = Array.from(sel.options).map(o => o.text);
            // 상태 필터 찾기
            if (opts.some(t => t.includes('진행')) && opts.some(t => t.includes('준공'))) {
                const allOpt = Array.from(sel.options).find(o => o.text.trim() === '전체');
                if (allOpt) {
                    sel.value = allOpt.value;
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
            // 개수 필터를 60개로 설정
            else if (opts.some(t => t.includes('개'))) {
                const opt60 = Array.from(sel.options).find(o => o.text.includes('60'));
                if (opt60) {
                    sel.value = opt60.value;
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
        }
    })();
    """)

    time.sleep(2)
    page.wait_for_load_state("load", timeout=5000)

    # 테이블 데이터 추출
    table_data = page.evaluate("""
    (() => {
        const rows = document.querySelectorAll('table tbody tr');
        const devices = [];
        const stats = {
            total_records: 0,
            total_device_count: 0,
            by_status: {}
        };

        rows.forEach((row) => {
            const cells = row.querySelectorAll('td');
            if (cells.length > 0) {
                const noText = cells[0]?.innerText?.trim() || '';

                // NO가 숫자인 행만 (실제 데이터)
                if (/^\\d+$/.test(noText)) {
                    const device = {
                        no: noText,
                        project: cells[1]?.innerText?.trim() || '',
                        contract: cells[2]?.innerText?.trim() || '',
                        code: cells[3]?.innerText?.trim() || '',
                        device_count: parseInt(cells[5]?.innerText?.trim() || '1')
                    };

                    if (device.project) {
                        devices.push(device);
                        stats.total_records++;
                        stats.total_device_count += device.device_count;
                    }
                }
            }
        });

        return {
            devices: devices,
            stats: stats,
            page_info: {
                title: document.title,
                visible_rows: rows.length
            }
        };
    })();
    """)

    print(f"\n프로젝트 레코드: {table_data['stats']['total_records']}건")
    print(f"총 단말기 수: {table_data['stats']['total_device_count']}대")
    print(f"\n[상위 5개 프로젝트]")
    for device in table_data['devices'][:5]:
        print(f"  NO:{device['no']} | {device['project'][:45]}... | {device['device_count']}대")

    if len(table_data['devices']) > 5:
        print(f"  ... 외 {len(table_data['devices'])-5}개")

    return {
        'page_id': 'WEBMAN380M00',
        'name': '단말기 관리',
        'data': table_data
    }


def extract_webman390_data(page) -> dict:
    """WEBMAN390M00 (단말기설치현황) - 설치 상황 파악"""
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

    # 페이지 정보 추출
    page_info = page.evaluate("""
    (() => {
        const allText = document.body.innerText;

        // 필터 정보
        const filters = Array.from(document.querySelectorAll('select')).map(s => ({
            name: s.name || s.id,
            selected: s.value,
            options: Array.from(s.options).map(o => o.text)
        }));

        // 테이블 정보
        const table = document.querySelector('table');
        const headers = Array.from((table?.querySelectorAll('thead th') || [])).map(h => h.innerText.trim());
        const rowCount = table?.querySelectorAll('tbody tr').length || 0;

        // 통계 숫자 찾기
        const numbers = allText.match(/\\d+/g) || [];
        const largeNumbers = numbers.filter(n => parseInt(n) > 10);

        return {
            title: document.title,
            headers: headers,
            rowCount: rowCount,
            filters: filters,
            largeNumbers: [...new Set(largeNumbers)].slice(0, 10)
        };
    })();
    """)

    print(f"\n테이블 열: {len(page_info['headers'])}개")
    print(f"테이블 행: {page_info['rowCount']}개")
    print(f"헤더: {', '.join(page_info['headers'][:5])}")
    print(f"\n[발견된 숫자 (통계)]")
    for num in page_info['largeNumbers']:
        print(f"  • {num}")

    return {
        'page_id': 'WEBMAN390M00',
        'name': '단말기설치현황',
        'info': page_info
    }


def extract_webman400_data(page) -> dict:
    """WEBMAN400M00 (단말기별 이력관리) - 단말기 상태별 분류"""
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

    page_info = page.evaluate("""
    (() => {
        const filters = [];
        const selects = document.querySelectorAll('select');

        // 필터 정보 상세
        selects.forEach((sel, idx) => {
            const opts = Array.from(sel.options);
            filters.push({
                index: idx,
                name: sel.name || `filter_${idx}`,
                options: opts.map(o => ({
                    value: o.value,
                    text: o.text
                }))
            });
        });

        // 테이블 데이터
        const table = document.querySelector('table');
        const rows = table?.querySelectorAll('tbody tr') || [];

        return {
            filterCount: filters.length,
            filters: filters,
            rowCount: rows.length,
            title: document.title
        };
    })();
    """)

    print(f"\n필터: {page_info['filterCount']}개")
    print(f"테이블 행: {page_info['rowCount']}개")

    # 각 필터의 옵션 확인
    print(f"\n[필터 옵션]")
    for filt in page_info['filters']:
        print(f"  필터 {filt['index']}: {len(filt['options'])}개 옵션")
        for opt in filt['options'][:5]:
            if opt['text']:
                print(f"    - {opt['text']}")

    return {
        'page_id': 'WEBMAN400M00',
        'name': '단말기별 이력관리',
        'info': page_info
    }


def extract_dashboard_stats(page) -> dict:
    """마이페이지/대시보드에서 통계 정보 추출"""
    print("\n" + "="*80)
    print("[4] 대시보드 통계 정보")
    print("="*80)

    url = "https://eum.cw.or.kr/mypage"
    page.goto(url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    stats = page.evaluate("""
    (() => {
        const allText = document.body.innerText;

        // 큰 숫자 찾기
        const numberMatches = allText.matchAll(/\\d{2,}/g);
        const numbers = [];
        for (const match of numberMatches) {
            const num = parseInt(match[0]);
            if (num > 1) {
                numbers.push({ value: num, text: match[0] });
            }
        }

        // 중복 제거 및 정렬
        const unique = [];
        const seen = new Set();
        for (const num of numbers.sort((a, b) => b.value - a.value)) {
            if (!seen.has(num.value) && num.value < 100000) {
                unique.push(num);
                seen.add(num.value);
            }
        }

        // "단말기", "임대", "보유" 등의 키워드와 함께 나타나는 숫자 찾기
        const lines = allText.split('\\n');
        const relevantStats = [];
        for (const line of lines) {
            if ((line.includes('단말') || line.includes('임대') || line.includes('보유') || line.includes('관리')) &&
                /\\d{1,}/.test(line)) {
                relevantStats.push(line.trim());
            }
        }

        return {
            topNumbers: unique.slice(0, 15),
            relevantLines: relevantStats.slice(0, 10)
        };
    })();
    """)

    print(f"\n[주요 통계 숫자]")
    for stat in stats['topNumbers'][:10]:
        print(f"  • {stat['value']}")

    print(f"\n[관련 텍스트]")
    for text in stats['relevantLines']:
        print(f"  • {text[:60]}")

    return {
        'page_id': 'dashboard',
        'name': '마이페이지',
        'stats': stats
    }


def main():
    """메인 추출"""
    page = get_page()

    all_results = []

    try:
        # 1. 단말기 관리 페이지 (WEBMAN380M00)
        result1 = extract_webman380_full_data(page)
        all_results.append(result1)
        time.sleep(1)

        # 2. 단말기설치현황 (WEBMAN390M00)
        result2 = extract_webman390_data(page)
        all_results.append(result2)
        time.sleep(1)

        # 3. 단말기별 이력관리 (WEBMAN400M00)
        result3 = extract_webman400_data(page)
        all_results.append(result3)
        time.sleep(1)

        # 4. 대시보드
        result4 = extract_dashboard_stats(page)
        all_results.append(result4)

    except Exception as e:
        _log.error(f"추출 중 오류: {e}")
        import traceback
        traceback.print_exc()

    # 최종 요약
    print("\n" + "="*80)
    print("[최종 요약: 단말기 보유 현황]")
    print("="*80)

    if all_results and 'data' in all_results[0]:
        data = all_results[0]['data']
        print(f"\n✓ 총 임대 프로젝트: {data['stats']['total_records']}건")
        print(f"✓ 총 단말기 보유 수: {data['stats']['total_device_count']}대")
        print(f"\n단말기 상태 분류:")
        print(f"  - 현재 임대 중인 프로젝트")
        print(f"  - 임대 완료/반납 대기 중인 프로젝트")
        print(f"\n상세 정보는 최종 보고서를 참조하세요.")

    print("="*80)

    # JSON으로 저장
    output_file = Path("data") / "device_totals_final.json"
    output_file.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding='utf-8')
    _log.info(f"✓ 최종 데이터 저장: {output_file}")


if __name__ == "__main__":
    main()
