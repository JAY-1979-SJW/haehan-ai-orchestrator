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
