"""카탈로그·메뉴·가이드 엔드포인트 (읽기 전용)."""

from __future__ import annotations

import contextlib
import json
import sys

from fastapi import APIRouter, Depends

from tools.gates.auth import require_role

from ...audit.audit_logger import log_event
from ._helpers import ROOT

router = APIRouter()

REQUIRED_FIELDS = ["name", "price", "stock", "category"]
OPTIONAL_FIELDS = ["description", "brand", "manufacturer", "main_image", "model_name"]


@router.get("/status")
def api_status(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """스마트스토어 액션 카탈로그 + DB 상태."""
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.api.actions import build_action_catalog, load_action_catalog

    catalog_path = ROOT / "data" / "smartstore_action_catalog_latest.json"
    try:
        catalog = load_action_catalog(catalog_path) if catalog_path.exists() else build_action_catalog()
    except Exception:  # noqa: BLE001 - 스마트스토어 카탈로그/이력/메뉴 조회 엔드포인트(읽기전용) — 카탈로그 로드 실패 시 build_action_catalog()로 재생성 폴백, 제출이력 JSON 파일 손상 시 해당 건만 건너뜀(이미 noqa: S110 존재).
        catalog = build_action_catalog()
    log_event("SMARTSTORE_STATUS_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return {"catalog": catalog, "db_path": str(catalog_path.name)}


@router.get("/submit-history")
def api_submit_history(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """최근 제출 이력."""
    data_dir = ROOT / "data"
    submit_path = data_dir / "smartstore_submit_latest.json"
    submits_dir = data_dir / "smartstore_submits"
    history: list = []
    if submits_dir.exists():
        for f in sorted(submits_dir.glob("*.json"), reverse=True)[:20]:
            # 제출이력 JSON 파일 손상 시 해당 건만 건너뜀(읽기전용)
            with contextlib.suppress(Exception):
                history.append(json.loads(f.read_text(encoding="utf-8")))
    latest: dict = {}
    if submit_path.exists():
        # 제출이력 JSON 파일 손상 시 건너뜀(읽기전용)
        with contextlib.suppress(Exception):
            latest = json.loads(submit_path.read_text(encoding="utf-8"))
    log_event(
        "SMARTSTORE_HISTORY_READ",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"count={len(history)}",
    )
    return {"latest": latest, "history": history, "count": len(history)}


@router.get("/menu-map")
def api_menu_map(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """13개 메뉴 구조."""
    log_event("SMARTSTORE_MENU_MAP_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return {
        "menus": [
            {
                "key": "products",
                "label": "상품관리",
                "features": ["상품 목록", "상품 등록", "상품 수정", "카탈로그 가격관리", "배송정보 관리"],
            },
            {"key": "orders", "label": "판매관리", "features": ["주문 목록", "발송 처리", "반품/교환"]},
            {"key": "settlement", "label": "정산관리", "features": ["정산 내역", "세금계산서"]},
            {"key": "reviews", "label": "문의/리뷰관리", "features": ["고객 리뷰", "고객 문의", "리뷰 자동응답"]},
            {"key": "store", "label": "스토어관리", "features": ["스토어 정보", "공지사항", "구독 관리"]},
            {"key": "marketing", "label": "혜택/마케팅", "features": ["쿠폰", "할인", "포인트"]},
            {"key": "delivery", "label": "N배송 관리", "features": ["배송 현황", "반품 처리"]},
            {"key": "solution", "label": "커머스솔루션", "features": ["솔루션 현황"]},
            {"key": "stats", "label": "데이터분석", "features": ["매출 통계", "방문 통계", "상품 분석"]},
            {"key": "ads", "label": "광고관리", "features": ["광고 현황"], "locked": True},
            {"key": "promo", "label": "프로모션 관리", "features": ["프로모션 목록"]},
            {"key": "connect", "label": "쇼핑 커넥트", "features": ["채널 연결"]},
            {"key": "seller", "label": "판매자 정보", "features": ["사업자 정보", "정책 관리"]},
        ]
    }


@router.get("/product-register-guide")
def api_register_guide(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """상품 등록 5단계 가이드."""
    log_event(
        "SMARTSTORE_REGISTER_GUIDE_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note=""
    )
    return {
        "steps": [
            {"step": 1, "title": "카테고리 선택", "desc": "생활/건강 > 조명 > 무드등/취침등", "required": True},
            {"step": 2, "title": "기본 정보", "desc": "상품명, 판매가, 재고 입력", "required": True},
            {"step": 3, "title": "이미지 등록", "desc": "대표이미지(필수), 추가이미지(선택)", "required": True},
            {"step": 4, "title": "상세 설명", "desc": "스마트에디터 또는 HTML 작성", "required": False},
            {"step": 5, "title": "저장", "desc": "임시저장 → 최종 저장(노출설정)", "required": True},
        ],
        "required_fields": REQUIRED_FIELDS,
        "optional_fields": OPTIONAL_FIELDS + ["options"],  # noqa: RUF005
        "limits": {"name_max": 100, "price_min": 10, "stock_max": 9999999, "image_max_mb": 10},
        "approval_token": "SMARTSTORE_APPROVED_SUBMIT",
    }


@router.get("/product-form-fields")
def api_product_form_fields(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """상품 등록 폼 필드 정의."""
    sys.path.insert(0, str(ROOT))
    required, optional = REQUIRED_FIELDS, OPTIONAL_FIELDS
    try:
        from scripts.naver.smartstore.product.models import (  # type: ignore[attr-defined]  # 실제 없음(2026-09-29 defect_index #39 확인) — 바로 아래 except ImportError 로 안전하게 fallback, 조용한 저하로 남겨둠(저우선순위)
            OPTIONAL_FIELDS as OF,
        )
        from scripts.naver.smartstore.product.models import REQUIRED_FIELDS as RF  # type: ignore[attr-defined]

        required, optional = RF, OF
    except ImportError:
        pass
    log_event("SMARTSTORE_FORM_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return {"required": required, "optional": optional}
