"""단말기관리 필터를 '전체'로 변경 후 모든 단말기 추출"""
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


def extract_all_devices() -> dict:
    """상태 필터를 '전체'로 변경하고 모든 단말기 추출"""
    page = get_page()

    search_page = "https://eum.cw.or.kr/web/man/WEBMAN380M00"
    _log.info(f"[단말기관리] {search_page} 접속")
    page.goto(search_page, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=10000)

    # 팝업 처리
    try:
        from scripts.popup_detector import handle_page_popups
        popup_result = handle_page_popups(page, timeout_s=2.0)
        _log.info(f"[팝업처리] {popup_result}")
    except Exception as e:
        _log.debug(f"팝업 처리 오류: {e}")

    # 상태 필터를 "전체"로 변경
    _log.info("[필터변경] 상태 필터를 '전체'로 설정...")

    filter_result = page.evaluate("""
    (() => {
        // 모든 select 찾기
        const selects = document.querySelectorAll('select');
        let statusSelect = null;

        // 상태 필터 찾기 (보통 4번째 select)
        for (let i = 0; i < selects.length; i++) {
            const opts = Array.from(selects[i].options).map(o => o.text);

            // "진행", "준공" 옵션을 가진 select 찾기
            if (opts.some(t => t.includes('진행')) && opts.some(t => t.includes('준공'))) {
                statusSelect = selects[i];
                console.log(`상태 필터 found at index ${i}`);
                break;
            }
        }

        if (statusSelect) {
            // "전체" 옵션 찾기
            const allOption = Array.from(statusSelect.options).find(o =>
                o.text.trim() === '전체'
            );

            if (allOption) {
                console.log(`선택: ${allOption.text}`);
                statusSelect.value = allOption.value;
                statusSelect.dispatchEvent(new Event('change', { bubbles: true }));
                return { success: true, changed: true };
            }
        }

        return { success: false, changed: false };
    })();
    """)

    _log.info(f"필터 변경 결과: {filter_result}")

    if filter_result.get('changed'):
        # 페이지 로드 대기
        time.sleep(2)
        page.wait_for_load_state("networkidle", timeout=10000)

    # 현재 보이는 행 수 확인
    initial_count = page.evaluate("""
    document.querySelectorAll('table tbody tr').length
    """)
    _log.info(f"현재 표시된 행: {initial_count}개")

    # 표시 개수를 60개로 설정 (있을 경우)
    page.evaluate("""
    (() => {
        const selects = document.querySelectorAll('select');

        // 개수 선택 select 찾기 (보통 마지막 select, "20개" "40개" "60개" 옵션)
        for (let sel of selects) {
            const opts = Array.from(sel.options).map(o => o.text.trim());

            if (opts.some(t => t.includes('개'))) {
                // "60개" 찾기
                const opt60 = Array.from(sel.options).find(o => o.text.includes('60'));
                if (opt60) {
                    console.log('60개 옵션 선택');
                    sel.value = opt60.value;
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                }
                break;
            }
        }
    })();
    """)

    _log.info("[필터변경] 표시 개수를 60개로 설정")
    time.sleep(2)
    page.wait_for_load_state("networkidle", timeout=10000)

    # 모든 단말기 추출 (페이지네이션 처리)
    all_devices = []
    page_num = 1

    while True:
        # 현재 페이지의 테이블 데이터 추출
        rows_data = page.evaluate("""
        (() => {
            const rows = document.querySelectorAll('table tbody tr');
            const devices = [];

            rows.forEach((row) => {
                const cells = row.querySelectorAll('td');
                if (cells.length > 0) {
                    const device = {
                        no: cells[0]?.innerText?.trim() || '',
                        project: cells[1]?.innerText?.trim() || '',
                        contract: cells[2]?.innerText?.trim() || '',
                        code: cells[3]?.innerText?.trim() || '',
                        contractor: cells[4]?.innerText?.trim() || '',
                        device_count: cells[5]?.innerText?.trim() || '1',
                        card_info: cells[6]?.innerText?.trim() || '',
                        // 나머지 열들도 필요시 추가
                    };

                    // 데이터 유효성 확인
                    if (device.no && device.project) {
                        devices.push(device);
                    }
                }
            });

            return devices;
        })();
        """)

        if not rows_data:
            _log.info(f"[페이지{page_num}] 데이터 없음, 추출 종료")
            break

        _log.info(f"[페이지{page_num}] {len(rows_data)}개 레코드 추출")
        all_devices.extend(rows_data)

        # 다음 페이지 확인
        has_next = page.evaluate("""
        (() => {
            const nextBtn = document.querySelector('a[title="다음"]');
            return nextBtn && nextBtn.offsetParent !== null && nextBtn.className !== 'disabled';
        })();
        """)

        if not has_next:
            _log.info(f"다음 페이지 없음 (총 {page_num}페이지)")
            break

        # 다음 페이지로 이동
        _log.info(f"다음 페이지로 이동...")
        try:
            page.click('a[title="다음"]')
            time.sleep(2)
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as e:
            _log.error(f"페이지 이동 실패: {e}")
            break

        page_num += 1

    # 데이터 집계
    total_devices = 0
    active_devices = 0
    terminated_devices = 0

    device_details = []

    for device in all_devices:
        try:
            count = int(device.get('device_count', '1'))
        except:
            count = 1

        # 여기서는 단순히 device_count로만 계산
        # 실제 상태는 추가 열에서 확인 필요
        total_devices += count
        device_details.append({
            'no': device.get('no'),
            'project': device.get('project'),
            'device_count': count
        })

    result = {
        "total_records": len(all_devices),
        "total_devices": total_devices,
        "devices": device_details,
        "pages": page_num,
        "extraction_date": "2026-05-11"
    }

    return result


if __name__ == "__main__":
    try:
        result = extract_all_devices()

        # 결과 출력
        print("\n" + "="*60)
        print("[전체 단말기 보유 현황]")
        print("="*60)
        print(f"총 프로젝트 레코드: {result['total_records']}건")
        print(f"총 단말기 수: {result['total_devices']}대")
        print(f"검색 페이지: {result['pages']}페이지")
        print("="*60)

        if result['total_devices'] > 0:
            print(f"\n[상위 10개 프로젝트]")
            for i, device in enumerate(result['devices'][:10], 1):
                print(f"{i}. {device['project'][:40]}... ({device['device_count']}대)")

        # JSON으로 저장
        output_file = Path("data") / "all_devices_inventory.json"
        output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        _log.info(f"✓ 전체 단말기 목록 저장: {output_file}")

    except Exception as e:
        _log.error(f"전체 단말기 추출 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
