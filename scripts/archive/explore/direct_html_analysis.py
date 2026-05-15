"""페이지 HTML을 직접 분석하여 데이터 추출"""
from __future__ import annotations

import json
import sys
import time
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page
from scripts.logger import get_logger

_log = get_logger(__name__)


def extract_from_page_content(page_content: str) -> list:
    """HTML 내용에서 데이터 추출"""
    # <tr><td> 패턴으로 모든 테이블 행 추출
    tr_pattern = r'<tr[^>]*>(.*?)</tr>'
    td_pattern = r'<td[^>]*>(.*?)</td>'

    matches = re.findall(tr_pattern, page_content, re.DOTALL)
    rows = []

    for match in matches:
        cells = re.findall(td_pattern, match, re.DOTALL)
        if cells:
            # HTML 태그 제거 및 텍스트 정제
            cell_texts = []
            for cell in cells:
                # HTML 태그 제거
                text = re.sub(r'<[^>]+>', '', cell)
                # 공백 정제
                text = re.sub(r'\s+', ' ', text).strip()
                if text and len(text) < 200:  # 너무 긴 텍스트는 제외
                    cell_texts.append(text)

            if cell_texts and len(cell_texts) > 2:  # 최소 3개 셀 이상
                rows.append(cell_texts)

    return rows


def analyze_page(page, url: str, page_name: str) -> dict:
    """페이지를 방문하고 내용 분석"""
    print(f"\n{'─'*80}")
    print(f"[{page_name}]")
    print(f"{url}")
    print(f"{'─'*80}")

    try:
        page.goto(url, timeout=30000)
        page.wait_for_load_state("load", timeout=5000)

        try:
            from scripts.popup_detector import handle_page_popups
            handle_page_popups(page, timeout_s=1.0)
        except:
            pass

        # 페이지 전체 HTML 가져오기
        page_content = page.content()

        # HTML에서 테이블 데이터 추출
        rows = extract_from_page_content(page_content)

        # 데이터 행 필터링
        data_rows = []
        for row in rows:
            # 필터/선택 옵션 제외 (너무 짧은 셀 또는 특정 키워드)
            if any(len(cell) > 5 for cell in row) and not any(
                keyword in ' '.join(row).lower()
                for keyword in ['선택', '전체', '당일', '당월', '전월']
            ):
                data_rows.append(row)

        print(f"✓ 테이블 행: {len(rows)}개")
        print(f"✓ 데이터 행: {len(data_rows)}개\n")

        # 샘플 출력
        if data_rows:
            print(f"[샘플 데이터] (상위 5개)")
            for i, row in enumerate(data_rows[:5], 1):
                # 첫 3개 셀만 출력
                sample = ' | '.join(row[:3])
                print(f"  {i}. {sample[:70]}")

            if len(data_rows) > 5:
                print(f"  ... 외 {len(data_rows)-5}개")

        return {
            'name': page_name,
            'url': url,
            'total_rows': len(rows),
            'data_rows': len(data_rows),
            'data': data_rows,
            'success': True
        }

    except Exception as e:
        print(f"✗ 오류: {e}")
        return {
            'name': page_name,
            'url': url,
            'error': str(e),
            'success': False
        }


def main():
    page = get_page()

    print("\n" + "="*80)
    print("🔍 HTML 직접 분석을 통한 전체 데이터 추출")
    print("="*80)

    pages = [
        ("https://eum.cw.or.kr/web/man/WEBMAN380M00", "WEBMAN380M00 - 현장별 단말기 목록"),
        ("https://eum.cw.or.kr/web/man/WEBMAN390M00", "WEBMAN390M00 - 단말기설치현황"),
        ("https://eum.cw.or.kr/web/man/WEBMAN400M00", "WEBMAN400M00 - 단말기별 이력관리"),
        ("https://eum.cw.or.kr/mypage", "마이페이지 - 대시보드"),
    ]

    results = []
    total_data_rows = 0

    for url, name in pages:
        result = analyze_page(page, url, name)
        results.append(result)
        total_data_rows += result.get('data_rows', 0)
        time.sleep(1)

    # 최종 요약
    print(f"\n{'='*80}")
    print("[최종 요약]")
    print(f"{'='*80}\n")

    print("페이지별 데이터 행 수:")
    for result in results:
        if result['success']:
            print(f"  • {result['name']:<40} : {result['data_rows']:3}행")
        else:
            print(f"  • {result['name']:<40} : 오류")

    print(f"\n총 데이터 행: {total_data_rows}개")

    if total_data_rows >= 40:
        print("✅ 40대 이상 확인됨!")
    else:
        print(f"⚠️  {total_data_rows}개 발견 (목표: 40대)")

    # JSON 저장
    output_file = Path("data") / "html_direct_analysis.json"
    output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    _log.info(f"✓ 분석 결과 저장: {output_file}")

    # 첫 번째 페이지의 상세 데이터도 따로 저장
    if results and results[0]['data']:
        webman380_data = {
            'page_id': 'WEBMAN380M00',
            'total_records': len(results[0]['data']),
            'records': results[0]['data'],
            'columns_detected': len(results[0]['data'][0]) if results[0]['data'] else 0
        }

        output_file2 = Path("data") / "webman380_detailed.json"
        output_file2.write_text(json.dumps(webman380_data, ensure_ascii=False, indent=2), encoding='utf-8')
        _log.info(f"✓ WEBMAN380M00 상세 데이터: {output_file2}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log.error(f"실행 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
