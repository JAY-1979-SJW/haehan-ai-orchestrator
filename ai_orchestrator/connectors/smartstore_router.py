"""스마트스토어 셀러센터 read-only API 엔드포인트."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends

from ..auth import require_role
from ..audit_logger import log_event

logger = logging.getLogger(__name__)

smartstore_router = APIRouter(prefix="/smartstore", tags=["smartstore"])

# ── 상품 등록 필드 정의 (scripts/naver/smartstore/product/models.py 미존재 시 내장) ──
REQUIRED_FIELDS = ["name", "price", "stock", "category"]
OPTIONAL_FIELDS = ["description", "brand", "manufacturer", "main_image", "model_name"]


@smartstore_router.get("/status")
def api_status(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """스마트스토어 액션 카탈로그 + DB 상태."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.naver.smartstore.api.actions import load_action_catalog, build_action_catalog
    catalog_path = Path(__file__).resolve().parents[2] / "data" / "smartstore_action_catalog_latest.json"
    try:
        catalog = load_action_catalog(catalog_path) if catalog_path.exists() else build_action_catalog()
    except Exception:
        catalog = build_action_catalog()
    log_event("SMARTSTORE_STATUS_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return {"catalog": catalog, "db_path": str(catalog_path.name)}


@smartstore_router.get("/submit-history")
def api_submit_history(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """최근 제출 이력."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    data_dir = Path(__file__).resolve().parents[2] / "data"
    submit_path = data_dir / "smartstore_submit_latest.json"
    submits_dir = data_dir / "smartstore_submits"
    history = []
    if submits_dir.exists():
        for f in sorted(submits_dir.glob("*.json"), reverse=True)[:20]:
            try:
                history.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
    latest: dict = {}
    if submit_path.exists():
        try:
            latest = json.loads(submit_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    log_event(
        "SMARTSTORE_HISTORY_READ",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"count={len(history)}",
    )
    return {"latest": latest, "history": history, "count": len(history)}


@smartstore_router.get("/menu-map")
def api_menu_map(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """13개 메뉴 구조 + 각 기능 목록."""
    log_event("SMARTSTORE_MENU_MAP_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return {
        "menus": [
            {"key": "products",   "label": "상품관리",     "features": ["상품 목록", "상품 등록", "상품 수정", "카탈로그 가격관리", "배송정보 관리"]},
            {"key": "orders",     "label": "판매관리",     "features": ["주문 목록", "발송 처리", "반품/교환"]},
            {"key": "settlement", "label": "정산관리",     "features": ["정산 내역", "세금계산서"]},
            {"key": "reviews",    "label": "문의/리뷰관리", "features": ["고객 리뷰", "고객 문의", "리뷰 자동응답"]},
            {"key": "store",      "label": "스토어관리",   "features": ["스토어 정보", "공지사항", "구독 관리"]},
            {"key": "marketing",  "label": "혜택/마케팅",  "features": ["쿠폰", "할인", "포인트"]},
            {"key": "delivery",   "label": "N배송 관리",   "features": ["배송 현황", "반품 처리"]},
            {"key": "solution",   "label": "커머스솔루션", "features": ["솔루션 현황"]},
            {"key": "stats",      "label": "데이터분석",   "features": ["매출 통계", "방문 통계", "상품 분석"]},
            {"key": "ads",        "label": "광고관리",     "features": ["광고 현황"], "locked": True},
            {"key": "promo",      "label": "프로모션 관리", "features": ["프로모션 목록"]},
            {"key": "connect",    "label": "쇼핑 커넥트",  "features": ["채널 연결"]},
            {"key": "seller",     "label": "판매자 정보",  "features": ["사업자 정보", "정책 관리"]},
        ]
    }


@smartstore_router.get("/product-register-guide")
def api_register_guide(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """상품 등록 5단계 가이드 + 필드 정의."""
    log_event("SMARTSTORE_REGISTER_GUIDE_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return {
        "steps": [
            {"step": 1, "title": "카테고리 선택", "desc": "생활/건강 > 조명 > 무드등/취침등", "required": True},
            {"step": 2, "title": "기본 정보",     "desc": "상품명, 판매가, 재고 입력", "required": True},
            {"step": 3, "title": "이미지 등록",   "desc": "대표이미지(필수), 추가이미지(선택)", "required": True},
            {"step": 4, "title": "상세 설명",     "desc": "스마트에디터 또는 HTML 작성", "required": False},
            {"step": 5, "title": "저장",          "desc": "임시저장 → 최종 저장(노출설정)", "required": True},
        ],
        "required_fields": ["name", "price", "stock", "category"],
        "optional_fields": ["description", "brand", "manufacturer", "main_image", "model_name", "options"],
        "limits": {
            "name_max": 100,
            "price_min": 10,
            "stock_max": 9999999,
            "image_max_mb": 10,
        },
        "approval_token": "SMARTSTORE_APPROVED_SUBMIT",
    }


@smartstore_router.get("/product-form-fields")
def api_product_form_fields(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """상품 등록 폼 필드 정의."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    required = REQUIRED_FIELDS
    optional = OPTIONAL_FIELDS
    try:
        from scripts.naver.smartstore.product.models import REQUIRED_FIELDS as RF, OPTIONAL_FIELDS as OF
        required = RF
        optional = OF
    except ImportError:
        pass
    log_event("SMARTSTORE_FORM_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return {"required": required, "optional": optional}


import time as _time

ROOT = Path(__file__).resolve().parents[2]
_SS_DATA_DIR = ROOT / "data" / "smartstore"


def _ss_data(name: str) -> Path:
    _SS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _SS_DATA_DIR / f"{name}.json"


def _load_ss(name: str) -> dict:
    p = _ss_data(name)
    if not p.exists():
        return {"ok": False, "error": "no_data", "hint": f"POST /smartstore/{name.replace('_','-')}/collect 먼저 실행"}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _save_ss(name: str, data: dict) -> None:
    _ss_data(name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 상품 목록 ────────────────────────────────────────────────────────────────

@smartstore_router.get("/products")
def api_products(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """저장된 상품 목록 반환."""
    log_event("SMARTSTORE_PRODUCTS_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return _load_ss("products")

@smartstore_router.post("/products/collect")
def api_products_collect(limit: int = 50, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """CDP로 상품 목록 수집 → 저장."""
    import sys; sys.path.insert(0, str(ROOT))
    t0 = _time.monotonic()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page = browser.contexts[0].pages[0]
            from scripts.naver.smartstore import NaverSmartStore
            ss = NaverSmartStore(page)
            result = ss.list_products(limit=limit)
    except Exception as e:
        result = {"ok": False, "error": str(e)}
    result["collected_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    result["duration_ms"] = int((_time.monotonic() - t0) * 1000)
    _save_ss("products", result)
    log_event("SMARTSTORE_PRODUCTS_COLLECT", task_id="-", actor=user["actor"], role=user["role"],
              decision="ok" if result.get("ok") else "error", note=f"rows={len(result.get('rows', []))}")
    return result


# ── 주문 목록 ────────────────────────────────────────────────────────────────

@smartstore_router.get("/orders")
def api_orders(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    log_event("SMARTSTORE_ORDERS_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return _load_ss("orders")

@smartstore_router.post("/orders/collect")
def api_orders_collect(limit: int = 50, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    import sys; sys.path.insert(0, str(ROOT))
    t0 = _time.monotonic()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page = browser.contexts[0].pages[0]
            from scripts.naver.smartstore import NaverSmartStore
            ss = NaverSmartStore(page)
            result = ss.list_orders(limit=limit)
    except Exception as e:
        result = {"ok": False, "error": str(e)}
    result["collected_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    result["duration_ms"] = int((_time.monotonic() - t0) * 1000)
    _save_ss("orders", result)
    log_event("SMARTSTORE_ORDERS_COLLECT", task_id="-", actor=user["actor"], role=user["role"],
              decision="ok" if result.get("ok") else "error", note="")
    return result


# ── 정산 내역 ────────────────────────────────────────────────────────────────

@smartstore_router.get("/settlements")
def api_settlements(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    log_event("SMARTSTORE_SETTLEMENTS_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return _load_ss("settlements")

@smartstore_router.post("/settlements/collect")
def api_settlements_collect(limit: int = 30, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    import sys; sys.path.insert(0, str(ROOT))
    t0 = _time.monotonic()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page = browser.contexts[0].pages[0]
            from scripts.naver.smartstore import NaverSmartStore
            ss = NaverSmartStore(page)
            result = ss.list_settlements(limit=limit)
    except Exception as e:
        result = {"ok": False, "error": str(e)}
    result["collected_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    result["duration_ms"] = int((_time.monotonic() - t0) * 1000)
    _save_ss("settlements", result)
    log_event("SMARTSTORE_SETTLEMENTS_COLLECT", task_id="-", actor=user["actor"], role=user["role"],
              decision="ok" if result.get("ok") else "error", note="")
    return result


# ── 리뷰/문의 ────────────────────────────────────────────────────────────────

@smartstore_router.get("/reviews")
def api_reviews(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    log_event("SMARTSTORE_REVIEWS_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return _load_ss("reviews")

@smartstore_router.post("/reviews/collect")
def api_reviews_collect(limit: int = 30, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    import sys; sys.path.insert(0, str(ROOT))
    t0 = _time.monotonic()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page = browser.contexts[0].pages[0]
            from scripts.naver.smartstore import NaverSmartStore
            ss = NaverSmartStore(page)
            result = ss.list_reviews(limit=limit)
    except Exception as e:
        result = {"ok": False, "error": str(e)}
    result["collected_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    result["duration_ms"] = int((_time.monotonic() - t0) * 1000)
    _save_ss("reviews", result)
    log_event("SMARTSTORE_REVIEWS_COLLECT", task_id="-", actor=user["actor"], role=user["role"],
              decision="ok" if result.get("ok") else "error", note="")
    return result


# ── 통계 ─────────────────────────────────────────────────────────────────────

@smartstore_router.get("/stats")
def api_stats(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    log_event("SMARTSTORE_STATS_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return _load_ss("stats")

@smartstore_router.post("/stats/collect")
def api_stats_collect(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    import sys; sys.path.insert(0, str(ROOT))
    t0 = _time.monotonic()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page = browser.contexts[0].pages[0]
            from scripts.naver.smartstore import NaverSmartStore
            ss = NaverSmartStore(page)
            result = ss.stats()
    except Exception as e:
        result = {"ok": False, "error": str(e)}
    result["collected_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    result["duration_ms"] = int((_time.monotonic() - t0) * 1000)
    _save_ss("stats", result)
    log_event("SMARTSTORE_STATS_COLLECT", task_id="-", actor=user["actor"], role=user["role"],
              decision="ok" if result.get("ok") else "error", note="")
    return result


# ── 마케팅/프로모션 ──────────────────────────────────────────────────────────

@smartstore_router.get("/marketing")
def api_marketing(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    log_event("SMARTSTORE_MARKETING_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return _load_ss("marketing")

@smartstore_router.post("/marketing/collect")
def api_marketing_collect(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    import sys; sys.path.insert(0, str(ROOT))
    t0 = _time.monotonic()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page = browser.contexts[0].pages[0]
            from scripts.naver.smartstore import NaverSmartStore
            ss = NaverSmartStore(page)
            promo = ss.list_promotions()
            marketing = ss.list_marketing()
            result = {"ok": True, "promotions": promo, "marketing": marketing}
    except Exception as e:
        result = {"ok": False, "error": str(e)}
    result["collected_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    result["duration_ms"] = int((_time.monotonic() - t0) * 1000)
    _save_ss("marketing", result)
    log_event("SMARTSTORE_MARKETING_COLLECT", task_id="-", actor=user["actor"], role=user["role"],
              decision="ok" if result.get("ok") else "error", note="")
    return result
