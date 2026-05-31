"""YouTube Studio 업로드 — 단일 CDP 연결 유지, 단계별 실행."""
import sys, time, threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.cdp_helper import CDP

VIDEO = r"C:\work\04. risk-assessment-generator\frontend\promo\bumper_v.mp4"
TITLE = "bumper_v"
PRIVACY = "PUBLIC"  # PUBLIC / PRIVATE / UNLISTED

STEP = int(sys.argv[1]) if len(sys.argv) > 1 else 1

import atexit
cdp = CDP()
atexit.register(cdp.close)  # 어떤 종료 방식이든 반드시 연결 닫기
time.sleep(0.5)


# ── STEP 1 ────────────────────────────────────────────────────────────────────
def step1():
    print("=== STEP 1: YouTube Studio 이동 ===")
    url = cdp.js("location.href")
    if "studio.youtube.com" not in url:
        cdp.navigate("https://studio.youtube.com", wait=5)

    # 만들기 버튼이 활성화될 때까지 최대 10초 대기
    for i in range(20):
        btn = cdp.js('Array.from(document.querySelectorAll("button")).find(b=>b.getAttribute("aria-label")==="만들기") ? "found" : "not_found"')
        if btn == "found":
            print(f"  만들기 버튼 활성화 ({i*0.5:.1f}s)")
            break
        time.sleep(0.5)
    else:
        print("  ❌ 만들기 버튼 타임아웃")
        cdp.shot("STEP1")
        return False

    url = cdp.js("location.href")
    cdp.shot("STEP1")
    print(f"  URL: {url}")
    print("  결과: ✅ 성공")
    return True


# ── STEP 2 ────────────────────────────────────────────────────────────────────
def step2():
    print("=== STEP 2: 동영상 업로드 다이얼로그 열기 ===")
    r = cdp.js('Array.from(document.querySelectorAll("button")).find(b=>b.getAttribute("aria-label")==="만들기")?.click(); "ok"')
    print(f"  만들기: {r}")
    time.sleep(2)

    r = cdp.js('''(function(){
      var item = Array.from(document.querySelectorAll("tp-yt-paper-item"))
                   .find(i => i.innerText && i.innerText.trim().startsWith("동영상 업로드"));
      if(item){ item.click(); return "clicked"; }
      return "not_found:" + Array.from(document.querySelectorAll("tp-yt-paper-item"))
                                  .map(i=>i.innerText?.trim().slice(0,20)).join("|");
    })()''')
    print(f"  동영상 업로드: {r}")
    time.sleep(3)
    cdp.shot("STEP2")

    ok = r == "clicked"
    print("  결과:", "✅ 성공" if ok else "❌ 실패")
    return ok


# ── STEP 3 ────────────────────────────────────────────────────────────────────
def step3():
    print("=== STEP 3: 파일 주입 ===")

    # File Chooser 인터셉트 — 버튼 클릭 전에 등록
    chooser_event = threading.Event()
    chooser_data  = {}

    def on_chooser(params):
        chooser_data.update(params)
        chooser_event.set()

    cdp.on("Page.fileChooserOpened", on_chooser)
    cdp.send("Page.setInterceptFileChooser", {"enabled": True})
    print("  인터셉트 활성화")

    # 파일 선택 버튼 클릭
    r = cdp.js('''(function(){
      var btn = document.querySelector("#select-files-button") ||
                Array.from(document.querySelectorAll("ytcp-button,button"))
                     .find(b => b.innerText && b.innerText.trim() === "파일 선택");
      if(btn){ btn.click(); return "clicked:" + (btn.id || btn.innerText?.trim()); }
      return "not_found";
    })()''')
    print(f"  파일 선택 버튼: {r}")

    got = chooser_event.wait(10)
    cdp.off("Page.fileChooserOpened")
    print(f"  fileChooserOpened: {'✅ 수신' if got else '❌ 타임아웃'}")

    if not got:
        cdp.shot("STEP3_fail")
        return False

    backend_node_id = chooser_data.get("backendNodeId", 0)
    print(f"  backendNodeId: {backend_node_id}")
    if not backend_node_id:
        return False

    r2 = cdp.send("DOM.setFileInputFiles", {"files": [VIDEO], "backendNodeId": backend_node_id})
    print(f"  setFileInputFiles: {r2.get('result', r2.get('error', r2))}")
    time.sleep(6)
    cdp.shot("STEP3")

    prog = cdp.js('document.querySelector("ytcp-video-upload-progress")?.innerText?.trim().slice(0,80) || "없음"')
    print(f"  진행 상태: {prog}")
    ok = "error" not in str(r2).lower()
    print("  결과:", "✅ 성공" if ok else "❌ 실패")
    return ok


# ── STEP 4 ────────────────────────────────────────────────────────────────────
def step4():
    print("=== STEP 4: 제목 입력 ===")
    cdp.shot("STEP4_before")

    r = cdp.js(f'''(function(){{
      var tb = document.querySelectorAll("#textbox")[0];
      if(!tb) return "not_found";
      tb.focus();
      document.execCommand("selectAll", false, null);
      document.execCommand("insertText", false, "{TITLE}");
      return "ok:" + tb.textContent?.trim().slice(0,30);
    }})()''')
    print(f"  제목: {r}")
    time.sleep(1)
    cdp.shot("STEP4")
    ok = r.startswith("ok:")
    print("  결과:", "✅ 성공" if ok else "❌ 실패")
    return ok


# ── STEP 5 ────────────────────────────────────────────────────────────────────
def step5():
    print("=== STEP 5: 공개 설정 → 게시 ===")
    for i in range(3):
        r = cdp.js('document.querySelector("#next-button")?.click(); "ok"')
        print(f"  다음 {i+1}: {r}")
        time.sleep(2)

    cdp.shot("STEP5_visibility")

    r = cdp.js(f'''(function(){{
      var rb = Array.from(document.querySelectorAll("tp-yt-paper-radio-button"))
                    .find(b => b.getAttribute("name") === "{PRIVACY}");
      if(rb){{ rb.click(); return "set:{PRIVACY}"; }}
      return "not_found";
    }})()''')
    print(f"  공개 설정: {r}")
    time.sleep(1)
    cdp.shot("STEP5_before_publish")

    r = cdp.js('document.querySelector("#done-button")?.click(); "ok"')
    print(f"  게시: {r}")
    time.sleep(6)
    cdp.shot("STEP5_done")
    print(f"  URL: {cdp.js('location.href')}")
    print("  결과: ✅ 완료")
    return True


# ── 실행 ─────────────────────────────────────────────────────────────────────
steps = {1: step1, 2: step2, 3: step3, 4: step4, 5: step5}

try:
    for n in range(1, STEP + 1):
        ok = steps[n]()
        if not ok:
            print(f"\n❌ STEP {n} 실패 — 중단")
            break
        if n < STEP:
            time.sleep(1)
finally:
    cdp.close()
