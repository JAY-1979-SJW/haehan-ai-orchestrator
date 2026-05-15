"""모든 단말기 목록 상세 추출."""
import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

def extract_all_devices():
    """모든 단말기 목록 추출."""
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
            
            print(f"\n[전체 단말기 목록 추출]\n")
            
            # 테이블 데이터 상세 추출
            device_data = current_page.evaluate("""
            (() => {
                const table = document.querySelector('tbody');
                if (!table) return { devices: [], total: 0 };
                
                const rows = Array.from(table.querySelectorAll('tr'));
                const devices = [];
                
                rows.forEach((row, idx) => {
                    const cells = Array.from(row.querySelectorAll('td'));
                    if (cells.length > 0) {
                        const device = {
                            no: (cells[0]?.innerText || '').trim(),
                            project_name: (cells[1]?.innerText || '').trim().substring(0, 50),
                            contract_type: (cells[2]?.innerText || '').trim(),
                            project_no: (cells[3]?.innerText || '').trim(),
                            contractor: (cells[4]?.innerText || '').trim(),
                            device_count: (cells[5]?.innerText || '').trim(),
                            installation_status: (cells[6]?.innerText || '').trim(),
                            teardown_date: (cells[7]?.innerText || '').trim(),
                            completion_status: (cells[8]?.innerText || '').trim(),
                            location: (cells[9]?.innerText || '').trim().substring(0, 30),
                        };
                        devices.push(device);
                    }
                });
                
                return {
                    devices: devices,
                    total: devices.length,
                };
            })();
            """)
            
            devices = device_data['devices']
            print(f"총 단말기 현황: {len(devices)}건\n")
            
            # 상태별 분류
            statuses = {}
            installations = {}
            completions = {}
            
            for device in devices:
                # 임대 상태 (설치 상태)
                status = device['installation_status']
                if status:
                    statuses[status] = statuses.get(status, 0) + 1
                
                # 설치 상태
                install = device['installation_status']
                if install:
                    installations[install] = installations.get(install, 0) + 1
                
                # 준공 상태
                completion = device['completion_status']
                if completion:
                    completions[completion] = completions.get(completion, 0) + 1
            
            # 요약 출력
            print("[현황 요약]")
            print(f"조회된 공사 현장: {len(devices)}개\n")
            
            print("[임대 상태별]")
            for status, count in sorted(statuses.items(), key=lambda x: x[1], reverse=True):
                print(f"  - {status}: {count}개")
            
            print("\n[준공 상태별]")
            for status, count in sorted(completions.items(), key=lambda x: x[1], reverse=True):
                print(f"  - {status}: {count}개")
            
            # 상세 목록 (처음 10개)
            print("\n[단말기별 상세 현황] (처음 10개)")
            print("-" * 100)
            for i, device in enumerate(devices[:10], 1):
                print(f"{i}. {device['no']:3} | {device['project_name']:40} | 도급:{device['contract_type']:5} | 단말:{device['device_count']:3}")
                print(f"   설치상태: {device['installation_status']:10} | 준공: {device['completion_status']:10}")
                if device['teardown_date']:
                    print(f"   철거일: {device['teardown_date']}")
            
            if len(devices) > 10:
                print(f"\n... 외 {len(devices) - 10}개")
            
            # JSON 저장
            output_file = ROOT / "data" / "device_status_list.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump({
                    "total": len(devices),
                    "page_url": current_page.url,
                    "devices": devices,
                    "summary": {
                        "by_status": statuses,
                        "by_completion": completions,
                    }
                }, f, ensure_ascii=False, indent=2)
            
            print(f"\n✓ 데이터 저장: {output_file}")
            
            browser.close()
            
    except Exception as e:
        print(f"✗ 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    extract_all_devices()
