"""카카오 개발자 콘솔 앱 삭제 — 출퇴근, ERP, 입찰분석."""

import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from scripts.browser.cdp.connection import get_page

page = get_page()
BASE = "https://developers.kakao.com/console/app"

# 삭제 대상 (해한AI 1395337 제외)
DELETE_APPS = [
    {"id": "1413624", "name": "해한메이아이출퇴근"},
    {"id": "1309295", "name": "해한 AI ERP"},
    {"id": "1303517", "name": "해한AI입찰분석"},
]

for app in DELETE_APPS:
    aid = app["id"]
    print(f"\n[삭제] {app['name']} (ID: {aid})")

    # page_goto 대신 직접 goto (팝업 자동처리 우회)
    page.goto(f"{BASE}/{aid}/config", wait_until="networkidle", timeout=15000)
    time.sleep(2)

    # "앱 영구 삭제" 버튼 클릭
    try:
        page.locator("button:has-text('앱 영구 삭제')").click()
        time.sleep(3)  # 모달 렌더링 대기
    except Exception as e:  # noqa: BLE001 - 카카오 개발자콘솔 앱 영구삭제 버튼/확인모달 클릭 브라우저자동화 — 실패시 콘솔에 오류만 출력하고 다음 앱으로 넘어감(추가 삭제나 성공 위장 없음, best-effort)
        print(f"  ✗ 삭제 버튼 없음: {e}")
        continue

    # 확인 다이얼로그 처리
    try:
        time.sleep(0.5)

        # JS로 input 찾아 네이티브 value setter로 입력 (React state 업데이트)
        filled = page.evaluate(f"""() => {{
            const inp = document.querySelector('input:not([type])');
            if (!inp) return 'no_input';
            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeSetter.call(inp, '{app["name"]}');
            inp.dispatchEvent(new Event('input', {{bubbles:true}}));
            inp.dispatchEvent(new Event('change', {{bubbles:true}}));
            return inp.value;
        }}""")
        print(f"  이름 입력: '{filled}'")

        time.sleep(0.8)

        # 삭제 버튼 활성화 확인
        btn_state = page.evaluate("""() => {
            const btns = [...document.querySelectorAll('button')];
            const del = btns.find(b => b.innerText.trim() === '삭제');
            return del ? {disabled: del.disabled} : null;
        }""")
        print(f"  삭제 버튼 상태: {btn_state}")

        # Playwright native click — React 이벤트 정상 처리
        # 모달 내 삭제 버튼 (취소 버튼 바로 옆)
        del_loc = page.locator('[role=dialog] button:has-text("삭제")')
        if del_loc.count() == 0:
            del_loc = page.locator('button:has-text("삭제")').last
        del_loc.click(timeout=5000)

        page.wait_for_load_state("networkidle", timeout=10000)
        time.sleep(2)

        if aid not in page.url:
            print("  ✓ 삭제 완료")
        else:
            print(f"  ? 현재 URL: {page.url}")
    except Exception as e:  # noqa: BLE001 - 카카오 개발자콘솔 앱 영구삭제 버튼/확인모달 클릭 브라우저자동화 — 실패시 콘솔에 오류만 출력하고 다음 앱으로 넘어감(추가 삭제나 성공 위장 없음, best-effort)
        print(f"  ✗ 확인 처리 실패: {e}")

print("\n완료. 남은 앱: 해한AI (1395337)")
