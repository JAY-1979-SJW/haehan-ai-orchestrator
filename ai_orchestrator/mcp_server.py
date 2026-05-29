"""해한 AI 오케스트레이터 MCP 서버 (stdio transport).

Claude Code에서 다음 도구를 직접 호출할 수 있게 합니다:
  - generate_description   : Claude/GPT로 상품 상세설명 HTML 생성
  - save_template          : 상세설명 템플릿 저장
  - list_templates         : 저장된 템플릿 목록 조회
  - get_template           : 템플릿 상세(HTML 포함) 조회
  - delete_template        : 템플릿 삭제
  - list_products          : 스마트스토어 상품 목록 조회 (캐시)
  - render_description     : 섹션 빌더로 HTML 렌더링

실행 (Claude Code가 자동으로 기동):
    python -m ai_orchestrator.mcp_server
"""
from __future__ import annotations

import json
import os
import sys
import datetime
import re
from pathlib import Path
from typing import Any

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# .env 로드
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

app = Server("haehan-ai-orchestrator")

# ── 템플릿 저장소 ─────────────────────────────────────────────────────────────
TMPL_DIR = ROOT / "data" / "smartstore" / "desc_templates"


def _tmpl_dir() -> Path:
    TMPL_DIR.mkdir(parents=True, exist_ok=True)
    return TMPL_DIR


# ── 도구 목록 ─────────────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="generate_description",
            description=(
                "상품 데이터(JSON)를 받아 Claude 또는 GPT로 고품질 상세설명 HTML을 생성합니다. "
                "model='claude'(기본) 또는 model='gpt'를 지정할 수 있습니다."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "product": {
                        "type": "object",
                        "description": "상품 데이터 (name, price, stock, category 필수)",
                    },
                    "model": {
                        "type": "string",
                        "enum": ["claude", "gpt", "builder"],
                        "description": "생성 모델 선택 (기본: claude)",
                        "default": "claude",
                    },
                    "sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "포함할 섹션 목록 (생략 시 전체)",
                    },
                },
                "required": ["product"],
            },
        ),
        types.Tool(
            name="save_template",
            description="생성된 상세설명 HTML을 템플릿으로 저장합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name":     {"type": "string",  "description": "템플릿 이름 (예: 무드등_감성표준)"},
                    "category": {"type": "string",  "description": "제품군 (예: 조명)"},
                    "sections": {"type": "array",   "items": {"type": "string"}},
                    "data":     {"type": "object",  "description": "상품 샘플 데이터"},
                    "html":     {"type": "string",  "description": "렌더링된 HTML"},
                    "source":   {"type": "string",  "description": "생성 방식 (claude/gpt/builder)"},
                },
                "required": ["name", "html"],
            },
        ),
        types.Tool(
            name="list_templates",
            description="저장된 상세설명 템플릿 목록을 반환합니다.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="get_template",
            description="특정 템플릿의 상세 정보(HTML 포함)를 반환합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "템플릿 ID"},
                },
                "required": ["id"],
            },
        ),
        types.Tool(
            name="delete_template",
            description="템플릿을 삭제합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "삭제할 템플릿 ID"},
                },
                "required": ["id"],
            },
        ),
        types.Tool(
            name="render_description",
            description="섹션 빌더로 상품 상세설명 HTML을 렌더링합니다 (API 키 불필요).",
            inputSchema={
                "type": "object",
                "properties": {
                    "product":  {"type": "object", "description": "상품 데이터"},
                    "sections": {"type": "array",  "items": {"type": "string"},
                                 "description": "포함할 섹션 목록"},
                },
                "required": ["product"],
            },
        ),
        types.Tool(
            name="list_products",
            description="스마트스토어 상품 목록을 캐시에서 조회합니다.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="collect_products",
            description="CDP 브라우저로 스마트스토어 상품 목록을 실시간 수집하고 캐시에 저장합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "수집 최대 개수 (기본 50)", "default": 50},
                },
            },
        ),
        types.Tool(
            name="list_orders",
            description="스마트스토어 주문 목록을 캐시에서 조회합니다.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="collect_orders",
            description="CDP 브라우저로 스마트스토어 주문 목록을 실시간 수집하고 캐시에 저장합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "수집 최대 개수 (기본 50)", "default": 50},
                },
            },
        ),
        types.Tool(
            name="list_settlements",
            description="스마트스토어 정산 내역을 캐시에서 조회합니다.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="collect_settlements",
            description="CDP 브라우저로 스마트스토어 정산 내역을 실시간 수집하고 캐시에 저장합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "수집 최대 개수 (기본 30)", "default": 30},
                },
            },
        ),
        types.Tool(
            name="list_reviews",
            description="스마트스토어 리뷰/문의 목록을 캐시에서 조회합니다.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="collect_reviews",
            description="CDP 브라우저로 스마트스토어 리뷰/문의 목록을 실시간 수집하고 캐시에 저장합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "수집 최대 개수 (기본 30)", "default": 30},
                },
            },
        ),
        types.Tool(
            name="list_stats",
            description="스마트스토어 데이터 분석(통계) 캐시를 조회합니다.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="collect_stats",
            description="CDP 브라우저로 스마트스토어 데이터 분석(통계)을 실시간 수집하고 캐시에 저장합니다.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="open_seller_center",
            description="CDP 브라우저를 셀러센터 지정 페이지로 이동합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_key": {
                        "type": "string",
                        "enum": ["dashboard", "list", "register", "orders", "settlement", "reviews", "stats"],
                        "description": "이동할 페이지 키 (기본: dashboard)",
                        "default": "dashboard",
                    },
                },
            },
        ),
        types.Tool(
            name="auto_register_product",
            description=(
                "CDP 브라우저로 셀러센터 상품 등록 폼을 자동으로 채웁니다. "
                "임시저장까지만 진행하며 최종 저장은 사용자가 직접 합니다."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name":        {"type": "string",  "description": "상품명"},
                    "price":       {"type": "integer", "description": "판매가 (원)"},
                    "stock":       {"type": "integer", "description": "재고 수량"},
                    "category":    {"type": "string",  "description": "카테고리 경로 (예: 생활/주방 > 조명 > 무드등)"},
                    "brand":       {"type": "string",  "description": "브랜드명"},
                    "keywords":    {"type": "array",   "items": {"type": "string"}, "description": "검색 키워드"},
                    "description": {"type": "string",  "description": "상세설명 HTML"},
                    "model_name":  {"type": "string",  "description": "모델명"},
                    "origin":      {"type": "string",  "description": "원산지"},
                },
                "required": ["name", "price", "stock"],
            },
        ),
        types.Tool(
            name="edit_product",
            description=(
                "CDP 브라우저로 기존 상품을 수정합니다. "
                "임시저장까지만 진행하며 최종 저장은 사용자가 직접 합니다."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string",  "description": "수정할 상품번호"},
                    "name":       {"type": "string",  "description": "변경할 상품명"},
                    "price":      {"type": "integer", "description": "변경할 판매가 (원)"},
                    "stock":      {"type": "integer", "description": "변경할 재고 수량"},
                    "description": {"type": "string", "description": "변경할 상세설명 HTML"},
                    "keywords":   {"type": "array",   "items": {"type": "string"}, "description": "변경할 검색 키워드"},
                    "brand":      {"type": "string",  "description": "변경할 브랜드명"},
                    "origin":     {"type": "string",  "description": "변경할 원산지"},
                },
                "required": ["product_id"],
            },
        ),
    ]


