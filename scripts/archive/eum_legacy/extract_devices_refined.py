"""단말기 데이터 정밀 추출 - 필터 텍스트 제외"""
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


def extract_devices_refined() -> dict:
    """필터를 '전체'로 변경 후 정제된 데이터만 추출"""
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

    # 상태 필터를 "전체"로 변경
    page.evaluate("""
    (() => {
        const selects = document.querySelectorAll('select');
        for (let sel of selects) {
            const opts = Array.from(sel.options).map(o => o.text);
            if (opts.some(t => t.includes('진행')) && opts.some(t => t.includes('준공'))) {
                const allOpt = Array.from(sel.options).find(o => o.text.trim() === '전체');
                if (allOpt) {
                    sel.value = allOpt.value;
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                }
                break;
            }
        }
    })();
    """)

    time.sleep(2)
    page.wait_for_load_state("networkidle", timeout=10000)

    # 표시 개수를 60개로 설정
    page.evaluate("""
    (() => {
        const selects = document.querySelectorAll('select');
        for (let sel of selects) {
            const opts = Array.from(sel.options).map(o => o.text.trim());
            if (opts.some(t => t.includes('개'))) {
                const opt60 = Array.from(sel.options).find(o => o.text.includes('60'));
                if (opt60) {
                    sel.value = opt60.value;
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                }
                break;
            }
        }
    })();
    """)

    time.sleep(2)
    page.wait_for_load_state("networkidle", timeout=10000)

    # 정제된 데이터 추출
    all_devices = []
    page_num = 1

    while True:
        rows_data = page.evaluate("""
        (() => {
            const rows = document.querySelectorAll('table tbody tr');
            const devices = [];

            rows.forEach((row) => {
                const cells = row.querySelectorAll('td');
                if (cells.length > 0) {
                    const noText = cells[0]?.innerText?.trim() || '';
                    const projectText = cells[1]?.innerText?.trim() || '';

                    // NO가 숫자인 행만 추출 (실제 데이터)
                    // 필터 텍스트나 합계 행 제외
                    if (/^\\d+$/.test(noText) && projectText && !projectText.includes('전체') && !projectText.includes('선택')) {
                        const device = {
                            no: noText,
                            project: projectText,
                            contract: cells[2]?.innerText?.trim() || '',
                            code: cells[3]?.innerText?.trim() || '',
                            contractor: cells[4]?.innerText?.trim() || '',
                            device_count: cells[5]?.innerText?.trim() || '1',
                            card_info: cells[6]?.innerText?.trim() || '',
                            status: cells.length > 10 ? (cells[10]?.innerText?.trim() || '') : '',
                            teardown_date: cells.length > 11 ? (cells[11]?.innerText?.trim() || '') : ''
                        };

                        devices.push(device);
                    }
                }
            });

            return devices;
        })();
        """)

        if not rows_data:
            _log.info(f"[페이지{page_num}] 유효한 데이터 없음")
            break

        _log.info(f"[페이지{page_num}] {len(rows_data)}개 레코드 추출")
        all_devices.extend(rows_data)

        # 다음 페이지 확인
        has_next = page.evaluate("""
        (() => {
            const nextBtn = document.querySelector('a[title="다음"]');
            return nextBtn && nextBtn.offsetParent !== null;
        })();
        """)

        if not has_next:
            _log.info(f"다음 페이지 없음 (총 {page_num}페이지)")
            break

        try:
            page.click('a[title="다음"]')
            time.sleep(2)
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as e:
            _log.error(f"페이지 이동 실패: {e}")
            break

        page_num += 1

    # 통계 계산
    total_devices = 0
    active = 0
    terminated = 0

    for device in all_devices:
        try:
            count = int(device.get('device_count', '1'))
        except:
            count = 1

        total_devices += count

        # teardown_date가 없으면 진행 중
        if not device.get('teardown_date'):
            active += count
        else:
            terminated += count

    result = {
        "total_records": len(all_devices),
        "total_devices": total_devices,
        "active_rentals": active,
        "terminated_rentals": terminated,
        "pages": page_num,
        "devices": all_devices,
        "summary": {
            "현재_임대중": active,
            "임대_종료_반납대기": terminated,
            "총_단말기수": total_devices
        }
    }

    return result


if __name__ == "__main__":
    try:
        result = extract_devices_refined()

        # 결과 출력
        print("\n" + "="*70)
        print("[건설근로자공제회 단말기 보유 현황]")
        print("="*70)
        print(f"총 임대 프로젝트: {result['total_records']}건")
        print(f"총 단말기 수: {result['total_devices']}대")
        print(f"  ✓ 현재 임대 중: {result['active_rentals']}대")
        print(f"  ⚠ 임대 종료(반납대기): {result['terminated_rentals']}대")
        print(f"조회 페이지: {result['pages']}페이지")
        print("="*70)

        if result['devices']:
            print(f"\n[임대 진행 중 프로젝트 ({result['active_rentals']}대)]")
            for device in result['devices']:
                if not device.get('teardown_date'):
                    print(f"  ✓ NO:{device['no']} | {device['project'][:40]}... | {device['device_count']}대")

            print(f"\n[임대 종료 대기 프로젝트 ({result['terminated_rentals']}대)]")
            count = 0
            for device in result['devices']:
                if device.get('teardown_date'):
                    if count < 10:  # 상위 10개만
                        print(f"  - NO:{device['no']} | {device['project'][:40]}... | 종료:{device['teardown_date']}")
                        count += 1
            if result['terminated_rentals'] > 10:
                print(f"  ... 외 {result['terminated_rentals'] - 10}대")

        # JSON 저장
        output_file = Path("data") / "device_inventory_final.json"
        output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        _log.info(f"✓ 단말기 인벤토리 저장: {output_file}")

    except Exception as e:
        _log.error(f"추출 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
