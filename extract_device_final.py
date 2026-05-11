"""단말기 최종 추출."""
import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

def extract_devices():
    """단말기 데이터 추출."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            contexts = browser.contexts
            context = contexts[0]
            pages = context.pages
            
            current_page = pages[-1] if pages else None
            
            if not current_page:
                print("활성 페이지 없음")
                return
            
            print(f"\n[단말기 현황 최종 추출]\n")
            
            # 모든 테이블의 모든 데이터 추출
            data = current_page.evaluate("""
            (() => {
                const tables = document.querySelectorAll('table');
                const allTables = [];
                
                tables.forEach((table, idx) => {
                    const rows = Array.from(table.querySelectorAll('tbody tr')).map(row =>
                        Array.from(row.querySelectorAll('td')).map(c => c.innerText.trim())
                    );
                    
                    if (rows.length > 0) {
                        allTables.push({
                            index: idx,
                            rowCount: rows.length,
                            rows: rows
                        });
                    }
                });
                
                return allTables;
            })();
            """)
            
            print(f"총 {len(data)}개 테이블 발견\n")
            
            # 가장 큰 테이블 찾기
            main_table = max(data, key=lambda t: t['rowCount'])
            print(f"메인 테이블: 테이블 {main_table['index']} ({main_table['rowCount']}행)\n")
            
            # 데이터 정리
            devices = []
            for row in main_table['rows']:
                if len(row) > 1 and row[0].strip() and '조회' not in row[0]:
                    try:
                        no = int(row[0].strip()) if row[0].strip().isdigit() else row[0]
                        if isinstance(no, int):
                            devices.append({
                                'no': row[0],
                                'project': row[1][:60] if len(row) > 1 else '',
                                'contract': row[2] if len(row) > 2 else '',
                                'code': row[3] if len(row) > 3 else '',
                                'contractor': row[4][:30] if len(row) > 4 else '',
                                'device_count': row[5] if len(row) > 5 else '0',
                                'card_info': row[6] if len(row) > 6 else '',
                                'teardown_date': row[7] if len(row) > 7 else '',
                                'completion': row[8] if len(row) > 8 else '',
                                'location': row[9][:40] if len(row) > 9 else '',
                            })
                    except:
                        pass
            
            print(f"[정렬된 단말기 목록] - {len(devices)}건\n")
            
            # 출력
            for i, dev in enumerate(devices, 1):
                print(f"{i:2}. NO:{dev['no']:3} | {dev['project']:55}")
                if dev['teardown_date']:
                    print(f"     철거일: {dev['teardown_date']}")
                if dev['completion']:
                    print(f"     준공: {dev['completion']}")
            
            # 상태 분석
            teardown_count = sum(1 for d in devices if d['teardown_date'] and d['teardown_date'].strip())
            
            print(f"\n[현황 요약]")
            print(f"  총 단말기: {len(devices)}개")
            print(f"  임대 종료(철거일 있음): {teardown_count}개")
            print(f"  진행 중: {len(devices) - teardown_count}개")
            
            # JSON 저장
            output = ROOT / "data" / "final_device_status.json"
            with open(output, "w", encoding="utf-8") as f:
                json.dump({
                    "total_devices": len(devices),
                    "teardown_required": teardown_count,
                    "active_devices": len(devices) - teardown_count,
                    "devices": devices,
                    "analysis_date": "2026-05-11",
                }, f, ensure_ascii=False, indent=2)
            
            print(f"\n✓ 저장: {output}")
            
            browser.close()
            
    except Exception as e:
        print(f"✗ 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    extract_devices()
