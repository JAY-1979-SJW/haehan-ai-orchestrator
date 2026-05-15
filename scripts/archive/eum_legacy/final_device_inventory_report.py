"""최종 단말기 재고 현황 보고서
- 현재 임대 중: 종료일이 없는 프로젝트의 단말기
- 임대 완료(반납 대기): 종료일이 있는 프로젝트의 단말기
- 전체 보유: 모든 단말기
"""
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


def main():
    page = get_page()

    url = "https://eum.cw.or.kr/web/man/WEBMAN380M00"
    page.goto(url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

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
            }
        }
    })();
    """)

    time.sleep(2)
    page.wait_for_load_state("load", timeout=5000)

    # 상세 데이터 추출 (현재 진행 상태 포함)
    full_data = page.evaluate("""
    (() => {
        const rows = document.querySelectorAll('table tbody tr');
        const devices = [];

        rows.forEach((row, idx) => {
            const cells = row.querySelectorAll('td');
            if (cells.length > 0) {
                const noText = cells[0]?.innerText?.trim() || '';

                // NO가 숫자인 행만
                if (/^\\d+$/.test(noText)) {
                    // 가능한 모든 셀 텍스트 추출 (정확한 열 위치를 모르므로)
                    const allCellTexts = Array.from(cells).map(c => c.innerText?.trim() || '');

                    const device = {
                        no: noText,
                        project: cells[1]?.innerText?.trim() || '',
                        contract: cells[2]?.innerText?.trim() || '',
                        code: cells[3]?.innerText?.trim() || '',
                        contractor: cells[4]?.innerText?.trim() || '',
                        device_count: parseInt(cells[5]?.innerText?.trim() || '1'),
                        card_info: cells[6]?.innerText?.trim() || '',
                        status_indicator: cells[7]?.innerText?.trim() || '',
                        teardown_date: cells[11]?.innerText?.trim() || '',  // 대략적인 위치
                        // 모든 셀 내용도 저장해서 나중에 분석 가능하게
                        all_cells: allCellTexts.slice(0, 15)
                    };

                    if (device.project) {
                        devices.push(device);
                    }
                }
            }
        });

        return {
            devices: devices,
            count: devices.length,
            totalDeviceCount: devices.reduce((sum, d) => sum + d.device_count, 0)
        };
    })();
    """)

    # 데이터 분석 및 정리
    print("\n" + "="*80)
    print("[건설근로자공제회 단말기 보유 현황 최종 분석]")
    print("="*80)

    all_devices = full_data['devices']
    print(f"\n조회된 프로젝트: {full_data['count']}건")
    print(f"조회된 단말기: {full_data['totalDeviceCount']}대\n")

    # 종료날짜가 없는 것 (현재 임대 중) / 있는 것 (임대 완료)
    active = []
    completed = []

    for device in all_devices:
        # teardown_date가 공백이거나 없으면 진행 중
        # 날짜 형식이 있으면 완료
        has_date = device['teardown_date'] and device['teardown_date'].strip() and device['teardown_date'] != '-'

        if has_date:
            completed.append(device)
        else:
            active.append(device)

    active_count = sum(d['device_count'] for d in active)
    completed_count = sum(d['device_count'] for d in completed)

    print("[분류 결과]")
    print(f"  ✓ 현재 임대 중:        {len(active):2}개 프로젝트 → {active_count:2}대 단말기")
    print(f"  ⚠ 임대 완료(반납대기): {len(completed):2}개 프로젝트 → {completed_count:2}대 단말기")
    print(f"  ─────────────────────────────────────")
    print(f"  총합:                {len(all_devices):2}개 프로젝트 → {active_count + completed_count:2}대 단말기")

    # 현재 임대 중인 항목 상세
    print(f"\n{'='*80}")
    print("[현재 임대 중인 프로젝트]")
    print(f"{'='*80}")
    for device in active:
        print(f"  NO:{device['no']:2} | {device['project'][:50]:<50} | {device['device_count']}대")

    # 임대 완료 항목 상세 (상위 10개)
    print(f"\n{'='*80}")
    print(f"[임대 완료 프로젝트] ({len(completed)}개)")
    print(f"{'='*80}")
    for i, device in enumerate(completed[:10], 1):
        print(f"  {i:2}. NO:{device['no']} | {device['project'][:45]:<45} | 종료:{device['teardown_date']:12} | {device['device_count']}대")
    if len(completed) > 10:
        print(f"  ... 외 {len(completed)-10}개 프로젝트")

    # 최종 요약
    summary = {
        "survey_date": datetime.now().isoformat(),
        "status": "완료",
        "summary": {
            "현재_임대_중": {
                "프로젝트_건수": len(active),
                "단말기_수": active_count
            },
            "임대_완료_반납대기": {
                "프로젝트_건수": len(completed),
                "단말기_수": completed_count
            },
            "총합": {
                "프로젝트_건수": len(all_devices),
                "단말기_수": active_count + completed_count
            }
        },
        "active_projects": active,
        "completed_projects": completed
    }

    # JSON으로 저장
    output_file = Path("data") / "device_inventory_final_report.json"
    output_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    print(f"\n{'='*80}")
    print("[답변]")
    print(f"{'='*80}")
    print(f"\n1️⃣  현재 임대중인 단말기: {active_count}대")
    print(f"    (프로젝트: {len(active)}건)\n")
    print(f"2️⃣  총 보유 단말기: {active_count + completed_count}대")
    print(f"    (임대 중: {active_count}대, 반납 대기: {completed_count}대)")
    print(f"    (프로젝트: {len(all_devices)}건)\n")
    print(f"{'='*80}\n")

    _log.info(f"✓ 최종 보고서 저장: {output_file}")

    return summary


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log.error(f"분석 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
