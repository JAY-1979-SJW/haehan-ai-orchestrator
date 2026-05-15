"""건설근로자공제회 단말기 데이터 심층 분석
- 단말기 관리 페이지의 모든 필터/뷰 조사
- 고장신고/실패 관리 페이지 조사
- 통계 데이터 추출
- 각 페이지의 테이블 구조와 데이터 상세 파악
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


def analyze_single_page(page, page_id: str, page_name: str) -> dict:
    """개별 페이지 상세 분석"""
    url = f"https://eum.cw.or.kr/web/man/{page_id}"

    print(f"\n{'='*80}")
    print(f"[{page_name}] {page_id}")
    print(f"{'='*80}")
    print(f"URL: {url}\n")

    try:
        page.goto(url, timeout=30000)
        page.wait_for_load_state("load", timeout=5000)

        try:
            from scripts.popup_detector import handle_page_popups
            handle_page_popups(page, timeout_s=2.0)
        except:
            pass

        # 페이지 구조 분석
        page_structure = page.evaluate("""
        (() => {
            const analysis = {
                title: document.title,
                hasTable: !!document.querySelector('table'),
                hasTabs: !!document.querySelector('[class*="tab"], [role="tab"]'),
                filters: [],
                stats: [],
                buttons: [],
                pageInfo: ''
            };

            // 필터/선택 옵션 분석
            const selects = document.querySelectorAll('select');
            selects.forEach(sel => {
                const opts = Array.from(sel.options).map(o => ({
                    value: o.value,
                    text: o.text
                }));
                analysis.filters.push({
                    name: sel.name || sel.id || '(이름없음)',
                    options: opts,
                    count: opts.length
                });
            });

            // 테이블 정보
            if (analysis.hasTable) {
                const table = document.querySelector('table');
                const headers = Array.from(table.querySelectorAll('thead th')).map(h => h.innerText.trim());
                const rowCount = table.querySelectorAll('tbody tr').length;

                analysis.tableInfo = {
                    headers: headers,
                    headerCount: headers.length,
                    rowCount: rowCount
                };
            }

            // 통계 정보 (큰 숫자 포함 텍스트 찾기)
            document.querySelectorAll('*').forEach(el => {
                const text = el.innerText?.trim() || '';
                // 2자 이상 5자 이하의 숫자가 있는 경우
                if (/\\d{2,5}/.test(text) && text.length < 50 && !text.includes('\\n')) {
                    if (!analysis.stats.some(s => s === text)) {
                        analysis.stats.push(text);
                    }
                }
            });

            // 버튼 텍스트
            document.querySelectorAll('button, a[class*="btn"]').forEach(btn => {
                const text = btn.innerText?.trim() || '';
                if (text && text.length > 1 && text.length < 30) {
                    if (!analysis.buttons.some(b => b === text)) {
                        analysis.buttons.push(text);
                    }
                }
            });

            // 페이지 정보 텍스트
            const infoEl = document.querySelector('[class*="info"], [class*="message"]');
            if (infoEl) {
                analysis.pageInfo = infoEl.innerText?.trim() || '';
            }

            return analysis;
        })();
        """)

        # 결과 출력
        print(f"[페이지 정보]")
        print(f"  제목: {page_structure['title']}")
        print(f"  테이블: {'있음' if page_structure['hasTable'] else '없음'}")

        if page_structure.get('tableInfo'):
            table = page_structure['tableInfo']
            print(f"\n[테이블 구조]")
            print(f"  열: {table['headerCount']}개")
            print(f"  행: {table['rowCount']}개")
            print(f"  헤더: {', '.join(table['headers'][:8])}")
            if len(table['headers']) > 8:
                print(f"          ... 외 {len(table['headers'])-8}개")

        if page_structure['filters']:
            print(f"\n[필터 옵션] ({len(page_structure['filters'])}개)")
            for i, filt in enumerate(page_structure['filters'][:5], 1):
                print(f"  {i}. {filt['name']} ({filt['count']}개)")
                for opt in filt['options'][:5]:
                    if opt['text']:
                        print(f"     - {opt['text']}")
                if len(filt['options']) > 5:
                    print(f"     ... 외 {len(filt['options'])-5}개")

        if page_structure['stats']:
            print(f"\n[통계/숫자 정보]")
            for stat in page_structure['stats'][:10]:
                print(f"  • {stat}")

        if page_structure['buttons']:
            print(f"\n[주요 버튼/액션]")
            for btn in page_structure['buttons'][:8]:
                print(f"  • {btn}")

        return {
            'page_id': page_id,
            'page_name': page_name,
            'url': url,
            'structure': page_structure
        }

    except Exception as e:
        _log.error(f"페이지 분석 오류: {e}")
        return {
            'page_id': page_id,
            'page_name': page_name,
            'error': str(e)
        }


def main():
    """메인 분석"""
    page = get_page()

    # 분석할 주요 페이지들
    pages_to_analyze = [
        ("WEBMAN380M00", "단말기 관리"),
        ("WEBMAN381M00", "단말기 설치계획"),
        ("WEBMAN382M00", "단말기 철거"),
        ("WEBMAN310M00", "고장신고/실패"),
        ("WEBMAN390M00", "기타 관리"),
        ("WEBMAN400M00", "통계/보고서"),
    ]

    results = []
    for page_id, page_name in pages_to_analyze:
        result = analyze_single_page(page, page_id, page_name)
        results.append(result)
        time.sleep(1)  # 페이지 간 대기

    # 최종 요약
    print("\n" + "="*80)
    print("[분석 요약]")
    print("="*80)

    print(f"\n[성공적으로 분석된 페이지]")
    for result in results:
        if 'error' not in result:
            print(f"  ✓ {result['page_name']:<20} | 필터: {len(result['structure']['filters'])}개, 통계: {len(result['structure']['stats'])}개")
        else:
            print(f"  ✗ {result['page_name']:<20} | 오류: {result['error']}")

    # JSON으로 저장
    output_file = Path("data") / "deep_device_analysis.json"
    output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    _log.info(f"✓ 심층 분석 결과 저장: {output_file}")

    print(f"\n✓ 결과 저장: {output_file}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log.error(f"분석 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
