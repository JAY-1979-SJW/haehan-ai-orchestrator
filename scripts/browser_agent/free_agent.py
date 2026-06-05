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
    "당신은 사용자의 로컬 로그인된 웹 브라우저를 운전하는 자율 에이전트입니다. "
    "사용자 명령을 달성하기 위해 제공된 도구를 스스로 골라 순서대로 사용하세요.\n"
    "- 먼저 read_page 로 '현재 열린 페이지'를 확인하세요. 사용자가 수동으로 로그인·이동해 둔 "
    "상태를 그대로 이어받아 작업합니다. 꼭 필요할 때만 navigate 로 이동하세요.\n"
    "- 사용자가 '여기서', '이 페이지에서', '현재 화면' 등으로 지시하면 절대 다른 곳으로 navigate 하지 말고 "
    "반드시 read_page 로 읽은 '지금 그 페이지'에서 작업하세요(사용자가 이미 로그인해 둔 사이트임).\n"
    "- click/type_text 는 read_page 가 준 요소 번호(index)로 조작합니다.\n"
    "- 결제·구매·송금·삭제·발송·제출 등 되돌릴 수 없는 동작은 절대 직접 하지 말고, 사용자에게 "
    "확인을 요청하는 문장으로 끝내세요.\n"
    "- 로그인 페이지가 나오면 당신은 로그인할 수 없으니, 사용자에게 로그인을 요청하세요.\n"
    "- 앱 내부 기능(카페·커뮤니티 분석, 블로그, 지원사업, 뉴스/키워드, 세션, 정산 등)이 필요하면 "
    "list_app_actions 로 알맞은 동작(path)을 찾고 run_app_action 으로 실행하세요. 위험·민감 동작(발송·"
    "결제·삭제·발행·승인 등)은 자동 차단되니, 무엇을 할지 사용자에게 알리고 확인을 받으세요.\n"
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
    max_steps: int = 12,
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
            tgt = _ag._element_text(obs, idx)
            if _ag._is_destructive(tgt):
                return (
                    f"차단: '{tgt[:40]}' 은(는) 위험 동작(결제/삭제/발송 등)이라 실행하지 않았습니다. 사용자 확인 필요."
                )
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
        return f"알 수 없는 도구: {name}"

    messages: list[dict] = [{"role": "system", "content": _SYSTEM}]
    for h in history or []:  # 이전 대화(멀티턴 맥락)
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])[:1500]})
    messages.append({"role": "user", "content": message})
    for _ in range(max(1, min(max_steps, 20))):
        res = call_openai_agent(messages=messages, tools=_TOOLS, model=model, max_tokens=700)
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
