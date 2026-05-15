"""단말기 테이블 정확 추출."""
import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

def extract_device_table():
    """장비 테이블 정확 추출."""
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
            
            print(f"\n[단말기 테이블 정확 추출]\n")
            
            # 모든 테이블 찾아서 실제 데이터 테이블 식별
            table_info = current_page.evaluate("""
            (() => {
                const tables = Array.from(document.querySelectorAll('table'));
                const results = [];
                
                tables.forEach((table, idx) => {
                    const rows = Array.from(table.querySelectorAll('tbody tr'));
                    const rowCount = rows.length;
                    
                    // 데이터가 있는 첫 행 샘플
                    let sample = [];
                    if (rows.length > 0) {
                        const cells = Array.from(rows[0].querySelectorAll('td'));
                        sample = cells.slice(0, 5).map(c => c.innerText.substring(0, 20));
                    }
                    
                    results.push({
                        index: idx,
                        rows: rowCount,
                        sample: sample,
                    });
                });
                
                return results;
            })();
            """)
            
            print("테이블 정보:")
            for t in table_info:
                print(f"  테이블 {t['index']}: {t['rows']}행, 샘플: {t['sample']}")
            
            # 가장 데이터가 많은 테이블 선택 (현장별 단말기 목록)
            main_table_idx = max(range(len(table_info)), key=lambda i: table_info[i]['rows'])
            print(f"\n메인 테이블: 테이블 {main_table_idx} ({table_info[main_table_idx]['rows']}행)\n")
            
            # 메인 테이블 상세 추출
            devices_raw = current_page.evaluate(f"""
            (() => {
                const table = document.querySelectorAll('table')[{main_table_idx}];
                const rows = Array.from(table.querySelectorAll('tbody tr'));
                
                return rows.map(row => {{
                    const cells = Array.from(row.querySelectorAll('td'));
                    return cells.map(c => c.innerText.trim());
                }});
            })();
            """)
            
            print(f"추출된 행: {len(devices_raw)}개\n")
            
            # 헤더 추출
            headers = current_page.evaluate(f"""
            (() => {{
                const table = document.querySelectorAll('table')[{main_table_idx}];
                const headers = Array.from(table.querySelectorAll('thead th, thead td'));
                return headers.map(h => h.innerText.trim());
            }})();
            """)
            
            print(f"헤더 ({len(headers)}개): {headers[:8]}\n")
            
            # 데이터 정리
            devices = []
            for row in devices_raw:
                if len(row) > 5 and row[0].strip() and row[0] != '조회된 내역이 없습니다.':
                    devices.append({
                        'no': row[0] if len(row) > 0 else '',
                        'project': row[1][:50] if len(row) > 1 else '',
                        'contract': row[2] if len(row) > 2 else '',
                        'code': row[3] if len(row) > 3 else '',
                        'contractor': row[4][:30] if len(row) > 4 else '',
                        'devices': row[5] if len(row) > 5 else '',
                        'status': row[6] if len(row) > 6 else '',
                        'teardown': row[7] if len(row) > 7 else '',
                    })
            
            print(f"[정리된 단말기 현황] - {len(devices)}건\n")
            
            for i, device in enumerate(devices[:15], 1):
                print(f"{i:2}. {device['no']:3} | {device['project']:45} | {device['contract']:6}")
            
            if len(devices) > 15:
                print(f"\n... 외 {len(devices) - 15}건")
            
            # 임대 상태 분석
            statuses = {}
            for device in devices:
                status = device['status'].strip() if device['status'] else '미정'
                statuses[status] = statuses.get(status, 0) + 1
            
            print(f"\n[임대 상태별 현황]")
            for status, count in sorted(statuses.items(), key=lambda x: x[1], reverse=True):
                print(f"  {status}: {count}건")
            
            # 철거 필요 확인
            teardown_needed = [d for d in devices if '철거' in d['teardown'].lower() or '종료' in d['teardown'].lower()]
            print(f"\n[임대 종료 필요 (철거)] - {len(teardown_needed)}건")
            if teardown_needed:
                for device in teardown_needed[:5]:
                    print(f"  - {device['no']} {device['project'][:40]}")
            
            # 저장
            output_file = ROOT / "data" / "device_complete_list.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump({
                    "total": len(devices),
                    "devices": devices,
                    "statuses": statuses,
                    "teardown_needed": len(teardown_needed),
                }, f, ensure_ascii=False, indent=2)
            
            print(f"\n✓ 저장: {output_file}")
            
            browser.close()
            
    except Exception as e:
        print(f"✗ 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    extract_device_table()