# ── 도구 실행 ─────────────────────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:

    if name == "generate_description":
        result = await _generate_description(arguments)

    elif name == "save_template":
        result = _save_template(arguments)

    elif name == "list_templates":
        result = _list_templates()

    elif name == "get_template":
        result = _get_template(arguments["id"])

    elif name == "delete_template":
        result = _delete_template(arguments["id"])

    elif name == "render_description":
        result = _render_description(arguments)

    elif name == "list_products":
        result = _list_products()

    elif name == "collect_products":
        result = _cdp_collect("products", arguments)

    elif name == "list_orders":
        result = _load_ss_data("orders")

    elif name == "collect_orders":
        result = _cdp_collect("orders", arguments)

    elif name == "list_settlements":
        result = _load_ss_data("settlements")

    elif name == "collect_settlements":
        result = _cdp_collect("settlements", arguments)

    elif name == "list_reviews":
        result = _load_ss_data("reviews")

    elif name == "collect_reviews":
        result = _cdp_collect("reviews", arguments)

    elif name == "list_stats":
        result = _load_ss_data("stats")

    elif name == "collect_stats":
        result = _cdp_collect("stats", arguments)

    elif name == "open_seller_center":
        result = _open_seller_center(arguments)

    elif name == "auto_register_product":
        result = _auto_register_product(arguments)

    elif name == "edit_product":
        result = _edit_product(arguments)

    else:
        result = {"ok": False, "error": f"알 수 없는 도구: {name}"}

    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


# ── 구현 ──────────────────────────────────────────────────────────────────────

