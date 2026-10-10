"""상세설명 미리보기 — CDP 브라우저로 열기."""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

html_path = ROOT / "data" / "smartstore" / "description_preview.html"
url = html_path.as_uri()

pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
page = browser.contexts[0].new_page()
page.goto(url, wait_until="domcontentloaded")
page.bring_to_front()
time.sleep(2)

print("미리보기 열림:", url)
print("제목:", page.title())

checks = page.evaluate("""
() => ({
    hero:     !!document.querySelector(".pd-hero"),
    trust:    !!document.querySelector(".pd-trust"),
    features: !!document.querySelector(".pd-features"),
    price:    !!(document.querySelector(".pd-price-box") || document.querySelector(".pd-price-cta")),
    quality:  !!document.querySelector(".pd-quality-grid"),
    origin:   !!(document.querySelector(".pd-origin-box") || document.querySelector(".pd-origin-card")),
    spec:     !!document.querySelector(".pd-spec-table"),
    howto:    !!document.querySelector(".pd-howto-list"),
    as_box:   !!(document.querySelector(".pd-as-box") || document.querySelector(".pd-as-grid")),
    notice:   !!(document.querySelector(".pd-notice-box") || document.querySelector(".pd-notice-list")),
    delivery: !!(document.querySelector(".pd-delivery-box") || document.querySelector(".pd-delivery-grid")),
})
""")

print()
for k, v in checks.items():
    print(f"  S-{k:10}: {'OK ✓' if v else 'MISSING ✗'}")

total = sum(checks.values())
print(f"\n  전체 {total}/{len(checks)} 섹션 확인")
pw.stop()
