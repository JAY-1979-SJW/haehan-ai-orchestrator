"""STEP 5: 다음 × 3 → 공개 설정 → 게시."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.browser.cdp.cdp_helper import CDP


def run() -> bool:
    cdp = CDP()
    try:
        # 다음 버튼 3회
        for i in range(3):
            r = cdp.js('document.querySelector("#next-button")?.click(); "ok"')
            print(f"  다음 {i+1}: {r}")
            time.sleep(2)

        cdp.shot("STEP5 공개 설정 전")

        # 공개 설정
        r = cdp.js('''(function(){
          var pub = Array.from(document.querySelectorAll("tp-yt-paper-radio-button"))
                         .find(rb => rb.getAttribute("name")==="PUBLIC");
          if(pub){ pub.click(); return "public_set"; }
          // 드롭다운 방식
          var sel = document.querySelector("ytcp-video-visibility-select tp-yt-paper-radio-button[name=PUBLIC]");
          if(sel){ sel.click(); return "public_set_v2"; }
          return "not_found";
        })()''')
        print(f"  공개 설정: {r}")
        time.sleep(1)
        cdp.shot("STEP5 게시 전")

        # 게시 버튼
        r = cdp.js('document.querySelector("#done-button")?.click(); "ok"')
        print(f"  게시 클릭: {r}")
        time.sleep(5)
        cdp.shot("STEP5 완료")

        url = cdp.js("location.href")
        print(f"  최종 URL: {url}")
        print("  결과: ✅ 게시 완료")
        return True
    finally:
        cdp.close()

if __name__ == "__main__":
    run()
