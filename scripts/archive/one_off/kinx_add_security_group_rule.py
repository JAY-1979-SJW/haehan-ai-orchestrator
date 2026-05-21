"""KINX IXcloud 콘솔 - 보안그룹 인바운드 규칙 추가 (1회성 스크립트)

작업: haehan-ai 프로젝트 default 보안그룹에 TCP 22 / 220.85.59.196/32 추가
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import websockets

CDP_PORT = 9222
TARGET_URL = "https://console.ixcloud.net/login"
LOGIN_ID = "skyjwshin@kakao.com"
LOGIN_PW = "[삭제됨]"
SSH_IP = "220.85.59.196/32"


async def get_ws_url(port: int = 9222) -> str:
    import urllib.request
    resp = urllib.request.urlopen(f"http://localhost:{port}/json", timeout=5)
    tabs = json.loads(resp.read())
    for tab in tabs:
        if tab.get("type") == "page":
            return tab["webSocketDebuggerUrl"]
    raise RuntimeError("사용 가능한 page 탭이 없습니다")


class CDP:
    def __init__(self, ws):
        self._ws = ws
        self._mid = 0

    async def send(self, method: str, params: dict | None = None):
        self._mid += 1
        m = self._mid
        await self._ws.send(json.dumps({"id": m, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=20))
            if msg.get("id") == m:
                return msg.get("result", {})

    async def js(self, expr: str):
        res = await self.send("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": True,
        })
        return res.get("result", {}).get("value")

    async def navigate(self, url: str, wait: float = 4.0):
        await self.send("Page.navigate", {"url": url})
        await asyncio.sleep(wait)

    async def focus_selector(self, selector: str):
        """JS로 포커스"""
        escaped = selector.replace('"', '\\"')
        return await self.js(f'''
(function() {{
  const el = document.querySelector("{escaped}");
  if (!el) return false;
  el.focus();
  return true;
}})()
''')

    async def react_fill(self, selector: str, value: str):
        """React input에 값 설정 (nativeInputValueSetter)"""
        escaped = selector.replace('"', '\\"')
        safe_val = value.replace("\\", "\\\\").replace('"', '\\"')
        return await self.js(f'''
(function() {{
  const el = document.querySelector("{escaped}");
  if (!el) return false;
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(el, "{safe_val}");
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return true;
}})()
''')

    async def insert_text_to(self, selector: str, value: str):
        """포커스 후 Input.insertText 사용"""
        ok = await self.focus_selector(selector)
        if not ok:
            return False
        await asyncio.sleep(0.2)
        # 기존 값 지우기
        await self.js(f'''
(function() {{
  const el = document.querySelector("{selector.replace('"', '\\"')}");
  if (el) el.value = "";
}})()
''')
        await self.send("Input.insertText", {"text": value})
        return True

    async def click(self, selector: str):
        escaped = selector.replace('"', '\\"')
        return await self.js(f'''
(function() {{
  const el = document.querySelector("{escaped}");
  if (el) {{ el.click(); return el.textContent.trim() || true; }}
  return false;
}})()
''')

    async def url(self):
        return await self.js("window.location.href")

    async def title(self):
        return await self.js("document.title")

    async def text(self, limit=5000):
        return await self.js(f"document.body.innerText.substring(0, {limit})")

    async def html(self, limit=10000):
        return await self.js(f"document.body.innerHTML.substring(0, {limit})")

    async def snapshot(self, label: str):
        snap = {
            "label": label,
            "url": await self.url(),
            "title": await self.title(),
            "body_text": await self.text(),
            "body_html": await self.html(),
        }
        p = Path(f"data/kinx_snap_{label}.json")
        p.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [스냅샷] {p}")
        return snap


async def main():
    print("=" * 60)
    print("KINX IXcloud 보안그룹 규칙 추가 자동화")
    print("=" * 60)

    ws_url = await get_ws_url()
    print(f"\n탭 WS: {ws_url[:60]}...")

    async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
        cdp = CDP(ws)
        await cdp.send("Page.enable")
        await cdp.send("Runtime.enable")
        await cdp.send("DOM.enable")

        # ─── 1. 로그인 ───
        print(f"\n[1단계] 로그인 페이지 이동...")
        await cdp.navigate(TARGET_URL, wait=4)
        print(f"  URL: {await cdp.url()}")

        print("[2단계] 아이디/비밀번호 입력...")
        # 아이디: React fill
        id_ok = await cdp.react_fill("input#username", LOGIN_ID)
        print(f"  아이디 입력: {'성공' if id_ok else '실패'}")

        # 비밀번호: focus + insertText
        pw_ok = await cdp.insert_text_to("input[type=password]", LOGIN_PW)
        print(f"  비밀번호 입력: {'성공' if pw_ok else '실패'}")

        # 값 확인
        id_val = await cdp.js('document.querySelector("input#username").value')
        pw_val = await cdp.js('document.querySelector("input[type=password]").value')
        print(f"  확인 — ID: {id_val}, PW길이: {len(pw_val) if pw_val else 0}")

        print("[2단계] 로그인 버튼 클릭...")
        btn_res = await cdp.click("button[role='submit']")
        if not btn_res:
            btn_res = await cdp.click("button.button")
        print(f"  버튼 결과: {btn_res}")

        print("  로그인 대기(10초)...")
        await asyncio.sleep(10)

        cur = await cdp.url()
        print(f"  로그인 후 URL: {cur}")

        if "login" in (cur or "").lower():
            err = await cdp.js('''
Array.from(document.querySelectorAll(
  ".ant-message-notice-content, [class*='error'], [class*='Error'], .alert"
)).map(e => e.textContent.trim()).filter(t => t).join(" | ")
''')
            print(f"\n❌ 로그인 실패! 오류: {err}")
            await cdp.snapshot("login_failed")
            return

        print(f"\n✅ 로그인 성공!")

        # ─── 3. 보안그룹 메뉴 찾기 ───
        print("\n[3단계] 보안그룹 메뉴 탐색...")
        await cdp.snapshot("dashboard")

        # 네비게이션 메뉴에서 '네트워크' 혹은 '보안그룹' 링크 찾기
        menu_links = await cdp.js('''
Array.from(document.querySelectorAll("a[href]")).map(a => ({
  href: a.href,
  text: a.textContent.trim().substring(0, 40)
})).filter(l => l.text.length > 0).slice(0, 80)
''')
        print(f"  메뉴 링크({len(menu_links) if menu_links else 0}개):")
        if menu_links:
            for l in menu_links:
                print(f"    {l['text']} → {l['href']}")

        # 보안그룹 관련 URL 탐색
        sg_keywords = ["security", "보안그룹", "securitygroup", "security-group", "sg"]
        sg_link = None
        if menu_links:
            for l in menu_links:
                if any(k in l["href"].lower() or k in l["text"].lower() for k in sg_keywords):
                    sg_link = l["href"]
                    print(f"\n  보안그룹 링크 발견: {sg_link}")
                    break

        # 직접 URL 패턴 시도
        sg_urls_to_try = []
        if sg_link:
            sg_urls_to_try = [sg_link]
        # 현재 URL에서 기반 추출
        base_url = "/".join((cur or "https://console.ixcloud.net").split("/")[:3])
        sg_urls_to_try += [
            f"{base_url}/network/security-groups",
            f"{base_url}/project/security_groups/",
            f"{base_url}/network/securitygroups",
        ]

        sg_reached = False
        for sg_url in sg_urls_to_try:
            print(f"\n  시도: {sg_url}")
            await cdp.navigate(sg_url, wait=4)
            cur2 = await cdp.url()
            title2 = await cdp.title()
            body2 = await cdp.text(500)
            print(f"  → {cur2[:80]}")
            print(f"  텍스트: {body2[:200]}")
            if "login" not in (cur2 or "").lower() and any(
                kw in (body2 or "").lower() for kw in ["보안그룹", "security group", "default", "securitygroup"]
            ):
                sg_reached = True
                print(f"  ✓ 보안그룹 페이지 도달!")
                break

        if not sg_reached:
            print("\n⚠ 보안그룹 직접 URL 실패. 전체 메뉴 구조 탐색...")
            await cdp.snapshot("sg_not_found")
            # 사이드바/메뉴 링크 전체 출력
            all_links = await cdp.js('''
Array.from(document.querySelectorAll("a[href], .sidebar a, nav a, [class*='menu'] a")).map(a => ({
  href: a.href, text: a.textContent.trim()
})).filter(l => l.text && l.href.includes(location.hostname)).slice(0, 100)
''')
            print(f"  내부 링크:\n{json.dumps(all_links, ensure_ascii=False, indent=2)[:3000]}")
            return

        snap_sg = await cdp.snapshot("security_groups_page")
        print(f"\n  보안그룹 페이지 텍스트:\n{snap_sg['body_text'][:3000]}\n")

        # ─── 4. default 보안그룹 선택 ───
        print("\n[4단계] default 보안그룹 규칙 관리 버튼 클릭...")

        # 테이블에서 default 행 찾기
        manage_result = await cdp.js('''
(function() {
  // 테이블 행 탐색
  const rows = Array.from(document.querySelectorAll("tr, [class*='table-row'], [class*='TableRow']"));
  for (const row of rows) {
    const text = row.textContent;
    if (/\\bdefault\\b/i.test(text)) {
      // 규칙 관리/보기 버튼
      const btns = Array.from(row.querySelectorAll("a, button"));
      for (const b of btns) {
        const t = b.textContent.trim();
        if (/규칙|Rule|관리|Manage|Edit|수정/i.test(t)) {
          b.click();
          return "clicked:" + t;
        }
      }
      // 첫 번째 링크
      const firstLink = row.querySelector("a");
      if (firstLink) { firstLink.click(); return "link:" + firstLink.href; }
      return "row_found_no_action";
    }
  }
  return "default_not_found";
})()
''')
        print(f"  결과: {manage_result}")
        await asyncio.sleep(3)

        snap_default = await cdp.snapshot("default_sg_rules")
        print(f"  페이지:\n{snap_default['body_text'][:3000]}\n")

        # ─── 5. 인바운드 규칙 추가 ───
        print("\n[5단계] 인바운드 규칙 추가 버튼 찾기...")
        add_result = await cdp.js('''
(function() {
  const btns = Array.from(document.querySelectorAll("button, a"));
  for (const b of btns) {
    const t = b.textContent.trim();
    if (/규칙 추가|인바운드 추가|Add Rule|Add Inbound|추가/.test(t) && !b.disabled) {
      b.click();
      return "clicked:" + t;
    }
  }
  // 버튼 목록 반환
  return "not_found:" + btns.map(b => b.textContent.trim()).filter(t => t).slice(0, 20).join(" | ");
})()
''')
        print(f"  추가 버튼: {add_result}")
        await asyncio.sleep(2)

        snap_modal = await cdp.snapshot("add_rule_modal")
        print(f"  모달 텍스트:\n{snap_modal['body_text'][:2000]}\n")

        # ─── 6. 폼 입력 ───
        print("\n[6단계] 규칙 폼 입력...")

        # 모달 내 입력 필드 확인
        fields = await cdp.js('''
Array.from(document.querySelectorAll("input, select")).map(el => ({
  tag: el.tagName,
  type: el.type || "",
  id: el.id || "",
  name: el.name || "",
  placeholder: el.placeholder || "",
  className: el.className.substring(0, 50)
}))
''')
        print(f"  입력 필드들: {json.dumps(fields, ensure_ascii=False)[:1000]}")

        # 프로토콜 선택 (TCP)
        proto_res = await cdp.js('''
(function() {
  // ant-design select 처리
  const selects = Array.from(document.querySelectorAll("select"));
  for (const s of selects) {
    const opts = Array.from(s.options);
    const tcp = opts.find(o => /tcp/i.test(o.text) || o.value === "tcp" || o.value === "6");
    if (tcp) {
      s.value = tcp.value;
      s.dispatchEvent(new Event("change", {bubbles: true}));
      return "TCP selected via select: " + tcp.value;
    }
  }
  // ant-design select dropdown 처리 - 클릭으로 열기
  const antSelects = Array.from(document.querySelectorAll(".ant-select:not(.ant-select-disabled)"));
  if (antSelects.length > 0) {
    return "ant-select found: " + antSelects.length;
  }
  return "no select found";
})()
''')
        print(f"  프로토콜 선택: {proto_res}")

        # 포트 입력
        port_selectors = [
            "input[placeholder*='포트']",
            "input[placeholder*='Port']",
            "input[name*='port']",
            "input[id*='port']",
        ]
        port_ok = False
        for sel in port_selectors:
            res = await cdp.react_fill(sel, "22")
            if res:
                print(f"  포트 입력 성공: {sel}")
                port_ok = True
                break
        if not port_ok:
            print("  포트 필드 없음 — insertText 시도")
            # 두 번째 input에 입력 시도
            await cdp.js('''document.querySelectorAll("input")[1] && document.querySelectorAll("input")[1].focus()''')
            await asyncio.sleep(0.2)
            await cdp.send("Input.insertText", {"text": "22"})

        # IP/CIDR 입력
        ip_selectors = [
            "input[placeholder*='IP']",
            "input[placeholder*='CIDR']",
            "input[placeholder*='ip']",
            "input[name*='cidr']",
            "input[name*='ip']",
            "input[id*='cidr']",
        ]
        ip_ok = False
        for sel in ip_selectors:
            res = await cdp.react_fill(sel, SSH_IP)
            if res:
                print(f"  IP 입력 성공: {sel}")
                ip_ok = True
                break
        if not ip_ok:
            print("  IP 필드 없음 — 마지막 input insertText 시도")
            await cdp.js('''
const inputs = document.querySelectorAll("input");
if (inputs.length > 0) inputs[inputs.length-1].focus();
''')
            await asyncio.sleep(0.2)
            await cdp.send("Input.insertText", {"text": SSH_IP})

        await asyncio.sleep(1)
        snap_filled = await cdp.snapshot("form_filled")
        print(f"  폼 입력 후:\n{snap_filled['body_text'][:1500]}\n")

        # ─── 7. 저장 ───
        print("\n[7단계] 저장/확인 버튼 클릭...")
        save_res = await cdp.js('''
(function() {
  const btns = Array.from(document.querySelectorAll("button"));
  const priority = ["저장", "확인", "추가", "OK", "Add", "Save", "등록"];
  for (const label of priority) {
    const btn = btns.find(b => b.textContent.trim() === label && !b.disabled);
    if (btn) { btn.click(); return "clicked:" + label; }
  }
  // 모달 내 마지막 submit 버튼
  const modal = document.querySelector(".ant-modal-footer button:last-child, .modal-footer button:last-child");
  if (modal) { modal.click(); return "modal_footer:" + modal.textContent.trim(); }
  return "no_save_btn:" + btns.map(b => b.textContent.trim()).filter(t => t).join("|");
})()
''')
        print(f"  저장 결과: {save_res}")
        await asyncio.sleep(5)

        snap_final = await cdp.snapshot("final_result")
        print(f"\n[최종 결과]\n{snap_final['body_text'][:4000]}\n")
        print(f"최종 URL: {snap_final['url']}")

        # 성공 판정
        ft = snap_final["body_text"] or ""
        if "220.85.59.196" in ft or SSH_IP in ft:
            print(f"\n✅ 성공! {SSH_IP} 규칙이 보안그룹에 추가되었습니다.")
            status = "success"
        elif any(kw in ft for kw in ["오류", "실패", "error", "Error", "failed"]):
            print(f"\n❌ 오류 발생. 스냅샷: data/kinx_snap_final_result.json")
            status = "error"
        else:
            print(f"\n⚠ 결과 불확실. 스냅샷 확인 필요: data/kinx_snap_final_result.json")
            status = "uncertain"

        result = {
            "status": status,
            "ip": SSH_IP,
            "port": 22,
            "protocol": "TCP",
            "security_group": "default",
            "final_url": snap_final["url"],
            "snapshots": sorted(str(p) for p in Path("data").glob("kinx_snap_*.json")),
        }
        Path("data/kinx_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n결과 저장: data/kinx_result.json")


if __name__ == "__main__":
    asyncio.run(main())
