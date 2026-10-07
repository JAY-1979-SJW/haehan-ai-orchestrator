"""STEP 3: File Chooser 인터셉트로 파일 주입."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.browser.cdp.cdp_helper import CDP
from scripts.common.app_paths import resolve_external, sibling_project

VIDEO = str(
    resolve_external(
        "HAEHAN_PROMO_VIDEO", "frontend", "promo", "bumper_v.mp4", base=sibling_project("04. risk-assessment-generator")
    )
)


def _open_dialog(cdp: CDP):
    url = cdp.js("location.href")
    if "studio.youtube.com" not in url:
        cdp.navigate("https://studio.youtube.com", wait=4)
    cdp.js('Array.from(document.querySelectorAll("button")).find(b=>b.getAttribute("aria-label")==="만들기")?.click()')
    time.sleep(2)
    cdp.js('''(function(){
      var item = Array.from(document.querySelectorAll("tp-yt-paper-item"))
                   .find(i => i.innerText && i.innerText.trim().startsWith("동영상 업로드"));
      if(item) item.click();
    })()''')
    time.sleep(3)


def run() -> bool:
    cdp = CDP()
    try:
        # 다이얼로그 확인 및 재오픈
        dialog = cdp.js('document.querySelector("ytcp-uploads-dialog,ytcp-video-upload-dialog") ? "found" : "not_found"')
        print(f"  다이얼로그: {dialog}")
        if dialog != "found":
            print("  → 다이얼로그 재오픈")
            _open_dialog(cdp)
            cdp.shot("STEP3 다이얼로그")

        # File Chooser 인터셉트 등록 (버튼 클릭 전에!)
        chooser_event = threading.Event()
        chooser_data  = {}

        def on_file_chooser(params):
            chooser_data.update(params)
            chooser_event.set()

        cdp.on("Page.fileChooserOpened", on_file_chooser)
        cdp.send("Page.setInterceptFileChooser", {"enabled": True})
        print("  File chooser 인터셉트 활성화")

        # 파일 선택 버튼 클릭
        r = cdp.js('''(function(){
          var btn = document.querySelector("#select-files-button") ||
                    Array.from(document.querySelectorAll("ytcp-button,button"))
                         .find(b => b.innerText && b.innerText.trim() === "파일 선택");
          if(btn){ btn.click(); return "clicked:" + (btn.id || btn.innerText?.trim()); }
          return "not_found";
        })()''')
        print(f"  파일 선택 버튼: {r}")

        # fileChooserOpened 이벤트 대기
        got = chooser_event.wait(10)
        cdp.off("Page.fileChooserOpened")
        print(f"  fileChooserOpened: {'✅ 수신' if got else '❌ 타임아웃'}")
        print(f"  params: {chooser_data}")

        if got:
            backend_node_id = chooser_data.get("backendNodeId", 0)
            print(f"  backendNodeId: {backend_node_id}")
            if backend_node_id:
                r2 = cdp.send("DOM.setFileInputFiles", {
                    "files": [VIDEO],
                    "backendNodeId": backend_node_id
                })
                print(f"  setFileInputFiles: {r2.get('result', r2.get('error', r2))}")
                time.sleep(6)
                cdp.shot("STEP3 파일 주입 후")
                prog = cdp.js('document.querySelector("ytcp-video-upload-progress")?.innerText?.trim().slice(0,80) || "없음"')
                print(f"  진행 상태: {prog}")
                return True

        cdp.shot("STEP3 실패")
        return False

    finally:
        cdp.close()


if __name__ == "__main__":
    ok = run()
    print("결과:", "✅ 성공" if ok else "❌ 실패")
