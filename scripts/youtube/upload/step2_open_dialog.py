"""STEP 2: 만들기 → 동영상 업로드 다이얼로그 열기."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.browser.cdp.cdp_helper import CDP


def run() -> bool:
    cdp = CDP()
    try:
        # 현재 URL 확인 후 필요시 이동
        url = cdp.js("location.href")
        print(f"  현재 URL: {url}")
        if "studio.youtube.com" not in url:
            print("  → YouTube Studio로 이동")
            cdp.navigate("https://studio.youtube.com", wait=4)

        cdp.shot("STEP2 시작")

        # 만들기 버튼 클릭
        r = cdp.js('''(function(){
          var btn = Array.from(document.querySelectorAll("button"))
                        .find(b => b.getAttribute("aria-label")==="만들기");
          if(btn){ btn.click(); return "clicked"; }
          return "not_found";
        })()''')
        print(f"  만들기 클릭: {r}")
        time.sleep(2)
        cdp.shot("STEP2 만들기 후")

        # 동영상 업로드 메뉴 클릭
        r = cdp.js('''(function(){
          var items = Array.from(document.querySelectorAll("tp-yt-paper-item"));
          console.log("items count:", items.length, items.map(i=>i.innerText?.trim().slice(0,20)).join("|"));
          var item = items.find(i => i.innerText && i.innerText.trim().startsWith("동영상 업로드"));
          if(item){ item.click(); return "clicked"; }
          return "not_found:" + items.map(i=>i.innerText?.trim().slice(0,20)).join("|");
        })()''')
        print(f"  동영상 업로드: {r}")
        time.sleep(3)

        cdp.shot("STEP2 업로드 다이얼로그")

        # 다이얼로그 확인
        dialog = cdp.js('document.querySelector("ytcp-uploads-dialog,ytcp-video-upload-dialog") ? "found" : "not_found"')
        print(f"  다이얼로그: {dialog}")

        ok = r == "clicked"
        print("  결과:", "✅ 성공" if ok else "❌ 실패")
        return ok
    finally:
        cdp.close()

if __name__ == "__main__":
    run()
