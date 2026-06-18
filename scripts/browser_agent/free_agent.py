"""자율 도구호출 에이전트 — GPT가 도구를 자유롭게 골라 사용자 명령을 수행.

기존 통제 파이프라인(분류기·고정 URL표·경직 루프)을 대체. GPT가 Claude처럼
'관찰→판단→도구 호출→반복'으로 자유롭게 일한다. 현재 열린 페이지(사용자 수동 작업)를
먼저 읽어 그대로 이어받는다.

안전: 결제/구매/삭제/발송/제출 등 파괴적 동작은 차단(_is_destructive). 읽기·탐색·입력은 자유.
재사용: agent.py 의 _observe/_execute/_is_destructive/_wait_for_login/_show_cdp_window.
"""

from __future__ import annotations

import json
import os

from scripts.browser_agent import agent as _ag

_SYSTEM = (
    "당신은 사용자의 PC와 앱을 완전히 제어하는 자율 에이전트입니다. "
    "사용자 명령을 달성하기 위해 제공된 도구를 자유롭게 골라 사용하세요. 도구 선택·순서는 당신이 판단합니다.\n"
    "사용 가능한 도구:\n"
    "- web_search: 공개 웹 정보(뉴스·공모전·기업/기관 소식·일반 사실)를 검색 (브라우저 불필요)\n"
    "- read_page / navigate / click / type_text / scroll: 로그인된 CDP 브라우저 조작\n"
    "- call_local_api: 로컬 FastAPI 엔드포인트 직접 호출 (GET/POST, CDP 없어도 동작)\n"
    "- list_app_actions / run_app_action: 앱 내부 기능 검색 및 실행\n"
    "- smartstore_register_product / smartstore_list_products / smartstore_list_orders: 스마트스토어 전용\n"
    "- session_status: 외부 사이트 로그인 세션 확인\n"
    "■ 기능 재사용 원칙(필수): 사용자가 앱 기능(분석·조회·수집·등록·발송·현황 등)을 요청하면, "
    "브라우저 수작업으로 새로 만들기 전에 반드시 먼저 list_app_actions 로 이미 만들어진 기능이 "
    "있는지 검색하세요. 있으면 run_app_action 으로 그 기능을 재사용합니다. "
    "검색 결과가 없을 때만 브라우저 도구로 직접 수행하세요.\n"
    "■ 실행 원칙(필수): ⚠ 표시가 없는 동작은 사용자에게 묻지 말고 즉시 도구를 호출·실행하세요. "
    "⚠ 동작(발송·결제·삭제)만 '~을(를) 실행할까요?' 라고 한 번 확인하세요. "
    "절대로 '진행할까요?', '확인하시겠습니까?', '실행해도 될까요?' 같은 질문으로 흐름을 끊지 마세요.\n"
    "■ 공개정보 조회 원칙(필수): 외부 공개 정보(뉴스·공모전·지원사업·기업/기관 소식·일반 사실)는 "
    "특정 사이트 로그인이 꼭 필요한 게 아니라면 먼저 web_search 로 찾으세요(브라우저 불필요). "
    "로그인된 내 계정 화면(메일·셀러센터·카페 등)에서만 가능한 일일 때만 브라우저 도구를 씁니다.\n"
    "■ 떠넘기기 금지(필수): 절대로 '직접 검색하세요', '브라우저를 사용할 수 없습니다', "
    "'다른 방법으로 확인하세요' 같이 작업을 사용자에게 미루지 마세요. "
    "브라우저 도구가 막히면 web_search·call_local_api 등 대체 수단으로 끝까지 시도하고, "
    "그래도 불가능하면 막힌 구체적 사유와 사용자가 할 수 있는 다음 행동(예: 해당 사이트 로그인)을 제시하세요.\n"
    "로그인 페이지가 나오면 사용자에게 로그인을 요청하세요. "
    "일반 질문·대화는 도구 없이 바로 답하세요. "
    "목적을 달성하면 결과를 간결히 보고하세요."
)