async def _generate_description(args: dict) -> dict:
    product  = args.get("product", {})
    model    = args.get("model", "claude")
    sections = args.get("sections")

    # Claude
    if model in ("claude", "auto"):
        try:
            from scripts.naver.smartstore.product.ai_description_writer import (
                AIDescriptionWriter, QUALITY_MODEL,
            )
            w = AIDescriptionWriter(model=QUALITY_MODEL)
            r = w.generate(product)
            if r.get("ok") and r.get("html"):
                return {"ok": True, "html": r["html"], "source": "claude",
                        "model": QUALITY_MODEL, "chars": len(r["html"])}
            if model == "claude":
                return {"ok": False, "error": r.get("error", "Claude 생성 실패"),
                        "hint": "ANTHROPIC_API_KEY를 .env에 추가하세요"}
        except Exception as e:
            if model == "claude":
                return {"ok": False, "error": str(e)}

    # GPT
    if model in ("gpt", "auto"):
        try:
            from scripts.naver.smartstore.product.gpt_description_writer import GptDescriptionWriter
            w = GptDescriptionWriter()
            r = w.generate(product)
            if r.get("ok") and r.get("html"):
                return {"ok": True, "html": r["html"], "source": "gpt",
                        "chars": len(r["html"])}
            return {"ok": False, "error": r.get("error") or str(r.get("errors", "GPT 실패"))}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # 섹션 빌더 fallback
    return _render_description({"product": product, "sections": sections})


