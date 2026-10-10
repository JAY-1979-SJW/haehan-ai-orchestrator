"""STEP 4: 제목 입력 및 다음 버튼 클릭."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.browser.cdp.cdp_helper import CDP

TITLE = "bumper_v"

def run() -> bool:
    cdp = CDP()
    try:
        cdp.shot("STEP4 메타데이터 입력 전")

        # 제목 입력
        r = cdp.js(f'''(function(){{
          var tb = document.querySelectorAll("#textbox")[0];
          if(!tb) return "not_found";
          tb.focus();
          document.execCommand("selectAll", false, null);
          document.execCommand("insertText", false, "{TITLE}");
          return "ok:" + tb.textContent?.trim().slice(0,30);
        }})()''')
        print(f"  제목 입력: {r}")
        time.sleep(1)

        cdp.shot("STEP4 제목 입력 후")
        ok = r.startswith("ok:")
        print("  결과:", "✅ 성공" if ok else "❌ 실패")
        return ok
    finally:
        cdp.close()

if __name__ == "__main__":
    run()
