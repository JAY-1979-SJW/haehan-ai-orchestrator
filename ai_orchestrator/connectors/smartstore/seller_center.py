"""셀러센터 CDP 페이지 이동 엔드포인트."""
from __future__ import annotations
from fastapi import APIRouter, Depends
from ...auth import require_role
from ...audit_logger import log_event

router = APIRouter()
_CDP = "http://127.0.0.1:9222"

SELLER_CENTER_URLS: dict[str, str] = {
    "register":   "https://sell.smartstore.naver.com/#/products/new",
    "list":       "https://sell.smartstore.naver.com/#/products/list",
    "dashboard":  "https://sell.smartstore.naver.com/#/home/dashboard",
    "orders":     "https://sell.smartstore.naver.com/#/order/list",
    "settlement": "https://sell.smartstore.naver.com/#/settlement/main",
    "reviews":    "https://sell.smartstore.naver.com/#/review/list",
    "stats":      "https://sell.smartstore.naver.com/#/analytics/dashboard",
}


@router.post("/open")
def api_open_seller_center(page_key: str = "dashboard",
                            user: dict = Depends(require_role("admin", "owner"))) -> dict:
    url = SELLER_CENTER_URLS.get(page_key)
    if not url:
        return {"ok": False, "error": f"알 수 없는 page_key: {page_key}",
                "available": list(SELLER_CENTER_URLS.keys())}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            page = pw.chromium.connect_over_cdp(_CDP).contexts[0].pages[0]
            page.bring_to_front()
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
    except Exception as e:
        return {"ok": False, "error": str(e), "hint": "CDP 브라우저가 실행 중인지 확인하세요"}
    log_event("SMARTSTORE_OPEN", task_id="-", actor=user["actor"], role=user["role"],
              decision="ok", note=f"page_key={page_key}")
    return {"ok": True, "page_key": page_key, "url": url,
            "message": f"CDP 브라우저가 {page_key} 페이지로 이동했습니다."}