def _render_description(args: dict) -> dict:
    product  = args.get("product", {})
    sections = args.get("sections")
    try:
        from scripts.naver.smartstore.product.page_builder import ProductPageBuilder, DEFAULT_SECTIONS
        b = ProductPageBuilder()
        b.select(sections or DEFAULT_SECTIONS)
        html = b.render(product)
        return {"ok": True, "html": html, "source": "builder", "chars": len(html)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _save_template(args: dict) -> dict:
    d    = _tmpl_dir()
    name = args.get("name", "unnamed")
    safe = re.sub(r"[^\w가-힣]", "_", name)[:40]
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tid  = f"{safe}_{ts}"
    payload = {
        "id":         tid,
        "name":       name,
        "category":   args.get("category", ""),
        "sections":   args.get("sections", []),
        "data":       args.get("data", {}),
        "html":       args.get("html", ""),
        "source":     args.get("source", "manual"),
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "created_by": "claude_code_mcp",
    }
    (d / f"{tid}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"ok": True, "id": tid, "name": name}


def _list_templates() -> dict:
    d = _tmpl_dir()
    templates = []
    for f in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
            templates.append({
                "id":         f.stem,
                "name":       t.get("name", f.stem),
                "category":   t.get("category", ""),
                "source":     t.get("source", ""),
                "created_at": t.get("created_at", ""),
                "chars":      len(t.get("html", "")),
                "sections":   t.get("sections", []),
            })
        except Exception:
            pass
    return {"ok": True, "templates": templates, "count": len(templates)}


def _get_template(tid: str) -> dict:
    f = _tmpl_dir() / f"{tid}.json"
    if not f.exists():
        return {"ok": False, "error": "template_not_found"}
    try:
        return {"ok": True, **json.loads(f.read_text(encoding="utf-8"))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _delete_template(tid: str) -> dict:
    f = _tmpl_dir() / f"{tid}.json"
    if not f.exists():
        return {"ok": False, "error": "template_not_found"}
    f.unlink()
    return {"ok": True, "id": tid}


def _list_products() -> dict:
    return _load_ss_data("products")


# ── 공통 캐시 로더 ────────────────────────────────────────────────────────────

SS_DATA_DIR = ROOT / "data" / "smartstore"

_SS_COLLECT_METHODS = {
    "products":    ("list_products",    50),
    "orders":      ("list_orders",      50),
    "settlements": ("list_settlements", 30),
    "reviews":     ("list_reviews",     30),
    "stats":       ("stats",            None),
}


def _load_ss_data(name: str) -> dict:
    p = SS_DATA_DIR / f"{name}.json"
    if not p.exists():
        return {"ok": False, "error": "no_data",
                "hint": f"collect_{name} 도구를 먼저 실행하세요"}
    try:
        import json as _j
        data = _j.loads(p.read_text(encoding="utf-8"))
        if not data.get("ok") and data.get("error") in (
            "section_open_failed", "CDP_ERROR", "playwright_error"
        ):
            return {"ok": False, "error": "no_data",
                    "hint": f"이전 수집이 실패했습니다. collect_{name} 재실행 필요",
                    "last_error": data.get("error")}
        return data
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _save_ss_data(name: str, data: dict) -> None:
    SS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    import json as _j
    (SS_DATA_DIR / f"{name}.json").write_text(
        _j.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _cdp_collect(name: str, args: dict) -> dict:
    """CDP 브라우저로 지정 데이터를 수집해 캐시에 저장합니다."""
    import time as _t
    method_name, default_limit = _SS_COLLECT_METHODS.get(name, (None, None))
    if not method_name:
        return {"ok": False, "error": f"알 수 없는 수집 대상: {name}"}

    limit = args.get("limit", default_limit)
    t0 = _t.monotonic()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page = browser.contexts[0].pages[0]
            from scripts.naver.smartstore import NaverSmartStore
            ss = NaverSmartStore(page)
            method = getattr(ss, method_name)
            result = method(limit=limit) if limit is not None else method()
    except Exception as e:
        result = {"ok": False, "error": str(e),
                  "hint": "CDP 브라우저가 실행 중인지 확인하세요 (cdp_force_start.py start)"}

    result["collected_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    result["duration_ms"] = int((_t.monotonic() - t0) * 1000)
    if result.get("ok"):
        _save_ss_data(name, result)
    return result


# ── 셀러센터 페이지 열기 ──────────────────────────────────────────────────────

_SELLER_CENTER_URLS = {
    "register":   "https://sell.smartstore.naver.com/#/products/new",
    "list":       "https://sell.smartstore.naver.com/#/products/list",
    "dashboard":  "https://sell.smartstore.naver.com/#/home/dashboard",
    "orders":     "https://sell.smartstore.naver.com/#/order/list",
    "settlement": "https://sell.smartstore.naver.com/#/settlement/main",
    "reviews":    "https://sell.smartstore.naver.com/#/review/list",
    "stats":      "https://sell.smartstore.naver.com/#/analytics/dashboard",
}


def _open_seller_center(args: dict) -> dict:
    page_key = args.get("page_key", "dashboard")
    url = _SELLER_CENTER_URLS.get(page_key)
    if not url:
        return {"ok": False, "error": f"알 수 없는 page_key: {page_key}",
                "available": list(_SELLER_CENTER_URLS.keys())}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page = browser.contexts[0].pages[0]
            page.bring_to_front()
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
    except Exception as e:
        return {"ok": False, "error": str(e),
                "hint": "CDP 브라우저가 실행 중인지 확인하세요 (cdp_force_start.py start)"}
    return {"ok": True, "page_key": page_key, "url": url}


# ── 상품 등록 / 수정 ──────────────────────────────────────────────────────────

def _auto_register_product(args: dict) -> dict:
    """CDP 브라우저로 상품 등록 폼을 자동 채웁니다 (임시저장까지)."""
    import time as _t
    register_data = dict(args)
    register_data["save"] = False
    register_data["require_confirm"] = False

    REGISTER_URL = "https://sell.smartstore.naver.com/#/products/create"
    t0 = _t.monotonic()
    try:
        from playwright.sync_api import sync_playwright
        from scripts.naver.smartstore.product.form_runner import ProductFormRunner
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            ctx = browser.contexts[0]
            page = next(
                (p for p in ctx.pages if "products/create" in p.url or "products/register" in p.url),
                None,
            )
            skip = False
            if page is None:
                page = ctx.new_page()
                page.goto(REGISTER_URL, timeout=20000, wait_until="domcontentloaded")
                skip = True
            page.bring_to_front()
            runner = ProductFormRunner(page)
            result = runner.run(register_data, skip_open=skip)
    except Exception as e:
        return {"ok": False, "error": str(e),
                "hint": "CDP 브라우저가 실행 중인지 확인하세요 (cdp_force_start.py start)"}

    result["duration_ms"] = int((_t.monotonic() - t0) * 1000)
    result["dry_run"] = True
    return result


def _edit_product(args: dict) -> dict:
    """CDP 브라우저로 기존 상품을 수정합니다 (임시저장까지)."""
    import time as _t
    product_id = args.get("product_id")
    if not product_id:
        return {"ok": False, "error": "product_id 필수"}

    edit_fields = {k: v for k, v in args.items() if k != "product_id"}
    edit_fields["save"] = False

    t0 = _t.monotonic()
    try:
        from playwright.sync_api import sync_playwright
        from scripts.naver.smartstore.product.form_runner import ProductFormRunner
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            ctx = browser.contexts[0]
            page = next(
                (p for p in ctx.pages if f"products/{product_id}" in p.url),
                None,
            )
            if page is None:
                page = ctx.new_page()
            page.bring_to_front()
            runner = ProductFormRunner(page)
            result = runner.edit(product_id, edit_fields)
    except Exception as e:
        return {"ok": False, "error": str(e),
                "hint": "CDP 브라우저가 실행 중인지 확인하세요 (cdp_force_start.py start)"}

    result["duration_ms"] = int((_t.monotonic() - t0) * 1000)
    result["dry_run"] = True
    return result


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> None:
    import asyncio
    asyncio.run(mcp.server.stdio.stdio_server(app))


if __name__ == "__main__":
    main()