# 앱 동작 실행 시 부여할 owner 컨텍스트(데스크톱=owner 본인).
_OWNER = {
    "actor": "ai-agent",
    "role": "owner",
    "organization_ids": ["default-org"],
    "active_organization_id": "default-org",
}

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_page",
            "description": "현재 열린 브라우저 페이지의 URL·제목·클릭가능 요소(번호 포함)·본문 일부를 읽는다. 작업 전 먼저 호출.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "브라우저를 주어진 URL(http로 시작)로 이동한다.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "이동할 전체 URL"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "read_page 가 알려준 요소 번호(index)를 클릭한다.",
            "parameters": {
                "type": "object",
                "properties": {"index": {"type": "integer"}},
                "required": ["index"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "요소 번호(index)에 텍스트를 입력한다.",
            "parameters": {
                "type": "object",
                "properties": {"index": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["index", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "페이지를 위/아래로 스크롤한다.",
            "parameters": {
                "type": "object",
                "properties": {"direction": {"type": "string", "enum": ["down", "up"]}},
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "session_status",
            "description": "외부 사이트(네이버/스토어/EUM/가비아 등) 로그인 세션 현황을 조회한다.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_app_actions",
            "description": "앱 내부 기능(동작) 목록을 검색한다. 사용자가 앱 기능을 요청하면 먼저 이걸로 정확한 path 와 위험도를 확인. 예: '카페 분석', '블로그', '지원사업', '세션'.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "검색어(공백구분 다중 가능)"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_app_action",
            "description": (
                "앱 내부 기능을 실행한다. path 는 list_app_actions 가 알려준 값. "
                "⚠ 표시가 없는 동작은 즉시 실행. "
                "⚠ 표시(발송·결제·삭제 등)는 confirmed=true 로 사용자 확인 후 실행."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "동작 경로(list_app_actions 결과의 path)"},
                    "params": {"type": "object", "description": "동작 입력값"},
                    "confirmed": {"type": "boolean", "description": "⚠ 동작만 사용. 사용자가 명시 승인한 경우 true."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "smartstore_register_product",
            "description": (
                "네이버 스마트스토어에 상품을 등록한다(폼 자동 입력 후 임시저장 — 최종 저장은 사용자가 직접). "
                "셀러센터 로그인 세션이 필요. 상품명·가격·재고는 필수. "
                "완료 후 '폼 작성 완료, 저장 버튼을 눌러주세요' 안내."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "상품명(필수)"},
                    "price": {"type": "integer", "description": "판매가(원, 필수)"},
                    "stock": {"type": "integer", "description": "재고 수량(필수)"},
                    "category": {"type": "string", "description": "카테고리 경로(예: '패션의류 > 상의 > 티셔츠')"},
                    "description": {"type": "string", "description": "상품 설명(HTML 가능)"},
                    "keywords": {"type": "array", "items": {"type": "string"}, "description": "검색 태그 목록"},
                    "main_image": {"type": "string", "description": "메인 이미지 파일 경로(로컬 절대경로)"},
                    "tax_type": {"type": "string", "description": "과세유형: 과세(기본)|면세|영세"},
                    "product_type": {"type": "string", "description": "상품유형: 신상품(기본)|중고"},
                    "origin": {"type": "string", "description": "원산지(예: '국내산')"},
                    "extra": {"type": "object", "description": "기타 추가 필드"},
                },
                "required": ["name", "price", "stock"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "smartstore_list_products",
            "description": "네이버 스마트스토어 상품 목록을 조회한다(최근 캐시 또는 실시간 수집). 셀러센터 로그인 세션 필요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "refresh": {"type": "boolean", "description": "True면 실시간 수집, False(기본)면 캐시 반환"},
                    "limit": {"type": "integer", "description": "최대 상품 수(기본 50)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "smartstore_list_orders",
            "description": "네이버 스마트스토어 최근 주문 목록을 조회한다. 셀러센터 로그인 세션 필요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "주문상태 필터(신규주문|발송대기|발송완료|전체)"},
                    "limit": {"type": "integer", "description": "최대 주문 수(기본 30)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "공개 웹 정보를 검색한다(네이버 뉴스 검색, CDP 브라우저 불필요). "
                "뉴스·공모전·지원사업·기업/기관 소식·일반 사실 확인에 사용. "
                "특정 사이트 로그인이 필요 없는 공개정보 조회는 브라우저 대신 이 도구를 먼저 쓴다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색어"},
                    "page": {"type": "integer", "description": "페이지(기본 1)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_local_api",
            "description": (
                "로컬 FastAPI 서버의 엔드포인트를 직접 호출해 데이터를 조회·분석한다. "
                "카페 목록·분석, 뉴스 검색, 정산, 키워드 등 모든 앱 기능에 사용. "
                "예: path='/api/v1/naver-cafe/my-cafes' method='GET' 으로 카페 목록 조회. "
                "path='/api/v1/naver-cafe/ai-analyze' method='POST' body={...} 로 AI 분석."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "API 경로 (예: /api/v1/naver-cafe/my-cafes)"},
                    "method": {"type": "string", "description": "HTTP 메서드: GET(기본) 또는 POST"},
                    "body": {"type": "object", "description": "POST 요청 body (선택)"},
                    "params": {"type": "object", "description": "GET 쿼리 파라미터 (선택)"},
                },
                "required": ["path"],
            },
        },
    },
]

# 자율 에이전트 도구를 중앙 레지스트리에 등록(채팅 도구와 함께 all_tools 로 일괄 조회).
# OpenAI 직접 포맷이므로 register_openai 로 정규화 등록. 실행은 _exec_browser 가 담당.
try:
    from ai_orchestrator.connectors.tool_registry import register_openai

    register_openai("agent", _TOOLS)
except Exception:
    pass


def _fmt_obs(obs: dict) -> str:
    """관찰 결과를 GPT가 읽을 텍스트로."""
    els = "\n".join(
        f"  [{e['idx']}] <{e['tag']}{('/' + e['type']) if e.get('type') else ''}> {e['text'][:50]}"
        + (f" → {e['href'][:40]}" if e.get("href") else "")
        for e in obs.get("elements", [])[:50]
    )
    return (
        f"URL: {obs.get('url', '')}\n제목: {obs.get('title', '')[:80]}\n"
        f"[클릭가능 요소]\n{els or '  (없음)'}\n\n[본문]\n{obs.get('bodyText', '')[:1500]}"
    )


def run_free_agent(
    message: str,
    model: str | None = None,
    max_steps: int = 20,
    login_wait: bool = False,
    history: list[dict] | None = None,
) -> dict:
    """GPT 자율 도구호출로 사용자 명령 수행. 현재 페이지를 이어받아 작업.

    history: 같은 채팅창의 이전 대화([{role,content}...]) — 멀티턴 맥락 유지.
    반환: {"ok": bool, "text": str, "needs_login": bool, "login_url": str}
    """
    from ai_orchestrator.openai_proxy_caller import call_openai_agent
    from scripts.web_connector import get_page, run_on_browser_thread

    state: dict = {"obs": None}  # 최근 read_page 관찰(click index 매핑용)

    def _observe_now() -> dict:
        return run_on_browser_thread(lambda: _ag._observe(get_page()))

    def _exec_browser(name: str, args: dict) -> str:
        if name == "read_page":
            obs = _observe_now()
            state["obs"] = obs
            return _fmt_obs(obs)
        if name == "navigate":
            url = (args.get("url") or "").strip()
            if not url.lower().startswith("http"):
                return "오류: url은 http로 시작해야 합니다."

            def _go():
                p = get_page()
                _ag._execute(p, {"action": "goto", "url": url}, {})
                return _ag._observe(p)

            obs = run_on_browser_thread(_go)
            state["obs"] = obs
            return _fmt_obs(obs)
        if name in ("click", "type_text"):
            obs = state.get("obs") or {}
            idx = args.get("index")
            decision = (
                {"action": "click", "index": idx}
                if name == "click"
                else {"action": "type", "index": idx, "text": args.get("text", "")}
            )
            outcome = run_on_browser_thread(lambda: _ag._execute(get_page(), decision, obs))
            new = _observe_now()
            state["obs"] = new
            return f"{outcome}\n\n[변경 후 페이지]\n{_fmt_obs(new)}"
        if name == "scroll":
            run_on_browser_thread(
                lambda: _ag._execute(get_page(), {"action": "scroll", "dir": args.get("direction", "down")}, {})
            )
            obs = _observe_now()
            state["obs"] = obs
            return _fmt_obs(obs)
        if name == "session_status":
            from ai_orchestrator.agent_ai_proxy_router import _op_session_status

            return _op_session_status()
        if name == "list_app_actions":
            from ai_orchestrator import app_actions

            acts = app_actions.list_actions(args.get("query", ""))
            head = f"앱 동작 {len(acts)}개" + (" (상위 40)" if len(acts) > 40 else "") + ":\n"
            # DESTRUCTIVE 만 ⚠ 표시, 나머지는 표시 없음
            return head + "\n".join(
                f"  {'⚠ ' if a['risk'] == 'DESTRUCTIVE' else ''}{a['path']} — {a['desc']}" for a in acts[:40]
            )
        if name == "run_app_action":
            from ai_orchestrator import app_actions

            confirmed = bool(args.get("confirmed", False))
            rr = app_actions.run_action(args.get("path", ""), args.get("params") or {}, _OWNER, confirmed=confirmed)
            if rr.get("needs_confirm"):
                return rr.get("message", "확인이 필요한 동작입니다.")
            if rr.get("ok"):
                return f"실행 결과:\n{rr.get('result', '')}"
            return f"실행 실패: {rr.get('error', '')}"
        if name == "smartstore_register_product":
            return _ss_register_product(args)
        if name == "smartstore_list_products":
            return _ss_list_products(args)
        if name == "smartstore_list_orders":
            return _ss_list_orders(args)
        if name == "web_search":
            return _web_search(args)
        if name == "call_local_api":
            return _call_local_api(args)
        return f"알 수 없는 도구: {name}"

    messages: list[dict] = [{"role": "system", "content": _SYSTEM}]
    for h in history or []:  # 이전 대화(멀티턴 맥락)
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])[:1500]})
    messages.append({"role": "user", "content": message})
    for _ in range(max(1, min(max_steps, 20))):
        res = call_openai_agent(messages=messages, tools=_TOOLS, model=model, max_tokens=2000)
        if not res.get("ok"):
            return {"ok": False, "text": f"AI 오류: {res.get('error_code')}", "needs_login": False}
        msg = res["message"]
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return {"ok": True, "text": (msg.get("content") or "완료").strip(), "needs_login": False}
        messages.append(msg)
        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            try:
                args = json.loads(tc.get("function", {}).get("arguments") or "{}")
            except Exception:
                args = {}
            _CDP_TOOLS = {"read_page", "navigate", "click", "type_text", "scroll"}
            try:
                result = _exec_browser(name, args)
            except Exception as e:
                emsg = str(e).lower()
                if name in _CDP_TOOLS and (
                    "connect" in emsg or "cdp" in emsg or "context" in emsg or "playwright" in emsg
                ):
                    # CDP 브라우저 전용 도구만 no_browser 처리. API 도구는 계속 진행.
                    result = "⚠️ CDP 브라우저가 실행되지 않아 이 도구를 사용할 수 없습니다. 공개정보 조회면 web_search, 앱 기능이면 call_local_api 등 브라우저 불필요 도구로 대신 처리하세요. 사용자에게 '직접 하라'고 떠넘기지 마세요."
                else:
                    result = f"도구 '{name}' 실행 오류: {str(e)[:120]}"
            # 로그인 벽 감지 → 비동기/안내 흐름으로 위임.
            # navigate/click 으로 '이동한 결과' 로그인 페이지일 때만 에스컬레이션.
            # (현재 페이지를 단순 read_page 한 경우는 GPT가 보고 스스로 판단)
            cur = (state.get("obs") or {}).get("url", "")
            if name in ("navigate", "click") and _ag._is_login_page(cur):
                _ag._show_cdp_window()
                logged_in = login_wait and run_on_browser_thread(
                    lambda: _ag._wait_for_login(get_page(), None, timeout=180), timeout=200
                )
                if logged_in:
                    result += "\n(로그인 완료 — 계속 진행)"
                else:
                    return {"ok": False, "needs_login": True, "login_url": cur, "text": "로그인이 필요합니다."}
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result[:4000]})
    return {"ok": True, "text": "최대 단계 도달 — 부분 수행", "needs_login": False}


