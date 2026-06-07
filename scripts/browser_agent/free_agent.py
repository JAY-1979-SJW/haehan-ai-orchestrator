"""자율 도구호출 에이전트 — GPT가 도구를 자유롭게 골라 사용자 명령을 수행.

기존 통제 파이프라인(분류기·고정 URL표·경직 루프)을 대체. GPT가 Claude처럼
'관찰→판단→도구 호출→반복'으로 자유롭게 일한다. 현재 열린 페이지(사용자 수동 작업)를
먼저 읽어 그대로 이어받는다.

안전: 결제/구매/삭제/발송/제출 등 파괴적 동작은 차단(_is_destructive). 읽기·탐색·입력은 자유.
재사용: agent.py 의 _observe/_execute/_is_destructive/_wait_for_login/_show_cdp_window.
"""

from __future__ import annotations

import json

from scripts.browser_agent import agent as _ag

_SYSTEM = (
    "당신은 사용자의 로컬 로그인된 웹 브라우저를 완전히 제어하는 자율 에이전트입니다. "
    "사용자 명령을 달성하기 위해 제공된 도구를 스스로 골라 순서대로 사용하세요.\n"
    "- 먼저 read_page 로 '현재 열린 페이지'를 확인하세요. 사용자가 수동으로 로그인·이동해 둔 "
    "상태를 그대로 이어받아 작업합니다. 꼭 필요할 때만 navigate 로 이동하세요.\n"
    "- 사용자가 '여기서', '이 페이지에서', '현재 화면' 등으로 지시하면 절대 다른 곳으로 navigate 하지 말고 "
    "반드시 read_page 로 읽은 '지금 그 페이지'에서 작업하세요(사용자가 이미 로그인해 둔 사이트임).\n"
    "- click/type_text 는 read_page 가 준 요소 번호(index)로 조작합니다.\n"
    "- 모든 동작(클릭·입력·제출·발송 포함)을 사용자 명령대로 직접 수행하세요. 제약 없이 실행합니다.\n"
    "- 로그인 페이지가 나오면 당신은 로그인할 수 없으니, 사용자에게 로그인을 요청하세요.\n"
    "- 네이버 스마트스토어 작업(상품등록·상품목록·주문조회)은 전용 도구 "
    "smartstore_register_product / smartstore_list_products / smartstore_list_orders 를 사용하세요. "
    "단, 스마트스토어 셀러센터(sell.smartstore.naver.com)에 로그인된 세션이 필요합니다. "
    "로그인 안 된 경우 사용자에게 CDP 브라우저에서 스마트스토어 셀러센터에 로그인을 요청하세요.\n"
    "- 앱 내부 기능(카페·커뮤니티 분석, 블로그, 지원사업, 뉴스/키워드, 세션, 정산 등)이 필요하면 "
    "list_app_actions 로 알맞은 동작(path)을 찾고 run_app_action 으로 실행하세요.\n"
    "- 웹/브라우저가 필요 없는 일반 질문·대화·조언은 도구를 쓰지 말고 바로 한국어로 답하세요.\n"
    "- 이전 대화 맥락을 이어가세요. 지시가 모호하면(예: '탐색해줘'만 있고 목적이 불명확) 추측해 "
    "실행하지 말고, 무엇을 원하는지 한 문장으로 사용자에게 되물으세요. 사용자가 답하면 그 맥락으로 이어 진행.\n"
    "- 같은 도구를 의미 없이 반복하지 말고, 목적을 달성하면 도구 없이 한국어로 결과를 간단히 보고하세요."
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
            "description": "앱 내부 기능을 실행한다. path 는 list_app_actions 가 알려준 값. 위험·민감 동작은 자동 차단되며, 그때는 사용자에게 확인을 받아야 한다. params 는 해당 동작의 입력값(JSON 객체).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "동작 경로(list_app_actions 결과의 path)"},
                    "params": {"type": "object", "description": "동작 입력값"},
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
]


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
            return head + "\n".join(f"  [{a['risk']}] {a['path']} — {a['desc']}" for a in acts[:40])
        if name == "run_app_action":
            from ai_orchestrator import app_actions

            rr = app_actions.run_action(args.get("path", ""), args.get("params") or {}, _OWNER)
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
            try:
                result = _exec_browser(name, args)
            except Exception as e:
                emsg = str(e).lower()
                if "connect" in emsg or "cdp" in emsg or "context" in emsg:
                    return {"ok": False, "text": "", "needs_login": False, "no_browser": True}
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

_SS_API = "http://127.0.0.1:8401/api/v1/smartstore"
_SS_AUTH = ("owner", "haehan2024!")  # Basic Auth (AUTH_ENABLED=false 환경)


def _ss_call(method: str, path: str, **kwargs) -> dict:
    """스마트스토어 FastAPI 내부 호출. requests Basic Auth."""
    try:
        import requests as _req

        url = f"{_SS_API}{path}"
        r = _req.request(method, url, auth=_SS_AUTH, timeout=120, **kwargs)
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
