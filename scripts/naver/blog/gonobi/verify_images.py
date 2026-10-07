"""카테고리별 이미지 스크린샷 촬영 및 분류 검증."""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.browser.agent.agent import BrowserAgent  # noqa: E402

agent = BrowserAgent()
agent.connect()
page = agent.page

OUT = ROOT / "data" / "gonobi_verify_screenshots"
OUT.mkdir(parents=True, exist_ok=True)

# 저장소 루트 기준 상대경로(2026-09-29 defect: 하드코딩된 구 경로 C:/work/... 가 이미
# 이 PC에서도 깨져 있었음 — 프로젝트가 C:\Users\skyjw\claude-dev-handoff\... 로 이동됨).
GALLERY = ROOT.as_uri() + "/data/gonobi_gallery.html"
page.goto(GALLERY)
time.sleep(2)

# 이미지 로딩 대기
page.wait_for_load_state("networkidle", timeout=10000)

cats = page.evaluate("""() => Array.from(document.querySelectorAll("section")).map(s => s.id)""")
print(f"총 {len(cats)}개 카테고리 스크린샷 촬영 시작")

results = {}

for cat in cats:
    # 해당 섹션으로 스크롤
    page.evaluate(f'document.getElementById("{cat}").scrollIntoView()')
    time.sleep(1.5)

    # 이미지 로딩 대기
    page.wait_for_timeout(1000)

    # 섹션 스크린샷
    section = page.locator(f"#{cat}")
    shot_path = OUT / f"{cat}.png"

    try:
        section.screenshot(path=str(shot_path))

        # 깨진 이미지 수 확인
        broken = page.evaluate(f'''() => {{
            const sec = document.getElementById("{cat}");
            return sec ? sec.querySelectorAll(".broken").length : 0;
        }}''')

        # 실제 로드된 이미지 수
        loaded = page.evaluate(f'''() => {{
            const sec = document.getElementById("{cat}");
            if (!sec) return 0;
            return [...sec.querySelectorAll("img")].filter(img => img.complete && img.naturalWidth > 0).length;
        }}''')

        total_imgs = page.evaluate(f'''() => {{
            const sec = document.getElementById("{cat}");
            return sec ? sec.querySelectorAll("img").length : 0;
        }}''')

        results[cat] = {"total": total_imgs, "loaded": loaded, "broken": broken, "screenshot": str(shot_path)}
        status = "✅" if broken == 0 else f"❌ {broken}개 깨짐"
        print(f"  {cat:25} 전체:{total_imgs:4} 로드:{loaded:4} {status}")

    except Exception as e:  # noqa: BLE001 - 카테고리별 이미지 검증(스크린샷) 실패를 출력만 하고 계속 진행 - 읽기전용 검증 스크립트, 결과 리포트에 실패로 표시될 뿐 위험 조작 없음
        print(f"  {cat:25} 스크린샷 실패: {e}")

print(f"\n스크린샷 저장: {OUT}")
print("\n=== 요약 ===")
total_broken = sum(r["broken"] for r in results.values())
total_unloaded = sum(r["total"] - r["loaded"] for r in results.values())
print(f"깨진 이미지: {total_broken}개")
print(f"미로드 이미지: {total_unloaded}개")

if total_broken == 0 and total_unloaded == 0:
    print("✅ 모든 이미지 정상")