# ── 스마트스토어 전용 도구 핸들러 ──────────────────────────────────────────────

# 내부 FastAPI 포트는 환경마다 다르다(로컬 dev=8401, prod 컨테이너=8400).
# 같은 프로세스가 listen 하는 포트(APP_PORT)로 자기 자신을 호출한다. 하드코딩 금지.
# (prod 에서 8401 하드코딩 시 call_local_api/web_search/smartstore 도구 전부 연결거부됨)
_LOCAL_PORT = (os.environ.get("APP_PORT") or "8401").strip() or "8401"

_SS_API = f"http://127.0.0.1:{_LOCAL_PORT}/api/v1/smartstore"
# 서버 _WEB_UI_PASS(agent_ai_proxy_router.py)와 동일한 환경변수에서 읽어 동기화
_SS_AUTH = ("owner", os.environ.get("NEXT_PUBLIC_API_PASS", "haehan2024!"))


_LOCAL_API = f"http://127.0.0.1:{_LOCAL_PORT}"
_LOCAL_AUTH = ("owner", os.environ.get("NEXT_PUBLIC_API_PASS", "haehan2024!"))


def _web_search(args: dict) -> str:
    """공개 웹 정보 검색 — 네이버 뉴스검색(Naver OpenAPI) 커넥터를 in-process 직접 호출.

    HTTP 자기호출(call_local_api) 대신 같은 프로세스의 커넥터 함수를 바로 부른다.
    → 포트(8400/8401)·내부 인증(require_role)·네트워크 의존이 없어 local·prod 동일 동작.
    브라우저가 없어도 동작하므로, 공개정보 조회는 브라우저보다 이 경로를 먼저 쓴다.
    """
    query = (args.get("query") or "").strip()
    if not query:
        return "오류: query(검색어)가 필요합니다."
    try:
        page = int(args.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    try:
        from ai_orchestrator.connectors.naver_news_router import _naver_openapi_news

        items = _naver_openapi_news(query, page=page)
    except Exception as e:  # 키 미설정·네트워크 등 — 사용자에게 떠넘기지 말고 사유만 보고
        return f"검색 중 오류가 발생했습니다({str(e)[:120]}). 검색어를 바꿔 다시 시도해 주세요."
    if not items:
        return f"'{query}' 검색 결과가 없습니다. 더 일반적인 검색어로 다시 시도하거나, 로그인 사이트라면 브라우저로 접근하세요."
    lines = [f"'{query}' 검색 결과 {len(items)}건:"]
    for it in items[:10]:
        title = (it.get("title") or "").strip()
        summary = (it.get("summary") or "").strip()
        url = it.get("url") or ""
        when = it.get("datetime") or ""
        lines.append(f"- {title} ({when})\n  {summary[:120]}\n  {url}")
    return "\n".join(lines)


def _call_local_api(args: dict) -> str:
    """로컬 FastAPI 엔드포인트 직접 호출 — GET/POST 모두 지원."""
    try:
        import json as _json

        import requests as _req

        path = args.get("path", "")
        method = (args.get("method") or "GET").upper()
        body = args.get("body") or None
        params = args.get("params") or None
        url = f"{_LOCAL_API}{path}"
        r = _req.request(method, url, auth=_LOCAL_AUTH, json=body, params=params, timeout=60)
        if r.status_code == 200:
            try:
                d = r.json()
                return _json.dumps(d, ensure_ascii=False, default=str)[:3000]
            except Exception:
                return r.text[:3000]
        return f"HTTP {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return f"API 호출 오류: {str(e)[:200]}"


def _ss_call(method: str, path: str, **kwargs) -> dict:
    """스마트스토어 FastAPI 내부 호출. requests Basic Auth."""
    try:
        import requests as _req

        url = f"{_SS_API}{path}"
        r = _req.request(method, url, auth=_SS_AUTH, timeout=30, **kwargs)
        if r.status_code == 200:
            return r.json()
        return {"ok": False, "error": f"HTTP {r.status_code}", "body": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _ss_register_product(args: dict) -> str:
    """상품 등록 폼 자동 입력 (임시저장, 최종 저장은 사용자 직접)."""
    data = {
        "name": args.get("name", ""),
        "price": int(args.get("price") or 0),
        "stock": int(args.get("stock") or 0),
        "category": args.get("category", ""),
        "description": args.get("description", ""),
        "keywords": args.get("keywords") or [],
        "main_image": args.get("main_image", ""),
        "tax_type": args.get("tax_type", "과세"),
        "product_type": args.get("product_type", "신상품"),
        "origin": args.get("origin", ""),
        **(args.get("extra") or {}),
    }
    result = _ss_call("POST", "/products/auto-register", json={"data": data, "dry_run": True})
    if result.get("ok"):
        sections = result.get("sections", {})
        done = [k for k, v in sections.items() if isinstance(v, dict) and v.get("ok")]
        fail = [k for k, v in sections.items() if isinstance(v, dict) and not v.get("ok")]
        msg = f"✅ 상품 등록 폼 작성 완료!\n입력된 섹션: {', '.join(done) if done else '없음'}"
        if fail:
            msg += f"\n⚠️ 실패 섹션: {', '.join(fail)}"
        msg += "\n\n📌 CDP 브라우저에서 최종 '저장' 버튼을 눌러주세요."
        return msg
    err = result.get("error", "알 수 없는 오류")
    if "로그인" in err or "session" in err.lower() or "401" in err:
        return (
            "⚠️ 스마트스토어 셀러센터 로그인이 필요합니다. CDP 브라우저에서 sell.smartstore.naver.com 에 로그인해주세요."
        )
    return f"❌ 상품 등록 실패: {err}\n힌트: CDP 브라우저에서 스마트스토어 셀러센터에 로그인되어 있는지 확인하세요."


def _ss_list_products(args: dict) -> str:
    """상품 목록 조회."""
    refresh = bool(args.get("refresh", False))
    limit = int(args.get("limit") or 50)
    if refresh:
        result = _ss_call("POST", f"/products/collect?limit={limit}")
    else:
        result = _ss_call("GET", "/products")
    if result.get("ok"):
        rows = result.get("rows") or result.get("products") or []
        if not rows:
            return "상품 목록이 비어 있습니다. refresh=true 로 실시간 수집을 시도해보세요."
        lines = [f"총 {len(rows)}개 상품:"]
        for r in rows[:30]:
            name = r.get("name") or r.get("productName", "")
            pid = r.get("productId") or r.get("id", "")
            price = r.get("price") or r.get("salePrice", "")
            stock = r.get("stock") or r.get("stockCount", "")
            status = r.get("status") or r.get("productStatus", "")
            lines.append(f"  [{pid}] {name} — {price}원 / 재고 {stock} / {status}")
        return "\n".join(lines)
    err = result.get("error", "")
    if "로그인" in err or "401" in err:
        return "⚠️ 스마트스토어 셀러센터 로그인이 필요합니다."
    return f"상품 목록 조회 실패: {err}"


def _ss_list_orders(args: dict) -> str:
    """주문 목록 조회."""
    status = args.get("status", "")
    limit = int(args.get("limit") or 30)
    params = {}
    if status:
        params["status"] = status
    params["limit"] = limit
    result = _ss_call("GET", "/orders", params=params)
    if result.get("ok"):
        rows = result.get("rows") or result.get("orders") or []
        if not rows:
            return "주문 목록이 비어 있습니다."
        lines = [f"총 {len(rows)}건 주문:"]
        for r in rows[:30]:
            oid = r.get("orderId") or r.get("id", "")
            buyer = r.get("buyerName") or r.get("buyer", "")
            prod = r.get("productName") or r.get("name", "")
            amt = r.get("paymentAmount") or r.get("amount", "")
            st = r.get("orderStatus") or r.get("status", "")
            lines.append(f"  [{oid}] {buyer} / {prod} / {amt}원 / {st}")
        return "\n".join(lines)
    err = result.get("error", "")
    if "로그인" in err or "401" in err:
        return "⚠️ 스마트스토어 셀러센터 로그인이 필요합니다."
    return f"주문 목록 조회 실패: {err}"
