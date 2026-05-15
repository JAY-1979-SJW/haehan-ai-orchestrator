"""전체 40대 단말기 현황 완전 스캔
- WEBMAN380M00: 모든 페이지 데이터 추출 (페이지네이션 처리)
- 영천 포함 모든 임대 현장 파악
- 각 현장별 단말기 수/상태 정리
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page
from scripts.logger import get_logger

_log = get_logger(__name__)


def scan_all_pages() -> dict:
    """모든 페이지의 단말기 데이터 추출"""
    page = get_page()

    url = "https://eum.cw.or.kr/web/man/WEBMAN380M00"
    _log.info(f"[전체 스캔 시작] {url}")
    page.goto(url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    all_devices = []
    page_num = 0
    max_pages = 10  # 안전장치

    print("\n" + "="*80)
    print("[1단계] WEBMAN380M00 - 모든 페이지 스캔 (필터: 현재 임대 진행 중)")
    print("="*80)

    # 페이지 1: 현재 상태 그대로 (필터 변경 없음)
    while page_num < max_pages:
        page_num += 1
        _log.info(f"[페이지 {page_num}] 스캔 중...")

        # 현재 페이지의 데이터 추출 - 매우 상세하게
        page_data = page.evaluate("""
        (() => {
            // 모든 tbody 찾기 (여러 테이블일 수 있음)
            const allBodies = document.querySelectorAll('tbody');
            const allDevices = [];

            allBodies.forEach((tbody, bodyIdx) => {
                const rows = tbody.querySelectorAll('tr');
                rows.forEach((row, rowIdx) => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length > 0) {
                        const cellTexts = Array.from(cells).map(c => c.innerText?.trim() || '');

                        // 데이터 행 판단: 첫 셀이 숫자, 두 번째 셀이 텍스트(프로젝트명)
                        if (cellTexts.length > 1 &&
                            /^\\d+$/.test(cellTexts[0]) &&
                            cellTexts[1].length > 5 &&
                            !cellTexts[1].includes('선택') &&
                            !cellTexts[1].includes('전체')) {

                            allDevices.push({
                                no: cellTexts[0],
                                project: cellTexts[1],
                                contract: cellTexts[2] || '',
                                code: cellTexts[3] || '',
                                device_count: cellTexts[5] || '1',
                                card_info: cellTexts[6] || '',
                                // 나머지 모든 셀도 저장 (열 위치 파악용)
                                all_cells: cellTexts
                            });
                        }
                    }
                });
            });

            return {
                devices: allDevices,
                totalDeviceCount: allDevices.reduce((sum, d) => {
                    return sum + (parseInt(d.device_count) || 1);
                }, 0)
            };
        })();
        """)

        if not page_data['devices']:
            _log.info(f"[페이지 {page_num}] 데이터 없음")
            break

        all_devices.extend(page_data['devices'])
        _log.info(f"[페이지 {page_num}] {len(page_data['devices'])}건 추출, 누계: {len(all_devices)}건")

        print(f"  페이지 {page_num}: {len(page_data['devices'])}개 프로젝트")
        for device in page_data['devices'][:3]:
            print(f"    • NO:{device['no']} | {device['project'][:35]}... | {device['device_count']}대")

        # 다음 페이지 확인 및 이동
        has_next = page.evaluate("""
        (() => {
            const nextBtn = document.querySelector('a[title="다음"]');
            const nextDisabled = nextBtn?.classList.contains('disabled') || nextBtn?.style.display === 'none';
            return nextBtn && !nextDisabled && nextBtn.offsetParent !== null;
        })();
        """)

        if not has_next:
            _log.info(f"다음 페이지 없음 (총 {page_num}페이지)")
            break

        # 다음 페이지로 이동
        try:
            page.click('a[title="다음"]')
            time.sleep(2)
            page.wait_for_load_state("load", timeout=5000)
        except Exception as e:
            _log.error(f"페이지 이동 실패: {e}")
            break

    # 데이터 정리 및 분석
    print(f"\n{'='*80}")
    print("[2단계] 수집 데이터 분석")
    print(f"{'='*80}")

    total_device_count = sum(int(d.get('device_count', '1')) for d in all_devices)

    print(f"\n✓ 총 프로젝트 레코드: {len(all_devices)}건")
    print(f"✓ 총 단말기 수: {total_device_count}대\n")

    # 현장별 분류
    locations = {}
    for device in all_devices:
        project = device['project']
        count = int(device.get('device_count', '1'))

        # 현장명에서 지역 추출 (키워드 기반)
        location = '기타'
        if '영천' in project:
            location = '영천'
        elif '서울' in project:
            location = '서울'
        elif '경기' in project or '양주' in project or '인천' in project:
            location = '수도권'
        elif '부산' in project or '대구' in project:
            location = '영남권'

        if location not in locations:
            locations[location] = {'count': 0, 'projects': []}

        locations[location]['count'] += count
        locations[location]['projects'].append({
            'no': device['no'],
            'project': device['project'],
            'count': count
        })

    # 현장별 요약 출력
    print("[현장별 분류]")
    for location in sorted(locations.keys()):
        info = locations[location]
        print(f"  {location:<10}: {info['count']:2}대 ({len(info['projects'])}개 프로젝트)")
        for proj in info['projects'][:2]:
            print(f"    • {proj['project'][:50]}")
        if len(info['projects']) > 2:
            print(f"    ... 외 {len(info['projects'])-2}개")

    # 최종 데이터 저장
    result = {
        "total_projects": len(all_devices),
        "total_devices": total_device_count,
        "by_location": locations,
        "all_devices": all_devices,
        "pages_scanned": page_num
    }

    return result


def main():
    try:
        result = scan_all_pages()

        # 최종 요약
        print(f"\n{'='*80}")
        print("[최종 요약]")
        print(f"{'='*80}")
        print(f"\n총 보유 단말기: {result['total_devices']}대 (프로젝트 {result['total_projects']}건)")
        print(f"조회 페이지: {result['pages_scanned']}개\n")

        if result['total_devices'] < 40:
            print(f"⚠️  주의: 조회된 {result['total_devices']}대 < 보유 40대")
            print(f"   → 다른 필터/페이지에 {40 - result['total_devices']}대가 더 있을 수 있습니다")
            print(f"   → 다음 단계: WEBMAN390M00, WEBMAN400M00 등 다른 페이지 확인 필요\n")
        elif result['total_devices'] == 40:
            print(f"✓ 정확히 40대 확인됨!")
        else:
            print(f"⚠️  조회된 {result['total_devices']}대 > 보유 40대")
            print(f"   → 중복 카운트 가능성 확인 필요\n")

        # JSON 저장
        output_file = Path("data") / "complete_inventory_scan.json"
        output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        _log.info(f"✓ 스캔 결과 저장: {output_file}")

        return result

    except Exception as e:
        _log.error(f"스캔 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
