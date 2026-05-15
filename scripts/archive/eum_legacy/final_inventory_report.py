"""40대 단말기 최종 분석 보고서"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.logger import get_logger

_log = get_logger(__name__)


def main():
    # 이전에 추출한 HTML 분석 결과 로드
    data_file = Path("data") / "html_direct_analysis.json"

    with open(data_file, 'r', encoding='utf-8') as f:
        results = json.load(f)

    # WEBMAN390M00의 40개 단말기 데이터 찾기
    webman390_data = next(
        (r for r in results if 'WEBMAN390M00' in r['name']),
        None
    )

    if not webman390_data or not webman390_data['data']:
        print("❌ 데이터 없음")
        return

    devices_raw = webman390_data['data']

    print("\n" + "="*90)
    print("📊 건설근로자공제회 단말기 보유 현황 최종 분석 보고서")
    print("="*90)
    print(f"조회 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"데이터 출처: WEBMAN390M00 - 단말기설치현황\n")

    # 1. 데이터 구조 분석 및 컬럼 파싱
    # 각 행은 2개의 부분으로 나뉨 (메인 정보 + 상세 정보)
    # 패턴: NO, 고유번호, 수량, 공제번호, 프로젝트명, 위치, ... 그 다음 행이 추가 정보

    devices = []
    i = 0
    while i < len(devices_raw):
        main_row = devices_raw[i]

        device = {
            'no': main_row[0] if len(main_row) > 0 else '',
            'unique_id': main_row[1] if len(main_row) > 1 else '',
            'quantity': main_row[2] if len(main_row) > 2 else '1',
            'insurance_number': main_row[3] if len(main_row) > 3 else '',
            'project': main_row[4] if len(main_row) > 4 else '',
            'location': main_row[5] if len(main_row) > 5 else '',
            'type_flag': main_row[6] if len(main_row) > 6 else '',  # 의무/자율
            'manager': main_row[7] if len(main_row) > 7 else '',
            'device_type': main_row[8] if len(main_row) > 8 else '',  # 이동형/벽부형
            'status': main_row[9] if len(main_row) > 9 else '',  # 정상/장애
            'end_date': main_row[10] if len(main_row) > 10 else '',
            'teardown_status': main_row[11] if len(main_row) > 11 else '',
            'rental_type': main_row[12] if len(main_row) > 12 else '',  # 임대/구매
            'additional': main_row[13] if len(main_row) > 13 else '',
        }

        # 숫자로 시작하는 행인 경우만 유효한 데이터
        if device['no'].isdigit():
            devices.append(device)

        i += 1

    print(f"✓ 파싱된 단말기: {len(devices)}대\n")

    # 2. 상태별 분류
    print("["*1 + "상태별 분류" + "]"*1)
    print("─"*90)

    by_rental = defaultdict(list)
    by_status = defaultdict(list)
    by_location = defaultdict(list)
    rental_count = 0

    for device in devices:
        rental = device['rental_type'].strip()
        by_rental[rental].append(device)

        status = device['status'].strip()
        by_status[status].append(device)

        location = device['location'].strip().split('시')[0] + '시' if '시' in device['location'] else device['location'].strip()[:3]
        by_location[location].append(device)

        if '임대' in rental:
            rental_count += 1

    print(f"\n임대 현황:")
    for rental_type, items in sorted(by_rental.items()):
        print(f"  • {rental_type:<10}: {len(items):2}대")

    print(f"\n상태별 현황:")
    for status, items in sorted(by_status.items()):
        print(f"  • {status:<10}: {len(items):2}대")

    # 3. 임대 현장별 분류
    print(f"\n{'─'*90}")
    print("["*1 + "임대 현장 분석" + "]"*1)
    print(f"{'─'*90}\n")

    rented_devices = by_rental.get('임대', [])
    print(f"임대 중인 단말기: {len(rented_devices)}대\n")

    # 현장별 그룹화
    rental_by_location = defaultdict(list)
    for device in rented_devices:
        location = device['location'].strip()
        rental_by_location[location].append(device)

    for location in sorted(rental_by_location.keys()):
        items = rental_by_location[location]
        print(f"[{location}] {len(items)}대")
        for device in items[:3]:
            end_date = device['end_date']
            project = device['project'][:40]
            print(f"  • NO:{device['no']:<2} {project:<40} 종료:{end_date}")

        if len(items) > 3:
            print(f"  ... 외 {len(items)-3}대")

    # 4. 영천 확인
    print(f"\n{'─'*90}")
    print("["*1 + "영천 현장 확인" + "]"*1)
    print(f"{'─'*90}\n")

    yeongcheon_devices = [d for d in devices if '영천' in d['location']]
    if yeongcheon_devices:
        print(f"✓ 영천 현장: {len(yeongcheon_devices)}대")
        for device in yeongcheon_devices:
            rental_status = device['rental_type']
            print(f"  • NO:{device['no']:<2} {device['project']:<40} 임대상태: {rental_status}")
    else:
        print("✗ 영천 현장 데이터 없음 (또는 다른 이름으로 등록됨)")

    # 5. 최종 요약
    print(f"\n{'='*90}")
    print("📋 최종 요약")
    print(f"{'='*90}\n")

    print(f"1️⃣  총 보유 단말기: {len(devices)}대")
    print(f"   ✓ 임대 중: {len(rented_devices)}대")
    print(f"   ✓ 구매/기타: {len(by_rental.get('구매', []))}대")
    print(f"   ✓ 기타: {len(by_rental.get('기타', [])) + len([d for d in devices if d['rental_type'].strip() not in ['임대', '구매']])}대")

    print(f"\n2️⃣  상태별:")
    for status, items in sorted(by_status.items()):
        print(f"   • {status:<15}: {len(items):2}대")

    print(f"\n3️⃣  지역별 분포:")
    for location in sorted(by_location.keys(), key=lambda x: len(by_location[x]), reverse=True):
        items = by_location[location]
        print(f"   • {location:<20}: {len(items):2}대")

    print(f"\n4️⃣  임대 현장 수: {len(rental_by_location)}개")
    print(f"   현장: {', '.join(sorted(rental_by_location.keys()))}")

    # JSON으로 저장
    final_report = {
        'survey_date': datetime.now().isoformat(),
        'total_devices': len(devices),
        'rental_devices': len(rented_devices),
        'rental_locations': len(rental_by_location),
        'yeongcheon_count': len(yeongcheon_devices),
        'by_rental_type': {k: len(v) for k, v in by_rental.items()},
        'by_status': {k: len(v) for k, v in by_status.items()},
        'by_location': {k: len(v) for k, v in by_location.items()},
        'rental_by_location': {k: [
            {
                'no': d['no'],
                'project': d['project'],
                'location': d['location'],
                'end_date': d['end_date'],
                'status': d['status']
            } for d in v
        ] for k, v in rental_by_location.items()},
        'all_devices': [
            {
                'no': d['no'],
                'unique_id': d['unique_id'],
                'project': d['project'],
                'location': d['location'],
                'status': d['status'],
                'rental_type': d['rental_type'],
                'device_type': d['device_type'],
                'end_date': d['end_date']
            } for d in devices
        ]
    }

    output_file = Path("data") / "final_inventory_report.json"
    output_file.write_text(json.dumps(final_report, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"\n✓ 최종 보고서 저장: {output_file}\n")
    print("="*90 + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log.error(f"분석 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
