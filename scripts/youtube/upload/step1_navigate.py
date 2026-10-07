"""STEP 1: YouTube Studio 이동 및 로그인 확인."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.browser.cdp.cdp_helper import CDP


def run() -> bool:
    cdp = CDP()
    try:
        cdp.navigate("https://studio.youtube.com", wait=4)
        url = cdp.js("location.href")
        title = cdp.js("document.title")
        cdp.shot("STEP1 YouTube Studio")
        print(f"  URL  : {url}")
        print(f"  Title: {title}")
        ok = "studio.youtube.com" in url
        print("  결과:", "✅ 성공" if ok else "❌ 실패 (로그인 필요)")
        return ok
    finally:
        cdp.close()


if __name__ == "__main__":
    run()
