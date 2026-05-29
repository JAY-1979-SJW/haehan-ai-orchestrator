"""스마트스토어 AI 채팅 엔드포인트 — Claude / GPT → 도구 호출 → SSE 스트리밍.

CDP 도구(collect_*, open_seller_center 등)는 로컬 에이전트로 라우팅.
캐시 조회(list_*)는 서버에서 직접 처리.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...auth import require_role
from ...audit_logger import log_event
from ._helpers import ROOT

router = APIRouter()

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
GPT_MODEL    = "gpt-4o-mini"
WRITE_TOOLS  = {"auto_register_product", "edit_product"}

# CDP가 필요한 도구 — 로컬 에이전트로 라우팅
CDP_TOOLS = {
    "collect_products", "collect_orders", "collect_settlements",
    "collect_reviews", "collect_stats", "open_seller_center",
    "auto_register_product", "edit_product", "popup_handle",
}

SYSTEM_PROMPT = """당신은 스마트스토어 셀러센터 AI 에이전트입니다.
사용자의 자연어 명령을 이해하고 적절한 도구를 호출하세요.
- 상품 등록·수정 등 쓰기 작업은 confirmed=true일 때만 실행합니다
- 조회·수집은 바로 실행합니다
- 결과가 많으면 핵심만 요약해서 한국어로 간결하게 답변합니다
- 도구 결과의 rows/items 배열은 건수와 주요 항목만 요약합니다"""


# ── 도구 정의 ─────────────────────────────────────────────────────────────────

def _tool_defs() -> list[dict]:
    return [
        {"name": "list_products",        "description": "스마트스토어 상품 목록을 캐시에서 조회합니다.",        "params": {}},
        {"name": "collect_products",     "description": "CDP로 상품 목록을 실시간 수집합니다.",              "params": {"limit": {"type": "integer"}}},
        {"name": "list_orders",          "description": "주문 목록을 캐시에서 조회합니다.",                   "params": {}},
        {"name": "collect_orders",       "description": "CDP로 주문 목록을 실시간 수집합니다.",              "params": {"limit": {"type": "integer"}}},
        {"name": "list_settlements",     "description": "정산 내역을 캐시에서 조회합니다.",                  "params": {}},
        {"name": "collect_settlements",  "description": "CDP로 정산 내역을 실시간 수집합니다.",             "params": {"limit": {"type": "integer"}}},
        {"name": "list_reviews",         "description": "리뷰·문의 목록을 캐시에서 조회합니다.",             "params": {}},
        {"name": "collect_reviews",      "description": "CDP로 리뷰·문의를 실시간 수집합니다.",             "params": {"limit": {"type": "integer"}}},
        {"name": "list_stats",           "description": "데이터 분석(통계)을 캐시에서 조회합니다.",          "params": {}},
        {"name": "collect_stats",        "description": "CDP로 데이터 분석(통계)을 실시간 수집합니다.",      "params": {}},
        {"name": "open_seller_center",   "description": "CDP 브라우저를 셀러센터 지정 페이지로 이동합니다.",
         "params": {"page_key": {"type": "string", "enum": ["dashboard","list","register","orders","settlement","reviews","stats"]}}},
        {"name": "auto_register_product","description": "CDP로 상품 등록 폼을 자동으로 채웁니다 (쓰기).",
         "params": {"name":{"type":"string"},"price":{"type":"integer"},"stock":{"type":"integer"},
                    "category":{"type":"string"},"brand":{"type":"string"},
                    "keywords":{"type":"array","items":{"type":"string"}},
                    "description":{"type":"string"},"model_name":{"type":"string"},"origin":{"type":"string"}},
         "required": ["name","price","stock"]},
        {"name": "edit_product",         "description": "CDP로 기존 상품을 수정합니다 (쓰기).",
         "params": {"product_id":{"type":"string"},"name":{"type":"string"},"price":{"type":"integer"},
                    "stock":{"type":"integer"},"description":{"type":"string"},
                    "keywords":{"type":"array","items":{"type":"string"}},"brand":{"type":"string"},"origin":{"type":"string"}},
         "required": ["product_id"]},
        {"name": "generate_description", "description": "Claude 또는 GPT로 상품 상세설명 HTML을 생성합니다.",
         "params": {"data":{"type":"object"},"model":{"type":"string","enum":["claude","gpt"]}},
         "required": ["data"]},
        {"name": "search_categories",    "description": "카테고리 이름·경로를 검색합니다.",
         "params": {"q":{"type":"string"}}, "required": ["q"]},
        {"name": "popup_handle",         "description": "CDP 브라우저 팝업을 자동으로 닫습니다.", "params": {}},
    ]


def _to_claude_tools(confirmed: bool) -> list:
    import anthropic
    result = []
    for t in _tool_defs():
        if not confirmed and t["name"] in WRITE_TOOLS:
            continue
        schema: dict = {"type": "object", "properties": t["params"]}
        if "required" in t:
            schema["required"] = t["required"]
        result.append(anthropic.types.ToolParam(name=t["name"], description=t["description"], input_schema=schema))
    return result


def _to_gpt_tools(confirmed: bool) -> list:
    result = []
    for t in _tool_defs():
        if not confirmed and t["name"] in WRITE_TOOLS:
            continue
        params: dict = {"type": "object", "properties": t["params"]}
        if "required" in t:
            params["required"] = t["required"]
        result.append({"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": params}})
    return result


# ── 로컬 도구 실행 ─────────────────────────────────────────────────────────────

def _run_tool(name: str, inputs: dict, license_key: str | None = None) -> dict:
    """도구 실행 — CDP 도구는 로컬 에이전트로, 나머지는 서버 직접 처리."""
    sys.path.insert(0, str(ROOT))
    from ._helpers import load_ss

    # ── 로컬 에이전트 라우팅 (CDP 도구) ────────────────────────────────────────
    if name in CDP_TOOLS and license_key:
        from .agent_ws import call_local_tool
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(call_local_tool(license_key, name, inputs))
        finally:
            loop.close()

    # ── 서버 직접 처리 (캐시 조회, AI 생성 등) ──────────────────────────────────
    try:
        if name == "list_products":        return load_ss("products")
        if name == "list_orders":          return load_ss("orders")
        if name == "list_settlements":     return load_ss("settlements")
        if name == "list_reviews":         return load_ss("reviews")
        if name == "list_stats":           return load_ss("stats")

        if name == "collect_products":
            import time as _t
            from playwright.sync_api import sync_playwright
            from scripts.naver.smartstore import NaverSmartStore
            from ._helpers import save_ss, now_iso, elapsed_ms
            t0 = _t.monotonic()
            with sync_playwright() as pw:
                page = pw.chromium.connect_over_cdp(cdp).contexts[0].pages[0]
                result = NaverSmartStore(page).list_products(limit=inputs.get("limit", 50))
            result.update({"collected_at": now_iso(), "duration_ms": elapsed_ms(t0)})
            save_ss("products", result)
            return result

        if name == "collect_orders":
            import time as _t
            from playwright.sync_api import sync_playwright
            from scripts.naver.smartstore import NaverSmartStore
            from ._helpers import save_ss, now_iso, elapsed_ms
            t0 = _t.monotonic()
            with sync_playwright() as pw:
                page = pw.chromium.connect_over_cdp(cdp).contexts[0].pages[0]
                result = NaverSmartStore(page).list_orders(limit=inputs.get("limit", 50))
            result.update({"collected_at": now_iso(), "duration_ms": elapsed_ms(t0)})
            save_ss("orders", result)
            return result

        if name == "collect_settlements":
            import time as _t
            from playwright.sync_api import sync_playwright
            from scripts.naver.smartstore import NaverSmartStore
            from ._helpers import save_ss, now_iso, elapsed_ms
            t0 = _t.monotonic()
            with sync_playwright() as pw:
                page = pw.chromium.connect_over_cdp(cdp).contexts[0].pages[0]
                result = NaverSmartStore(page).list_settlements(limit=inputs.get("limit", 30))
            result.update({"collected_at": now_iso(), "duration_ms": elapsed_ms(t0)})
            save_ss("settlements", result)
            return result

        if name == "collect_reviews":
            import time as _t
            from playwright.sync_api import sync_playwright
            from scripts.naver.smartstore import NaverSmartStore
            from ._helpers import save_ss, now_iso, elapsed_ms
            t0 = _t.monotonic()
            with sync_playwright() as pw:
                page = pw.chromium.connect_over_cdp(cdp).contexts[0].pages[0]
                result = NaverSmartStore(page).list_reviews(limit=inputs.get("limit", 30))
            result.update({"collected_at": now_iso(), "duration_ms": elapsed_ms(t0)})
            save_ss("reviews", result)
            return result

        if name == "collect_stats":
            import time as _t
            from playwright.sync_api import sync_playwright
            from scripts.naver.smartstore import NaverSmartStore
            from ._helpers import save_ss, now_iso, elapsed_ms
            t0 = _t.monotonic()
            with sync_playwright() as pw:
                page = pw.chromium.connect_over_cdp(cdp).contexts[0].pages[0]
                result = NaverSmartStore(page).stats()
            result.update({"collected_at": now_iso(), "duration_ms": elapsed_ms(t0)})
            save_ss("stats", result)
            return result

        if name == "open_seller_center":
            from .seller_center import SELLER_CENTER_URLS
            from playwright.sync_api import sync_playwright
            url = SELLER_CENTER_URLS.get(inputs.get("page_key", "dashboard"))
            if not url:
                return {"ok": False, "error": f"알 수 없는 page_key: {inputs.get('page_key')}"}
            with sync_playwright() as pw:
                page = pw.chromium.connect_over_cdp(cdp).contexts[0].pages[0]
                page.bring_to_front()
                page.goto(url, timeout=15000, wait_until="domcontentloaded")
            return {"ok": True, "url": url}

        if name == "auto_register_product":
            from playwright.sync_api import sync_playwright
            from scripts.naver.smartstore.product.form_runner import ProductFormRunner
            data = {**inputs, "save": False, "require_confirm": False}
            REGISTER_URL = "https://sell.smartstore.naver.com/#/products/create"
            with sync_playwright() as pw:
                ctx = pw.chromium.connect_over_cdp(cdp).contexts[0]
                page = next((p for p in ctx.pages if "products/create" in p.url), None)
                if not page:
                    page = ctx.new_page()
                    page.goto(REGISTER_URL, timeout=20000, wait_until="domcontentloaded")
                page.bring_to_front()
                return {**ProductFormRunner(page).run(data, skip_open=True), "dry_run": True}

        if name == "edit_product":
            from playwright.sync_api import sync_playwright
            from scripts.naver.smartstore.product.form_runner import ProductFormRunner
            product_id = inputs.get("product_id")
            fields = {k: v for k, v in inputs.items() if k != "product_id"}
            fields["save"] = False
            with sync_playwright() as pw:
                ctx = pw.chromium.connect_over_cdp(cdp).contexts[0]
                page = next((p for p in ctx.pages if f"products/{product_id}" in p.url), None) or ctx.new_page()
                page.bring_to_front()
                return {**ProductFormRunner(page).edit(product_id, fields), "dry_run": True}

        if name == "generate_description":
            from scripts.naver.smartstore.product.ai_description_writer import AIDescriptionWriter, DEFAULT_MODEL, QUALITY_MODEL
            return AIDescriptionWriter(model=QUALITY_MODEL if inputs.get("model") == "quality" else DEFAULT_MODEL).generate(inputs.get("data", {}))

        if name == "search_categories":
            from scripts.naver.smartstore.product.category_cache import load_cache
            cats = load_cache()
            q = str(inputs.get("q", "")).lower()
            matches = [c for c in cats if q in c.get("name","").lower() or q in c.get("path","").lower()]
            return {"ok": True, "count": len(matches), "results": matches[:20]}

        if name == "popup_handle":
            from scripts.naver.smartstore.navigation.cdp_popup_manager import CdpPopupManager
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                ctx = pw.chromium.connect_over_cdp(cdp).contexts[0]
                page = ctx.pages[0]
                mgr = CdpPopupManager()
                mgr.unblock(ctx, origin="https://sell.smartstore.naver.com")
                return mgr.handle_page(page, auto_confirm=True)

        return {"ok": False, "error": f"알 수 없는 도구: {name}"}

    except Exception as e:
        return {"ok": False, "error": str(e), "hint": "CDP 브라우저가 실행 중인지 확인하세요"}


# ── SSE 헬퍼 ─────────────────────────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── Claude 루프 ───────────────────────────────────────────────────────────────

def _run_claude(messages: list, confirmed: bool, license_key: str | None = None):
    import anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        yield _sse("error", {"message": "ANTHROPIC_API_KEY 미설정 — .env에 추가하세요"})
        return

    client  = anthropic.Anthropic(api_key=api_key)
    tools   = _to_claude_tools(confirmed)
    history = list(messages)
    step    = 0

    while True:
        res = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=2048,
            system=SYSTEM_PROMPT, tools=tools, messages=history,
        )
        for b in res.content:
            if b.type == "text" and b.text:
                yield _sse("text", {"text": b.text})

        if res.stop_reason != "tool_use":
            break

        tool_results = []
        for b in res.content:
            if b.type != "tool_use":
                continue
            is_write = b.name in WRITE_TOOLS
            if is_write and not confirmed:
                yield _sse("confirm_required", {"tool": b.name, "inputs": b.input,
                    "message": f"'{b.input.get('name', b.name)}' 작업에 승인이 필요합니다."})
                return
            step += 1
            yield _sse("step_start", {"step": step, "tool": b.name, "inputs": b.input, "write": is_write})
            result = _run_tool(b.name, dict(b.input), license_key)
            yield _sse("step_done", {"step": step, "tool": b.name, "ok": result.get("ok") is not False, "result": result})
            tool_results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(result, ensure_ascii=False)})

        history.append({"role": "assistant", "content": res.content})
        history.append({"role": "user",      "content": tool_results})

    yield _sse("done", {"steps": step})


# ── GPT 루프 ─────────────────────────────────────────────────────────────────

def _run_gpt(messages: list, confirmed: bool, license_key: str | None = None):
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        yield _sse("error", {"message": "OPENAI_API_KEY 미설정 — .env에 추가하세요"})
        return

    client  = OpenAI(api_key=api_key)
    tools   = _to_gpt_tools(confirmed)
    history = [{"role": "system", "content": SYSTEM_PROMPT}] + list(messages)
    step    = 0

    while True:
        res = client.chat.completions.create(
            model=GPT_MODEL, max_tokens=2048,
            tools=tools, tool_choice="auto", messages=history,
        )
        msg = res.choices[0].message
        if msg.content:
            yield _sse("text", {"text": msg.content})
        if not msg.tool_calls:
            break

        tool_results = []
        for tc in msg.tool_calls:
            name    = tc.function.name
            inputs  = json.loads(tc.function.arguments or "{}")
            is_write = name in WRITE_TOOLS
            if is_write and not confirmed:
                yield _sse("confirm_required", {"tool": name, "inputs": inputs,
                    "message": f"'{inputs.get('name', name)}' 작업에 승인이 필요합니다."})
                return
            step += 1
            yield _sse("step_start", {"step": step, "tool": name, "inputs": inputs, "write": is_write})
            result = _run_tool(name, inputs, license_key)
            yield _sse("step_done", {"step": step, "tool": name, "ok": result.get("ok") is not False, "result": result})
            tool_results.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, ensure_ascii=False)})

        history.append(msg)
        history.extend(tool_results)

    yield _sse("done", {"steps": step})


# ── Request 모델 ──────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages:    List[ChatMessage]
    confirmed:   bool = False
    provider:    str  = "gpt"   # "claude" | "gpt"
    license_key: Optional[str] = None  # 로컬 에이전트 라우팅용


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@router.post("/chat")
def api_chat(body: ChatRequest, user: dict = Depends(require_role("admin", "owner"))):
    """자연어 명령 → LLM tool_use → 도구 실행(CDP=로컬, 나머지=서버) → SSE."""
    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    # 라이선스 검증 (제공된 경우)
    lic_key = body.license_key
    if lic_key:
        from .license import verify
        ok, _, reason = verify(lic_key)
        if not ok:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail=f"라이선스 오류: {reason}")

    def generate():
        try:
            runner = _run_gpt if body.provider == "gpt" else _run_claude
            yield from runner(messages, body.confirmed, lic_key)
        except Exception as e:
            yield _sse("error", {"message": str(e)})

    log_event("SMARTSTORE_CHAT", task_id="-", actor=user["actor"], role=user["role"],
              decision="ok", note=f"provider={body.provider} msgs={len(messages)}")

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
