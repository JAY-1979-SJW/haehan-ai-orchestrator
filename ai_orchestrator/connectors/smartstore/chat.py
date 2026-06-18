"""스마트스토어 AI 채팅 엔드포인트 — Claude / GPT → 도구 호출 → SSE 스트리밍.

CDP 도구(collect_*, open_seller_center 등)는 로컬 에이전트로 라우팅.
캐시 조회(list_*)는 서버에서 직접 처리.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...audit_logger import log_event
from ...auth import require_role
from ._helpers import ROOT

_TEMP_IMAGE_DIR = ROOT / "data" / "temp_images"

router = APIRouter()

GPT_MODEL = "gpt-4o-mini"
WRITE_TOOLS = {"auto_register_product", "edit_product", "reply_reviews", "process_shipping", "delete_product"}

# CDP가 필요한 도구 — 로컬 에이전트로 라우팅
CDP_TOOLS = {
    "collect_products",
    "collect_orders",
    "collect_settlements",
    "collect_reviews",
    "collect_stats",
    "open_seller_center",
    "auto_register_product",
    "edit_product",
    "popup_handle",
    "get_pending_reviews",
    "reply_reviews",
    "get_pending_orders",
    "process_shipping",
    "delete_product",
}

SYSTEM_PROMPT = """당신은 스마트스토어 셀러센터 AI 에이전트입니다.
사용자의 자연어 명령을 이해하고 적절한 도구를 호출하세요.
- 상품 등록·수정 등 쓰기 작업은 confirmed=true일 때만 실행합니다
- 조회·수집은 바로 실행합니다
- 결과가 많으면 핵심만 요약해서 한국어로 간결하게 답변합니다
- 도구 결과의 rows/items 배열은 건수와 주요 항목만 요약합니다
- **목록을 답변할 때는 반드시 각 항목을 줄바꿈(\\n)으로 구분해 한 줄에 하나씩 출력합니다. 절대 한 줄에 여러 항목을 나열하지 마세요.**
  예: "1. 첫째 항목\\n2. 둘째 항목\\n3. 셋째 항목" """


# ── 도구 정의 ─────────────────────────────────────────────────────────────────


def _tool_defs() -> list[dict]:
    return [
        {"name": "list_products", "description": "스마트스토어 상품 목록을 캐시에서 조회합니다.", "params": {}},
        {
            "name": "collect_products",
            "description": "CDP로 상품 목록을 실시간 수집합니다.",
            "params": {"limit": {"type": "integer"}},
        },
        {"name": "list_orders", "description": "주문 목록을 캐시에서 조회합니다.", "params": {}},
        {
            "name": "collect_orders",
            "description": "CDP로 주문 목록을 실시간 수집합니다.",
            "params": {"limit": {"type": "integer"}},
        },
        {"name": "list_settlements", "description": "정산 내역을 캐시에서 조회합니다.", "params": {}},
        {
            "name": "collect_settlements",
            "description": "CDP로 정산 내역을 실시간 수집합니다.",
            "params": {"limit": {"type": "integer"}},
        },
        {"name": "list_reviews", "description": "리뷰·문의 목록을 캐시에서 조회합니다.", "params": {}},
        {
            "name": "collect_reviews",
            "description": "CDP로 리뷰·문의를 실시간 수집합니다.",
            "params": {"limit": {"type": "integer"}},
        },
        {"name": "list_stats", "description": "데이터 분석(통계)을 캐시에서 조회합니다.", "params": {}},
        {"name": "collect_stats", "description": "CDP로 데이터 분석(통계)을 실시간 수집합니다.", "params": {}},
        {
            "name": "open_seller_center",
            "description": "CDP 브라우저를 셀러센터 지정 페이지로 이동합니다.",
            "params": {
                "page_key": {
                    "type": "string",
                    "enum": ["dashboard", "list", "register", "orders", "settlement", "reviews", "stats"],
                }
            },
        },
        {
            "name": "auto_register_product",
            "description": "CDP로 상품 등록 폼을 자동으로 채웁니다 (쓰기).",
            "params": {
                "name": {"type": "string"},
                "price": {"type": "integer"},
                "stock": {"type": "integer"},
                "category": {"type": "string"},
                "brand": {"type": "string"},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "description": {"type": "string"},
                "model_name": {"type": "string"},
                "origin": {"type": "string"},
            },
            "required": ["name", "price", "stock"],
        },
        {
            "name": "edit_product",
            "description": "CDP로 기존 상품을 수정합니다 (쓰기).",
            "params": {
                "product_id": {"type": "string"},
                "name": {"type": "string"},
                "price": {"type": "integer"},
                "stock": {"type": "integer"},
                "description": {"type": "string"},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "brand": {"type": "string"},
                "origin": {"type": "string"},
            },
            "required": ["product_id"],
        },
        {
            "name": "generate_description",
            "description": "GPT로 상품 상세설명 HTML을 생성합니다.",
            "params": {"data": {"type": "object"}, "model": {"type": "string", "enum": ["gpt"]}},
            "required": ["data"],
        },
        {
            "name": "search_categories",
            "description": "카테고리 이름·경로를 검색합니다.",
            "params": {"q": {"type": "string"}},
            "required": ["q"],
        },
        {"name": "popup_handle", "description": "CDP 브라우저 팝업을 자동으로 닫습니다.", "params": {}},
        {
            "name": "get_pending_reviews",
            "description": "미답변 리뷰 목록을 조회하고 Claude AI 답변 초안을 생성합니다.",
            "params": {"limit": {"type": "integer"}},
        },
        {
            "name": "reply_reviews",
            "description": "미답변 리뷰에 AI 초안으로 자동 답변을 저장합니다 (쓰기).",
            "params": {"limit": {"type": "integer"}},
        },
        {
            "name": "get_pending_orders",
            "description": "미발송(발송대기) 주문 목록을 조회합니다.",
            "params": {"limit": {"type": "integer"}},
        },
        {
            "name": "process_shipping",
            "description": "주문에 송장번호를 입력하고 발송처리합니다 (쓰기).",
            "params": {
                "order_id": {"type": "string"},
                "tracking_number": {"type": "string"},
                "carrier": {"type": "string"},
            },
            "required": ["order_id", "tracking_number"],
        },
        {
            "name": "delete_product",
            "description": "상품을 삭제합니다 (쓰기, 비가역).",
            "params": {
                "product_id": {"type": "string"},
                "product_ids": {"type": "array", "items": {"type": "string"}},
            },
        },
    ]


def _to_gpt_tools(confirmed: bool) -> list:
    result = []
    for t in _tool_defs():
        if not confirmed and t["name"] in WRITE_TOOLS:
            continue
        params: dict = {"type": "object", "properties": t["params"]}
        if "required" in t:
            params["required"] = t["required"]
        result.append(
            {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": params}}
        )
    return result


# ── 로컬 도구 실행 ─────────────────────────────────────────────────────────────


def _run_tool(name: str, inputs: dict, license_key: str | None = None, images: list | None = None) -> dict:
    """도구 실행 — CDP 도구는 로컬 에이전트로, 나머지는 서버 직접 처리."""
    sys.path.insert(0, str(ROOT))
    from ._helpers import load_ss

    images = images or []
    # 첨부 사진 → 등록/수정 도구의 이미지 필드로 주입 (LLM이 명시 안 해도 자동 사용)
    if images and name in ("auto_register_product", "edit_product"):
        inputs = {**inputs}
        inputs.setdefault("main_image", images[0])
        if len(images) > 1:
            inputs.setdefault("additional_images", images[1:])

    # ── 로컬 에이전트 라우팅 (CDP 도구) ────────────────────────────────────────
    if name in CDP_TOOLS and license_key:
        from .agent_ws import call_local_tool

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(call_local_tool(license_key, name, inputs))
        finally:
            loop.close()

    # ── 서버 직접 처리 (캐시 조회, AI 생성 등) ──────────────────────────────────
    # CDP 엔드포인트 — 라이선스 없이 서버가 직접 수집할 때 connect_over_cdp 대상.
    # (미정의 시 모든 collect_* 도구가 name 'cdp' is not defined 로 실패하던 버그 수정)
    cdp = "http://127.0.0.1:9222"
    try:
        if name == "list_products":
            return load_ss("products")
        if name == "list_orders":
            return load_ss("orders")
        if name == "list_settlements":
            return load_ss("settlements")
        if name == "list_reviews":
            return load_ss("reviews")
        if name == "list_stats":
            return load_ss("stats")

        if name == "collect_products":
            import time as _t

            from playwright.sync_api import sync_playwright

            from scripts.naver.smartstore import NaverSmartStore

            from ._helpers import elapsed_ms, now_iso, save_ss

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

            from ._helpers import elapsed_ms, now_iso, save_ss

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

            from ._helpers import elapsed_ms, now_iso, save_ss

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

            from ._helpers import elapsed_ms, now_iso, save_ss

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

            from ._helpers import elapsed_ms, now_iso, save_ss

            t0 = _t.monotonic()
            with sync_playwright() as pw:
                page = pw.chromium.connect_over_cdp(cdp).contexts[0].pages[0]
                result = NaverSmartStore(page).stats()
            result.update({"collected_at": now_iso(), "duration_ms": elapsed_ms(t0)})
            save_ss("stats", result)
            return result

        if name == "open_seller_center":
            from playwright.sync_api import sync_playwright

            from .seller_center import SELLER_CENTER_URLS

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
            data = inputs.get("data", {})
            # 사진 첨부 또는 model=gpt → GPT(이미지 지원). 그 외 Claude.
            if images or inputs.get("model") == "gpt":
                from scripts.naver.smartstore.product.gpt_description_writer import (
                    DEFAULT_MODEL as GPT_DEFAULT,
                )
                from scripts.naver.smartstore.product.gpt_description_writer import (
                    QUALITY_MODEL as GPT_QUALITY,
                )
                from scripts.naver.smartstore.product.gpt_description_writer import (
                    GptDescriptionWriter,
                )

                return GptDescriptionWriter(model=GPT_QUALITY if images else GPT_DEFAULT).generate(
                    data, images=images or None
                )

            from scripts.naver.smartstore.product.ai_description_writer import (
                DEFAULT_MODEL,
                QUALITY_MODEL,
                AIDescriptionWriter,
            )

            return AIDescriptionWriter(
                model=QUALITY_MODEL if inputs.get("model") == "quality" else DEFAULT_MODEL
            ).generate(data)

        if name == "search_categories":
            from scripts.naver.smartstore.product.category_cache import load_cache

            cats = load_cache()
            q = str(inputs.get("q", "")).lower()
            matches = [c for c in cats if q in c.get("name", "").lower() or q in c.get("path", "").lower()]
            return {"ok": True, "count": len(matches), "results": matches[:20]}

        if name == "popup_handle":
            from playwright.sync_api import sync_playwright

            from scripts.naver.smartstore.navigation.cdp_popup_manager import CdpPopupManager

            with sync_playwright() as pw:
                ctx = pw.chromium.connect_over_cdp(cdp).contexts[0]
                page = ctx.pages[0]
                mgr = CdpPopupManager()
                mgr.unblock(ctx, origin="https://sell.smartstore.naver.com")
                return mgr.handle_page(page, auto_confirm=True)

        if name == "get_pending_reviews":
            from playwright.sync_api import sync_playwright

            from scripts.naver.smartstore.product.review_reply import ReviewAutoResponder

            with sync_playwright() as pw:
                page = pw.chromium.connect_over_cdp(cdp).contexts[0].pages[0]
                result = ReviewAutoResponder(page).get_pending(limit=inputs.get("limit", 20))
            if result.get("ok") and result.get("pending"):
                from scripts.naver.smartstore.product.review_reply import ReviewAutoResponder as _RA

                result["pending"] = _RA(None).generate_replies(result["pending"])
            return result

        if name == "reply_reviews":
            from playwright.sync_api import sync_playwright

            from scripts.naver.smartstore.product.review_reply import ReviewAutoResponder

            with sync_playwright() as pw:
                page = pw.chromium.connect_over_cdp(cdp).contexts[0].pages[0]
                return ReviewAutoResponder(page).reply_pending(limit=inputs.get("limit", 10), confirmed=True)

        if name == "get_pending_orders":
            from playwright.sync_api import sync_playwright

            from scripts.naver.smartstore.product.order_shipping import OrderShippingProcessor

            with sync_playwright() as pw:
                page = pw.chromium.connect_over_cdp(cdp).contexts[0].pages[0]
                return OrderShippingProcessor(page).get_pending_orders(limit=inputs.get("limit", 50))

        if name == "process_shipping":
            from playwright.sync_api import sync_playwright

            from scripts.naver.smartstore.product.order_shipping import OrderShippingProcessor

            with sync_playwright() as pw:
                page = pw.chromium.connect_over_cdp(cdp).contexts[0].pages[0]
                return OrderShippingProcessor(page).process_order(
                    order_id=inputs["order_id"],
                    tracking_number=inputs["tracking_number"],
                    carrier=inputs.get("carrier", "CJ대한통운"),
                    confirmed=True,
                )

        if name == "delete_product":
            from playwright.sync_api import sync_playwright

            from scripts.naver.smartstore.product.product_delete import ProductDeleter

            with sync_playwright() as pw:
                page = pw.chromium.connect_over_cdp(cdp).contexts[0].pages[0]
                deleter = ProductDeleter(page)
                if inputs.get("product_ids"):
                    return deleter.delete_bulk(inputs["product_ids"], confirmed=True)
                return deleter.delete(inputs["product_id"], confirmed=True)

        return {"ok": False, "error": f"알 수 없는 도구: {name}"}

    except Exception as e:
        return {"ok": False, "error": str(e), "hint": "CDP 브라우저가 실행 중인지 확인하세요"}


# ── SSE 헬퍼 ─────────────────────────────────────────────────────────────────


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── Claude 루프 ───────────────────────────────────────────────────────────────


# ── GPT 루프 ─────────────────────────────────────────────────────────────────


def _run_gpt(messages: list, confirmed: bool, license_key: str | None = None, images: list | None = None):
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        yield _sse("error", {"message": "OPENAI_API_KEY 미설정 — .env에 추가하세요"})
        return

    client = OpenAI(api_key=api_key)
    tools = _to_gpt_tools(confirmed)
    history = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
    step = 0

    while True:
        res = client.chat.completions.create(
            model=GPT_MODEL,
            max_tokens=2048,
            tools=tools,
            tool_choice="auto",
            messages=history,
        )
        msg = res.choices[0].message
        if msg.content:
            yield _sse("text", {"text": msg.content})
        if not msg.tool_calls:
            break

        tool_results = []
        for tc in msg.tool_calls:
            name = tc.function.name
            inputs = json.loads(tc.function.arguments or "{}")
            is_write = name in WRITE_TOOLS
            if is_write and not confirmed:
                yield _sse(
                    "confirm_required",
                    {
                        "tool": name,
                        "inputs": inputs,
                        "message": f"'{inputs.get('name', name)}' 작업에 승인이 필요합니다.",
                    },
                )
                return
            step += 1
            yield _sse("step_start", {"step": step, "tool": name, "inputs": inputs, "write": is_write})
            result = _run_tool(name, inputs, license_key, images)
            yield _sse("step_done", {"step": step, "tool": name, "ok": result.get("ok") is not False, "result": result})
            tool_results.append(
                {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, ensure_ascii=False)}
            )

        history.append(msg)
        history.extend(tool_results)

    yield _sse("done", {"steps": step})


# ── Request 모델 ──────────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    confirmed: bool = False
    provider: str = "gpt"  # "claude" | "gpt"
    license_key: str | None = None  # 로컬 에이전트 라우팅용
    images: list[str] = []  # 채팅 첨부 사진(로컬 경로) — 상세설명 생성·상품 등록에 사용


# ── 엔드포인트 ────────────────────────────────────────────────────────────────


@router.post("/chat")
def api_chat(body: ChatRequest, user: dict = Depends(require_role("admin", "owner"))):
    """자연어 명령 → LLM tool_use → 도구 실행(CDP=로컬, 나머지=서버) → SSE."""
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    images = body.images or []

    # 첨부 사진이 있으면 LLM이 인지하도록 마지막 user 메시지에 힌트 추가
    if images:
        note = (
            f"\n\n[첨부 사진 {len(images)}장이 있습니다. "
            "상세설명 생성(generate_description)이나 상품 등록(auto_register_product) 시 "
            "이 사진을 자동으로 사용합니다.]"
        )
        for m in reversed(messages):
            if m["role"] == "user":
                m["content"] += note
                break

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
            runner = _run_gpt  # 앱 표준=GPT (Claude 경로 제거)
            yield from runner(messages, body.confirmed, lic_key, images)
        except Exception as e:
            yield _sse("error", {"message": str(e)})

    log_event(
        "SMARTSTORE_CHAT",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"provider={body.provider} msgs={len(messages)}",
    )

    return StreamingResponse(
        generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/images/upload")
async def api_upload_images(
    files: list[UploadFile] = File(...),
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """웹 브라우저에서 첨부한 이미지를 서버 임시 디렉터리에 저장 후 경로 반환.

    SmartStoreChat에서 Electron 없이 웹 HTML 파일선택으로 이미지를 첨부할 때 사용.
    반환된 경로를 /chat 엔드포인트의 images[] 필드에 전달하면 GPT-4V가 분석한다.
    """
    _TEMP_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for f in files:
        ext = Path(f.filename or "img").suffix or ".jpg"
        dest = _TEMP_IMAGE_DIR / f"{uuid.uuid4().hex}{ext}"
        dest.write_bytes(await f.read())
        saved.append(str(dest))
    log_event(
        "SMARTSTORE_IMAGE_UPLOAD",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"count={len(saved)}",
    )
    return {"ok": True, "paths": saved}
