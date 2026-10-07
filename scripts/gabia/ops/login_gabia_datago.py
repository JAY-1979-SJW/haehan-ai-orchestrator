"""가비아 + 공공데이터포털 로그인."""

import base64
import json
import pickle
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import websocket

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

CREDS_FILE = "data/.tmp_creds.pkl"
GABIA_TAB = "1620EC5553AE2CFFD42553A8DFD4E915"
DATAGO_TAB = "80E0AA27D5754BA065732958CB7082A9"


def ws_cmd(tabs, tid, m, p=None, to=20):
    t = next(x for x in tabs if x["id"] == tid)
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=to)
    mid = uuid.uuid4().int & 0xFFFFFF
    ws.send(json.dumps({"id": mid, "method": m, "params": p or {}}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == mid:
            ws.close()
            return r


def fill(tabs, tid, sel, val):
    js = (
        "(function(){"
        f"var inp=document.querySelector({json.dumps(sel)});"
        "if(!inp)return;"
        f"Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(inp,{json.dumps(val)});"
        "inp.dispatchEvent(new Event('input',{bubbles:true}));"
        "inp.dispatchEvent(new Event('change',{bubbles:true}));"
        "})()"
    )
    ws_cmd(tabs, tid, "Runtime.evaluate", {"expression": js})


def save(tabs, tid, domains, fname):
    r = ws_cmd(tabs, tid, "Network.getAllCookies", to=15)
    filtered = [c for c in r["result"]["cookies"] if any(d in c["domain"] for d in domains)]
    out = {
        "host": domains[0],
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cookie_count": len(filtered),
        "cookies": filtered,
    }
    with Path(fname).open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return len(filtered)


def cap_screenshot(tabs, tid, fname):
    r = ws_cmd(
        tabs,
        tid,
        "Runtime.evaluate",
        {
            "expression": (
                "(function(){"
                "var img=document.querySelector('.LBD_CaptchaImage,img[id*=captcha],img[src*=captcha],#captchaImg');"
                "if(!img)return null;"
                "var r2=img.getBoundingClientRect();"
                "return JSON.stringify({x:Math.round(r2.x),y:Math.round(r2.y),w:Math.round(r2.width),h:Math.round(r2.height)});"
                "})()"
            )
        },
    )
    val = r["result"]["result"]["value"]
    if not val or val == "null":
        return None
    cap = json.loads(val)
    r2 = ws_cmd(
        tabs,
        tid,
        "Page.captureScreenshot",
        {
            "format": "jpeg",
            "quality": 99,
            "clip": {
                "x": cap["x"] - 5,
                "y": cap["y"] - 5,
                "width": cap["w"] + 10,
                "height": cap["h"] + 10,
                "scale": 3.5,
            },
        },
    )
    img = base64.b64decode(r2["result"]["data"])
    with Path(fname).open("wb") as f:
        f.write(img)
    return fname


def main(gabia_captcha: str, datago_captcha: str = ""):
    with Path(CREDS_FILE).open("rb") as f:
        creds = pickle.load(f)

    tabs = json.loads(urllib.request.urlopen("http://localhost:9222/json").read())

    # ─── GABIA ───
    print(f"[가비아] captcha={gabia_captcha}")
    fill(tabs, GABIA_TAB, "input[placeholder*=아이디]", "haehan-ai")
    fill(tabs, GABIA_TAB, "input[type=password]", creds["gabia"]["password"])
    fill(tabs, GABIA_TAB, "input[type=number]", gabia_captcha)
    ws_cmd(
        tabs,
        GABIA_TAB,
        "Runtime.evaluate",
        {
            "expression": (
                "[...document.querySelectorAll('button')]"
                ".find(b=>b.textContent.includes('로그인')&&!b.disabled)?.click()"
            )
        },
    )
    print("  제출 완료")

    # ─── DATAGO ───
    print("[데이터포털] 로그인...")
    ws_cmd(tabs, DATAGO_TAB, "Page.navigate", {"url": "https://www.data.go.kr/uim/login/loginView.do"})
    time.sleep(5)
    r = ws_cmd(tabs, DATAGO_TAB, "Runtime.evaluate", {"expression": "location.href"})
    auth_url = r["result"]["result"]["value"]
    print("  URL:", auth_url[:80])

    fill(tabs, DATAGO_TAB, "#inputUsername,input[name=username]", "skyjwshin")
    fill(tabs, DATAGO_TAB, "#inputPassword,input[name=password]", creds["datago"]["password"])

    if datago_captcha:
        fill(tabs, DATAGO_TAB, "#captcha,input[name=captcha]", datago_captcha)
        ws_cmd(
            tabs,
            DATAGO_TAB,
            "Runtime.evaluate",
            {
                "expression": (
                    "[...document.querySelectorAll('button,input[type=submit]')]"
                    ".find(b=>(b.textContent||b.value||'').includes('로그인'))?.click()"
                )
            },
        )
        print("  제출 완료")
    else:
        fname = cap_screenshot(tabs, DATAGO_TAB, "data/datago_cap.jpg")
        if fname:
            print(f"  캡차 저장: {fname} — 캡차값 인자로 재실행 필요")
        else:
            ws_cmd(
                tabs,
                DATAGO_TAB,
                "Runtime.evaluate",
                {
                    "expression": (
                        "[...document.querySelectorAll('button,input[type=submit]')]"
                        ".find(b=>(b.textContent||b.value||'').includes('로그인'))?.click()"
                    )
                },
            )
            print("  캡차 없이 제출")

    # ─── 결과 확인 ───
    time.sleep(8)

    url_g = ws_cmd(tabs, GABIA_TAB, "Runtime.evaluate", {"expression": "location.href"}, to=15)["result"]["result"][
        "value"
    ]
    print("가비아 URL:", url_g[:80])
    if "accounts.gabia.com" not in url_g:
        n = save(tabs, GABIA_TAB, ["gabia.com"], "data/sessions/gabia.com.json")
        print(f"✓ 가비아 ({n} cookies)")
    else:
        fname = cap_screenshot(tabs, GABIA_TAB, "data/gabia_cap_next.jpg")
        print(f"✗ 가비아 실패 — 새 캡차: {fname}")

    if datago_captcha:
        url_d = ws_cmd(tabs, DATAGO_TAB, "Runtime.evaluate", {"expression": "location.href"}, to=15)["result"][
            "result"
        ]["value"]
        print("데이터포털 URL:", url_d[:80])
        if "login" not in url_d.lower() and "auth.data.go.kr" not in url_d:
            n = save(tabs, DATAGO_TAB, ["data.go.kr"], "data/sessions/data.go.kr.json")
            print(f"✓ 데이터포털 ({n} cookies)")
        else:
            fname = cap_screenshot(tabs, DATAGO_TAB, "data/datago_cap_next.jpg")
            print(f"✗ 데이터포털 실패 — 새 캡차: {fname}")


if __name__ == "__main__":
    gc = sys.argv[1] if len(sys.argv) > 1 else ""
    dc = sys.argv[2] if len(sys.argv) > 2 else ""
    main(gc, dc)
