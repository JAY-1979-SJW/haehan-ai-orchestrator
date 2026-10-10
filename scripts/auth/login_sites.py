"""4개 사이트(가비아/하이웍스/공공데이터포털/카카오) 자동 로그인."""

import json
import pickle
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import websocket

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

CREDS_FILE = "data/.tmp_creds.pkl"


def make_cmd(tabs, tab_id, timeout=25):
    t = next(x for x in tabs if x["id"] == tab_id)
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=timeout)

    def cmd(m, p=None):
        mid = uuid.uuid4().int & 0xFFFFFF
        ws.send(json.dumps({"id": mid, "method": m, "params": p or {}}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == mid:
                return r

    return ws, cmd


def fill(cmd, sel, val):
    cmd(
        "Runtime.evaluate",
        {
            "expression": f"""(function(){{
        var inp=document.querySelector({json.dumps(sel)});
        if(!inp)return;
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,"value").set.call(inp,{json.dumps(val)});
        inp.dispatchEvent(new Event("input",{{bubbles:true}}));
        inp.dispatchEvent(new Event("change",{{bubbles:true}}));
    }})()"""
        },
    )


def click_submit(cmd):
    return cmd(
        "Runtime.evaluate",
        {
            "expression": """(function(){
        var btn=[...document.querySelectorAll("button,input[type=submit]")].find(
            b=>(b.textContent||b.value||"").trim().includes("로그인")&&!b.disabled);
        if(btn){btn.click();return"clicked:"+btn.tagName+"/"+b.textContent.trim().substring(0,10);}
        return"no btn";
    })()"""
        },
    )


def save_cookies(tabs, tab_id, domains, filename):
    t = next(x for x in tabs if x["id"] == tab_id)
    ws2 = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=15)
    mid = uuid.uuid4().int & 0xFFFFFF
    ws2.send(json.dumps({"id": mid, "method": "Network.getAllCookies", "params": {}}))
    while True:
        resp = json.loads(ws2.recv())
        if resp.get("id") == mid:
            all_c = resp["result"]["cookies"]
            ws2.close()
            break
    filtered = [c for c in all_c if any(d in c["domain"] for d in domains)]
    out = {
        "host": domains[0],
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cookie_count": len(filtered),
        "cookies": filtered,
    }
    with Path(filename).open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return len(filtered)


def _login_gabia(tabs, creds, captcha_gabia):
    # ─── 1. GABIA ───
    print("[1/3] 가비아 로그인...")
    GABIA_TAB = "7FD8F243350F337D0205AF2890AFF592"
    ws_g, cmd_g = make_cmd(tabs, GABIA_TAB, 30)
    fill(cmd_g, "input[placeholder*=아이디]", "haehan-ai")
    fill(cmd_g, "input[type=password]", creds["gabia"]["password"])
    fill(cmd_g, "input[type=number]", captcha_gabia)
    time.sleep(0.4)
    cmd_g(
        "Runtime.evaluate",
        {
            "expression": """(function(){
        var btn=[...document.querySelectorAll("button")].find(b=>b.textContent.trim().includes("로그인")&&!b.disabled);
        if(btn)btn.click();
    })()"""
        },
    )
    ws_g.settimeout(30)
    time.sleep(7)
    try:
        r = cmd_g("Runtime.evaluate", {"expression": "location.href"})
        url = r["result"]["result"]["value"]
        print("  URL:", url[:80])
        if "accounts.gabia.com" not in url:
            n = save_cookies(tabs, GABIA_TAB, ["gabia.com"], "data/sessions/gabia.com.json")
            print(f"  ✓ 가비아 성공 ({n} cookies)")
        else:
            r3 = cmd_g(
                "Runtime.evaluate",
                {
                    "expression": """(function(){
                var e=document.querySelector("[class*=error],[class*=Error],.msg,.alert");
                return e?e.textContent.trim().substring(0,100):"(에러 메시지 없음)";
            })()"""
                },
            )
            print("  ✗ 가비아 실패:", r3["result"]["result"].get("value", ""))
    except Exception as e:  # noqa: BLE001 - 여러 사이트(가비아/하이웍스/공공데이터포털) 로그인 상태 WebSocket 확인 스크립트(읽기전용) — 각 사이트 확인 실패는 print로 오류만 출력하고 다음 사이트로 계속, 로그인 상태를 바꾸지 않음
        print("  !", e)
    ws_g.close()


def _login_hiworks(tabs, creds):
    # ─── 2. HIWORKS ───
    print("[2/3] 하이웍스 로그인...")
    HW_TAB = "C07DF661DE1912E6B21398F8F711C09A"
    ws_h, cmd_h = make_cmd(tabs, HW_TAB)
    cur_url = cmd_h("Runtime.evaluate", {"expression": "location.href"})["result"]["result"]["value"]
    print("  현재 URL:", cur_url[:70])

    fill(
        cmd_h,
        "input[type=email],input#user_id,input[name=user_id],input[placeholder*=이메일],input[placeholder*=아이디]",
        "jay@haehan-ai.kr",
    )
    fill(cmd_h, "input[type=password]", creds["hiworks"]["password"])
    time.sleep(0.3)
    r_btn = click_submit(cmd_h)
    print("  Submit:", r_btn["result"]["result"].get("value", ""))
    ws_h.settimeout(30)
    time.sleep(7)
    try:
        r2 = cmd_h("Runtime.evaluate", {"expression": "location.href"})
        url_h = r2["result"]["result"]["value"]
        print("  URL after:", url_h[:80])
        if "login" not in url_h.lower():
            n = save_cookies(tabs, HW_TAB, ["hiworks.com", "office.hiworks.com"], "data/sessions/hiworks.com.json")
            print(f"  ✓ 하이웍스 성공 ({n} cookies)")
        else:
            print("  ✗ 하이웍스 실패")
    except Exception as e:  # noqa: BLE001 - 여러 사이트(가비아/하이웍스/공공데이터포털) 로그인 상태 WebSocket 확인 스크립트(읽기전용) — 각 사이트 확인 실패는 print로 오류만 출력하고 다음 사이트로 계속, 로그인 상태를 바꾸지 않음
        print("  !", e)
    ws_h.close()


def _login_datago(tabs, creds):
    # ─── 3. DATA.GO.KR ───
    print("[3/3] 공공데이터포털 로그인...")
    DATAGO_TAB = "80E0AA27D5754BA065732958CB7082A9"
    ws_d, cmd_d = make_cmd(tabs, DATAGO_TAB)
    cmd_d("Page.navigate", {"url": "https://www.data.go.kr/uim/lo/loginUserView.do"})
    time.sleep(4)

    r_inp = cmd_d(
        "Runtime.evaluate",
        {
            "expression": """(function(){
        return JSON.stringify([...document.querySelectorAll("input")].map(i=>({id:i.id,type:i.type,name:i.name,ph:i.placeholder})));
    })()"""
        },
    )
    print("  Inputs:", r_inp["result"]["result"]["value"][:200])

    fill(cmd_d, "input#username,input[name=username],input[name=loginId],input[placeholder*=아이디]", "skyjwshin")
    fill(cmd_d, "input#password,input[name=password],input[type=password]", creds["datago"]["password"])
    time.sleep(0.3)
    r_btn2 = click_submit(cmd_d)
    print("  Submit:", r_btn2["result"]["result"].get("value", ""))
    ws_d.settimeout(30)
    time.sleep(7)
    try:
        r3 = cmd_d("Runtime.evaluate", {"expression": "location.href"})
        url_d = r3["result"]["result"]["value"]
        print("  URL after:", url_d[:80])
        if "login" not in url_d.lower():
            n = save_cookies(tabs, DATAGO_TAB, ["data.go.kr"], "data/sessions/data.go.kr.json")
            print(f"  ✓ 공공데이터포털 성공 ({n} cookies)")
        else:
            print("  ✗ 공공데이터포털 실패")
    except Exception as e:  # noqa: BLE001 - 여러 사이트(가비아/하이웍스/공공데이터포털) 로그인 상태 WebSocket 확인 스크립트(읽기전용) — 각 사이트 확인 실패는 print로 오류만 출력하고 다음 사이트로 계속, 로그인 상태를 바꾸지 않음
        print("  !", e)
    ws_d.close()


def main(captcha_gabia: str):
    with Path(CREDS_FILE).open("rb") as f:
        creds = pickle.load(f)

    tabs = json.loads(urllib.request.urlopen("http://localhost:9222/json").read())

    _login_gabia(tabs, creds, captcha_gabia)

    _login_hiworks(tabs, creds)

    _login_datago(tabs, creds)

    print("\n완료")


if __name__ == "__main__":
    captcha = sys.argv[1] if len(sys.argv) > 1 else "40519"
    main(captcha)
