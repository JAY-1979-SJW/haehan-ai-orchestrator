"""CDP 브라우저 원격 콘솔 — CLI + Python API 겸용.

━━━ CLI 사용 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    python scripts/browser/cdp/cdp_console.py                      # 대화형 REPL
    python scripts/browser/cdp/cdp_console.py eval "JS표현식"      # 단발 JS 실행
    python scripts/browser/cdp/cdp_console.py tabs                 # 탭 목록
    python scripts/browser/cdp/cdp_console.py info                 # 뷰포트·DPR
    python scripts/browser/cdp/cdp_console.py goto <url>           # URL 이동
    python scripts/browser/cdp/cdp_console.py screenshot [파일]    # 스크린샷
    python scripts/browser/cdp/cdp_console.py page-summary         # 페이지 구조 요약
    python scripts/browser/cdp/cdp_console.py find <텍스트>        # 텍스트로 요소 탐색
    python scripts/browser/cdp/cdp_console.py inspect <셀렉터>     # 요소 상세
    python scripts/browser/cdp/cdp_console.py count <셀렉터>       # 매칭 수
    python scripts/browser/cdp/cdp_console.py html <셀렉터>        # outerHTML
    python scripts/browser/cdp/cdp_console.py attrs <셀렉터>       # 속성 목록
    python scripts/browser/cdp/cdp_console.py table [셀렉터]       # 테이블 추출
    python scripts/browser/cdp/cdp_console.py form                 # 폼 필드 목록
    python scripts/browser/cdp/cdp_console.py links [필터]         # 링크 목록
    python scripts/browser/cdp/cdp_console.py suggest <텍스트>     # 셀렉터 추천
    python scripts/browser/cdp/cdp_console.py xhr-watch [초]       # XHR 감지

━━━ Python API 사용 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    from scripts.browser.cdp.cdp_console import connect

    with connect() as s:
        summary = s.page_summary()
        rows    = s.extract_table("table")
        elems   = s.find_elements("뉴스")
        fields  = s.get_form_fields()
        links   = s.get_links()
        html    = s.get_html("div.content")
        count   = s.count("li.item")
        s.goto("https://...")
        s.wait(1.5)

    # 특정 URL 탭에 연결
    with connect(url_contains="naver.com") as s:
        ...

    # Playwright Page와 함께 — 같은 탭을 두 가지 방식으로 제어
    from scripts.browser.cdp.connection import get_page
    from scripts.browser.cdp.cdp_console import connect_to_page

    page = get_page()
    page.goto("https://...")
    with connect_to_page(page) as s:
        data = s.extract_table()
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import requests
import websocket

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.common.config import CDP_HOST, CDP_PORT  # noqa: E402

# ── 탭 조회 ───────────────────────────────────────────────────────────────────


def get_tabs() -> list[dict]:
    try:
        return requests.get(f"http://{CDP_HOST}:{CDP_PORT}/json", timeout=5).json()
    except Exception as e:
        raise RuntimeError(f"CDP 서버 연결 실패: {e}") from e


def _find_tab(url_contains: str = "") -> dict:
    for t in get_tabs():
        if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
            if not url_contains or url_contains in (t.get("url") or ""):
                return t
    raise RuntimeError(f"탭을 찾을 수 없습니다 (url_contains={url_contains!r})")


# ── CDPSession ────────────────────────────────────────────────────────────────


class CDPSession:
    """CDP WebSocket 세션 — CLI·API 공용.

    with connect() as s:
        rows = s.extract_table("table")
    """

    def __init__(self, ws_url: str, timeout: float = 15):
        # suppress_origin: Chrome 148+ 는 Origin 헤더가 있는 DevTools WS 업그레이드를
        # 403 Forbidden 으로 거부한다(DNS rebinding 보호). Origin 을 제거해야 연결됨.
        self._ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        self._msg_id = 0

    # ── 저수준 CDP ────────────────────────────────────────────────────────────

    def cdp(self, method: str, params: dict | None = None) -> dict:
        self._msg_id += 1
        self._ws.send(json.dumps({"id": self._msg_id, "method": method, "params": params or {}}))
        while True:
            resp = json.loads(self._ws.recv())
            if resp.get("id") == self._msg_id:
                return resp

    def js(self, expression: str, timeout_ms: int = 8000) -> tuple[str, bool]:
        """JS 실행 → (결과문자열, 에러여부)."""
        resp = self.cdp(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "timeout": timeout_ms,
            },
        )
        if "error" in resp:
            return str(resp["error"]), True
        res = resp.get("result", {}).get("result", {})
        exc = resp.get("result", {}).get("exceptionDetails")
        if exc:
            return exc.get("exception", {}).get("description", str(exc)), True
        val = res.get("value")
        rtype = res.get("type", "")
        if val is None and rtype == "undefined":
            return "undefined", False
        if rtype == "object" and val is None:
            return res.get("description", "object"), False
        return (json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val), False

    def js_json(self, expression: str) -> tuple[Any, bool]:
        """JS → Python 객체. 반환값을 JSON.stringify로 감싸서 파싱."""
        raw, err = self.js(f"JSON.stringify({expression})")
        if err:
            return raw, True
        try:
            return json.loads(raw), False
        except Exception:  # noqa: BLE001 - CDP 콘솔 CLI 도구 -- JSON 파싱 실패 시 원문 텍스트 반환, 네트워크 요청 목록 출력 중 개별 오류는 무시(출력용 도구)
            return raw, True

    # ── 네비게이션 ────────────────────────────────────────────────────────────

    def goto(self, url: str, wait_idle: bool = True) -> str:
        """URL 이동. 완료 후 현재 URL 반환."""
        self.cdp("Page.navigate", {"url": url})
        if wait_idle:
            self.wait(1.5)
        val, _ = self.js("location.href")
        return val

    def wait(self, sec: float) -> None:
        time.sleep(sec)

    def reload(self) -> None:
        self.cdp("Page.reload")
        self.wait(1.5)

    @property
    def url(self) -> str:
        val, _ = self.js("location.href")
        return val

    @property
    def title(self) -> str:
        val, _ = self.js("document.title")
        return val

    # ── 스크래핑 API ─────────────────────────────────────────────────────────

    def page_summary(self) -> dict:
        """페이지 전체 구조 요약 — 테이블/폼/버튼/셀렉트 목록 반환."""
        data, err = self.js_json("""(function() {
            var tables = Array.from(document.querySelectorAll('table')).map(function(t,i){
                var rows=t.querySelectorAll('tr');
                var hdrs=Array.from(rows[0]?.querySelectorAll('th,td')||[]).map(function(c){return c.innerText.trim().slice(0,20);});
                return {index:i,id:t.id,cls:t.className.slice(0,40),
                        rows:rows.length,cols:(rows[0]?.children.length||0),headers:hdrs.slice(0,8)};
            });
            var forms=Array.from(document.querySelectorAll('form')).map(function(f,i){
                var flds=Array.from(f.querySelectorAll('input,select,textarea')).map(function(el){
                    return{tag:el.tagName.toLowerCase(),type:el.type||'',name:el.name||'',
                           id:el.id||'',placeholder:(el.placeholder||'').slice(0,25)};
                });
                return{index:i,id:f.id,action:(f.action||'').slice(0,60),method:f.method,fields:flds};
            });
            var btns=Array.from(document.querySelectorAll('button,input[type=submit]')).slice(0,15).map(function(b){
                return{tag:b.tagName.toLowerCase(),text:(b.innerText||b.value||'').trim().slice(0,25),
                       id:b.id||'',cls:b.className.slice(0,30)};
            });
            var sels=Array.from(document.querySelectorAll('select')).map(function(s){
                return{id:s.id||'',name:s.name||'',
                       options:Array.from(s.options).map(function(o){return o.text.trim().slice(0,15);}).slice(0,8)};
            });
            return{url:location.href,title:document.title,
                   bodyLen:(document.body?.innerText?.length||0),
                   tables:tables,forms:forms,buttons:btns,selects:sels};
        })()""")
        return {} if err else data

    def find_elements(self, text: str, limit: int = 10) -> list[dict]:
        """텍스트로 요소 탐색 + 셀렉터 추천 목록 반환."""
        data, err = self.js_json(f"""(function(){{
            var text={json.dumps(text)}, results=[], all=document.querySelectorAll('*');
            for(var i=0;i<all.length;i++){{
                var el=all[i];
                var t=(el.innerText||el.textContent||el.value||el.placeholder||'').trim();
                if(t.includes(text)&&el.children.length===0){{
                    var sel=el.tagName.toLowerCase();
                    if(el.id) sel+='#'+el.id;
                    else if(el.className) sel+='.'+el.className.trim().split(/\\s+/).join('.');
                    results.push({{tag:el.tagName.toLowerCase(),id:el.id||'',
                        cls:el.className.slice(0,40),name:el.getAttribute('name')||'',
                        text:t.slice(0,60),sel:sel.slice(0,80),
                        visible:el.offsetParent!==null}});
                    if(results.length>={limit}) break;
                }}
            }}
            return results;
        }})()""")
        return [] if err else data

    def inspect_element(self, selector: str, limit: int = 5) -> list[dict]:
        """셀렉터로 요소 상세 정보 반환."""
        data, err = self.js_json(f"""Array.from(document.querySelectorAll({json.dumps(selector)}))
            .slice(0,{limit}).map(function(el){{
                var attrs={{}};
                for(var a of el.attributes) attrs[a.name]=a.value.slice(0,80);
                var box=el.getBoundingClientRect();
                return{{tag:el.tagName.toLowerCase(),
                    text:(el.innerText||el.value||'').trim().slice(0,120),
                    html:el.outerHTML.slice(0,200),attrs:attrs,
                    visible:el.offsetParent!==null,
                    bbox:{{x:Math.round(box.x),y:Math.round(box.y),
                           w:Math.round(box.width),h:Math.round(box.height)}}}};
            }})""")
        return [] if err else data

    def count(self, selector: str) -> int:
        """셀렉터 매칭 수 반환."""
        val, err = self.js(f"document.querySelectorAll({json.dumps(selector)}).length")
        return 0 if err else int(val)

    def get_html(self, selector: str) -> str:
        """첫 번째 매칭 요소의 outerHTML 반환."""
        val, _ = self.js(f"document.querySelector({json.dumps(selector)})?.outerHTML||''")
        return val

    def get_text(self, selector: str) -> str:
        """첫 번째 매칭 요소의 innerText 반환."""
        val, _ = self.js(f"(document.querySelector({json.dumps(selector)})?.innerText||'').trim()")
        return val

    def get_texts(self, selector: str) -> list[str]:
        """모든 매칭 요소의 innerText 목록 반환."""
        data, err = self.js_json(
            f"Array.from(document.querySelectorAll({json.dumps(selector)}))"
            f".map(function(el){{return el.innerText.trim();}})"
        )
        return [] if err else data

    def get_attr(self, selector: str, attr: str) -> str:
        """첫 번째 매칭 요소의 속성값 반환."""
        val, _ = self.js(f"document.querySelector({json.dumps(selector)})?.getAttribute({json.dumps(attr)})||''")
        return val

    def get_attrs(self, selector: str, attr: str) -> list[str]:
        """모든 매칭 요소의 속성값 목록 반환."""
        attr_js = json.dumps(attr)
        data, err = self.js_json(
            f"Array.from(document.querySelectorAll({json.dumps(selector)}))"
            f".map(function(el){{return el.getAttribute({attr_js})||'';}})"
        )
        return [] if err else data

    def get_attrs_map(self, selector: str) -> list[dict]:
        """첫 번째 매칭 요소의 전체 속성 dict 반환."""
        data, err = self.js_json(f"""(function(){{
            var el=document.querySelector({json.dumps(selector)});
            if(!el) return null;
            var a={{}};
            for(var attr of el.attributes) a[attr.name]=attr.value;
            return a;
        }})()""")
        return {} if (err or data is None) else data

    def extract_table(self, selector: str = "table", skip_header_rows: int = 0) -> list[list[str]]:
        """테이블 데이터를 2D 리스트로 추출."""
        data, err = self.js_json(f"""(function(){{
            var tbl=document.querySelector({json.dumps(selector)});
            if(!tbl) return null;
            return Array.from(tbl.querySelectorAll('tr')).map(function(row){{
                return Array.from(row.querySelectorAll('th,td')).map(function(c){{
                    return c.innerText.trim().replace(/\\s+/g,' ');
                }});
            }});
        }})()""")
        if err or data is None:
            return []
        return data[skip_header_rows:]

    def extract_list(self, row_selector: str, field_map: dict[str, str]) -> list[dict]:
        """반복 행에서 필드맵 기반으로 데이터 추출.

        Args:
            row_selector: 반복 행 셀렉터 (예: "ul.list > li")
            field_map: {"필드명": "자식셀렉터"} (예: {"제목": "h3", "링크": "a[href]"})

        Returns:
            [{"필드명": 값, ...}, ...]
        """
        field_js = json.dumps(field_map)
        data, err = self.js_json(f"""(function(){{
            var rows=Array.from(document.querySelectorAll({json.dumps(row_selector)}));
            var fields={field_js};
            return rows.map(function(row){{
                var obj={{}};
                for(var key in fields){{
                    var sel=fields[key];
                    var el=row.querySelector(sel);
                    if(!el){{ obj[key]=''; continue; }}
                    if(sel.includes('[href]')||sel==='a')
                        obj[key]=el.href||el.getAttribute('href')||'';
                    else if(el.tagName==='IMG')
                        obj[key]=el.src||el.getAttribute('src')||'';
                    else
                        obj[key]=(el.innerText||el.textContent||'').trim();
                }}
                return obj;
            }});
        }})()""")
        return [] if err else data

    def get_form_fields(self) -> list[dict]:
        """현재 페이지의 모든 폼 필드 정보 반환."""
        data, err = self.js_json("""Array.from(document.querySelectorAll(
            'input,select,textarea')).map(function(el){
            return{tag:el.tagName.toLowerCase(),type:el.type||'',name:el.name||'',
                   id:el.id||'',placeholder:(el.placeholder||'').slice(0,30),
                   value:(el.value||'').slice(0,30),visible:el.offsetParent!==null};
        })""")
        return [] if err else data

    def get_links(self, filter_text: str = "") -> list[dict]:
        """링크 목록 반환. filter_text가 있으면 href 또는 text에 포함된 것만."""
        data, err = self.js_json("""Array.from(document.querySelectorAll('a[href]')).map(function(a){
            return{text:a.innerText.trim().slice(0,50),href:a.href.slice(0,120),
                   id:a.id||'',visible:a.offsetParent!==null};
        })""")
        if err:
            return []
        if filter_text:
            return [d for d in data if filter_text in d["text"] or filter_text in d["href"]]
        return data

    def suggest_selectors(self, text: str) -> list[dict]:
        """텍스트 기반 셀렉터 자동 추천 목록 반환."""
        data, err = self.js_json(f"""(function(){{
            var text={json.dumps(text)}, results=[];
            var all=Array.from(document.querySelectorAll('button,a,label,td,th,span,div,p,h1,h2,h3,li'));
            for(var el of all){{
                var t=(el.innerText||'').trim();
                if(t===text||t.startsWith(text)){{
                    var s=el.tagName.toLowerCase();
                    if(el.id) s+='#'+el.id;
                    else if(el.className) s+='.'+el.className.trim().split(/\\s+/).join('.');
                    results.push({{type:'text',selector:s,sample:t.slice(0,30)}});
                    if(results.length>=5) break;
                }}
            }}
            for(var inp of document.querySelectorAll('input,textarea')){{
                if((inp.placeholder||'').includes(text))
                    results.push({{type:'placeholder',
                        selector:'input[placeholder*='+JSON.stringify(text)+']',
                        sample:inp.placeholder}});
            }}
            return results.slice(0,8);
        }})()""")
        return [] if err else data

    def screenshot(self, path: str | Path | None = None) -> Path:
        """스크린샷 저장 후 경로 반환."""
        import base64

        resp = self.cdp("Page.captureScreenshot", {"format": "png"})
        data = base64.b64decode(resp["result"]["data"])
        out = Path(path) if path else ROOT / "data" / f"shot_{int(time.time())}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return out

    def enable_xhr_capture(self) -> None:
        """XHR/fetch 요청 캡처 시작."""
        self.cdp("Network.enable")

    def close(self):
        self._ws.close()

    # ── context manager ───────────────────────────────────────────────────────
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ── 편의 연결 함수 ────────────────────────────────────────────────────────────


@contextmanager
def connect(url_contains: str = "", websocket_timeout: float = 15) -> Generator[CDPSession]:
    """CDP 세션 컨텍스트 매니저.

    with connect() as s:
        rows = s.extract_table()
    """
    tab = _find_tab(url_contains)
    s = CDPSession(tab["webSocketDebuggerUrl"], timeout=websocket_timeout)
    try:
        yield s
    finally:
        s.close()


@contextmanager
def connect_to_page(page) -> Generator[CDPSession]:
    """Playwright Page 객체와 같은 탭에 CDP로 연결.

    page = get_page()
    page.goto("https://...")
    with connect_to_page(page) as s:
        data = s.extract_table()
    """
    # Playwright가 연결 중인 탭의 URL로 탭 매칭
    url = page.url or ""
    host = url.split("/")[2] if url.startswith("http") else ""
    tab = _find_tab(host) if host else _find_tab()
    s = CDPSession(tab["webSocketDebuggerUrl"])
    try:
        yield s
    finally:
        s.close()


# ── CLI 출력 헬퍼 ─────────────────────────────────────────────────────────────


def _print_summary(data: dict) -> None:
    if not data:
        print("요약 데이터 없음")
        return
    print(f"\n{'=' * 60}")
    print(f"제목: {data.get('title', '')}")
    print(f"URL : {data.get('url', '')}")
    print(f"텍스트: {data.get('bodyLen', 0):,}자")
    for tbl in data.get("tables", []):
        print(f"\n  [테이블{tbl['index']}] id={tbl['id']!r} {tbl['rows']}행x{tbl['cols']}열")
        print(f"    헤더: {tbl['headers']}")
    for frm in data.get("forms", []):
        print(f"\n  [폼{frm['index']}] id={frm['id']!r} action={frm['action']!r}")
        for f in frm["fields"]:
            print(f"    {f['tag']}[{f['type']}] name={f['name']!r} id={f['id']!r} '{f['placeholder']}'")
    print(f"\n  [버튼] {len(data.get('buttons', []))}개")
    for b in data.get("buttons", []):
        print(f"    {b['tag']} {b['text']!r} id={b['id']!r}")
    print(f"{'=' * 60}\n")


# ── CLI 명령 ─────────────────────────────────────────────────────────────────


def _cli_tabs():
    tabs = [t for t in get_tabs() if t.get("type") == "page"]
    print(f"\n탭 {len(tabs)}개")
    print("─" * 70)
    for i, t in enumerate(tabs):
        print(f"  [{i + 1}] {(t.get('title') or '')[:45]}")
        print(f"       {(t.get('url') or '')[:70]}")
    print()


def _repl_summary(s, line):
    _print_summary(s.page_summary())


def _repl_form(s, line):
    for f in s.get_form_fields():
        print(" ", f)


def _repl_links(s, line):
    for l in s.get_links():  # noqa: E741
        print(f"  {l['text']!r:35s} {l['href']}")


def _repl_find(s, line):
    for e in s.find_elements(line[6:]):
        print(f"  {'✓' if e['visible'] else '○'} {e['sel']}  {e['text']!r}")


def _repl_table(s, line):
    sel = line[6:].strip() or "table"
    rows = s.extract_table(sel)
    for i, r in enumerate(rows[:20]):
        print(f"  {i:3d} | " + " | ".join(c[:18] for c in r[:8]))
    print(f"  총 {len(rows)}행")


def _repl_inspect(s, line):
    for e in s.inspect_element(line[9:]):
        print(f"  <{e['tag']}> {e['text']!r}  {e['attrs']}")


def _repl_count(s, line):
    print(f"  {s.count(line[7:])}개")


def _repl_suggest(s, line):
    for r in s.suggest_selectors(line[9:]):
        print(f"  [{r['type']}] {r['selector']}  {r['sample']!r}")


def _repl_goto(s, line):
    print(s.goto(line[6:]))


def _repl_shot(s, line):
    print(s.screenshot())


_REPL_EXACT = {".summary": _repl_summary, ".form": _repl_form, ".links": _repl_links, ".shot": _repl_shot}
# 접두사 명령 — 위에서부터 순서대로 검사
_REPL_PREFIX = (
    (".find ", _repl_find),
    (".table", _repl_table),
    (".inspect ", _repl_inspect),
    (".count ", _repl_count),
    (".suggest ", _repl_suggest),
    (".goto ", _repl_goto),
)


def _repl_dot_command(s, line: str) -> bool:
    """점(.)으로 시작하는 단축 명령 처리. 처리했으면 True."""
    handler = _REPL_EXACT.get(line)
    if handler is not None:
        handler(s, line)
        return True
    for prefix, handler in _REPL_PREFIX:
        if line.startswith(prefix):
            handler(s, line)
            return True
    return False


def _cli_repl():
    tab = _find_tab()
    print(f"\nCDP REPL  {tab.get('title', '')[:50]}  |  {tab.get('url', '')[:60]}")
    print("단축: .summary .form .links .find<텍스트> .table[셀렉터] .inspect<셀렉터>  |  exit\n")
    s = CDPSession(tab["webSocketDebuggerUrl"])
    try:
        while True:
            try:
                line = input(">>> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n종료")
                break
            if not line:
                continue
            if line.lower() in ("exit", "quit", "q"):
                break

            if _repl_dot_command(s, line):
                continue

            val, err = s.js(line)
            print(f"{'[오류] ' if err else '<< '}{val}")
    finally:
        s.close()


def _cmd_info(s, rest):
    data, _ = s.js_json("""{dpr:window.devicePixelRatio,
                    iw:window.innerWidth,ih:window.innerHeight,
                    url:location.href,title:document.title}""")
    print(f"\nURL: {data['url']}\nTitle: {data['title']}")
    print(f"DPR: {data['dpr']}  inner: {data['iw']}x{data['ih']}\n")


def _cmd_eval(s, rest):
    val, err = s.js(" ".join(rest))
    print(f"{'[오류] ' if err else ''}{val}")


def _cmd_find(s, rest):
    for e in s.find_elements(" ".join(rest)):
        print(f"  {'✓' if e['visible'] else '○'} {e['sel']:60s} {e['text']!r}")


def _cmd_inspect(s, rest):
    for e in s.inspect_element(" ".join(rest)):
        print(f"  <{e['tag']}> visible={e['visible']} bbox={e['bbox']}")
        print(f"    text: {e['text']!r}")
        print(f"    attrs: {e['attrs']}")


def _cmd_table(s, rest):
    rows = s.extract_table(rest[0] if rest else "table")
    for i, r in enumerate(rows[:25]):
        pfx = "HDR" if i == 0 else f"{i:3d}"
        print(f"  {pfx} | " + " | ".join(c[:18] for c in r[:8]))
    print(f"  총 {len(rows)}행")


def _cmd_form(s, rest):
    for f in s.get_form_fields():
        vis = "✓" if f["visible"] else "○"
        sel = f"#{f['id']}" if f["id"] else f"[name={f['name']!r}]" if f["name"] else ""
        print(f"  {vis} <{f['tag']}> {sel} type={f['type']!r} '{f['placeholder']}'")


def _cmd_links(s, rest):
    for l in s.get_links(rest[0] if rest else ""):  # noqa: E741
        vis = "✓" if l["visible"] else "○"
        print(f"  {vis} {l['text']!r:35s} {l['href']}")


def _cmd_suggest(s, rest):
    for r in s.suggest_selectors(" ".join(rest)):
        print(f"  [{r['type']}] {r['selector']}  {r['sample']!r}")


def _cmd_xhr_watch(s, rest):
    dur = int(rest[0]) if rest else 10
    s.enable_xhr_capture()
    print(f"XHR 감지 {dur}초...")
    end = time.time() + dur
    seen = set()
    while time.time() < end:
        try:
            s._ws.settimeout(0.3)
            evt = json.loads(s._ws.recv())
            if evt.get("method") == "Network.requestWillBeSent":
                req = evt["params"].get("request", {})
                url = req.get("url", "")
                if url not in seen:
                    seen.add(url)
                    print(f"  {req.get('method', ''):4s} {url[:100]}")
        except Exception:  # noqa: BLE001 - CDP 콘솔 CLI 도구 -- JSON 파싱 실패 시 원문 텍스트 반환, 네트워크 요청 목록 출력 중 개별 오류는 무시(출력용 도구)
            pass
    print(f"\n총 {len(seen)}개")


_CLI_COMMANDS = {
    "tabs": lambda s, rest: _cli_tabs(),
    "info": _cmd_info,
    "eval": _cmd_eval,
    "goto": lambda s, rest: print(s.goto(rest[0] if rest else "")),
    "screenshot": lambda s, rest: print(s.screenshot(rest[0] if rest else None)),
    "shot": lambda s, rest: print(s.screenshot(rest[0] if rest else None)),
    "page-summary": lambda s, rest: _print_summary(s.page_summary()),
    "summary": lambda s, rest: _print_summary(s.page_summary()),
    "find": _cmd_find,
    "inspect": _cmd_inspect,
    "count": lambda s, rest: print(f"{s.count(' '.join(rest))}개"),
    "html": lambda s, rest: print(s.get_html(" ".join(rest))),
    "attrs": lambda s, rest: print(s.get_attrs_map(" ".join(rest))),
    "table": _cmd_table,
    "form": _cmd_form,
    "links": _cmd_links,
    "suggest": _cmd_suggest,
    "xhr-watch": _cmd_xhr_watch,
}


def main():
    args = sys.argv[1:]
    if not args:
        _cli_repl()
        return

    cmd, rest = args[0].lower(), args[1:]

    with connect() as s:
        handler = _CLI_COMMANDS.get(cmd)
        if handler is None:
            print(__doc__)
        else:
            handler(s, rest)


if __name__ == "__main__":
    main()
