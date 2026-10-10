"""SmartStore action catalog and approval-gated workflow helpers.

The module is intentionally browser-light.  It builds a static baseline from
the SmartStore modules already present in the repo, records dry-run plans, and
keeps every state-changing operation behind an explicit confirmation token.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.site_engine.catalog_helpers import load_or_build_catalog

ROOT = Path(__file__).resolve().parents[4]


def _ss_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("smartstore")


DATA_DIR = _ss_dir()
LATEST_ACTION_CATALOG_PATH = DATA_DIR / "smartstore_action_catalog_latest.json"
LATEST_PREPARE_PLAN_PATH = DATA_DIR / "smartstore_prepare_plan_latest.json"
LATEST_SUBMIT_RECORD_PATH = DATA_DIR / "smartstore_submit_latest.json"
SUBMIT_RECORD_DIR = DATA_DIR / "smartstore_submits"

APPROVAL_CONFIRM_TEXT = "SMARTSTORE_APPROVED_SUBMIT"

READ_ACTIONS = [
    {
        "action_id": "dashboard.open",
        "label": "open seller dashboard",
        "module": "scripts.naver.smartstore.NaverSmartStore.open_dashboard",
        "risk": "read",
        "status": "implemented",
    },
    {
        "action_id": "product.list",
        "label": "list registered products",
        "module": "scripts.naver.smartstore.NaverSmartStore.list_products",
        "risk": "read",
        "status": "implemented",
    },
    {
        "action_id": "order.list",
        "label": "list orders",
        "module": "scripts.naver.smartstore.NaverSmartStore.list_orders",
        "risk": "read",
        "status": "implemented",
    },
    {
        "action_id": "settlement.list",
        "label": "list settlements",
        "module": "scripts.naver.smartstore.NaverSmartStore.list_settlements",
        "risk": "read",
        "status": "implemented",
    },
    {
        "action_id": "review.list",
        "label": "list reviews",
        "module": "scripts.naver.smartstore.NaverSmartStore.list_reviews",
        "risk": "read",
        "status": "implemented",
    },
    {
        "action_id": "inquiry.list",
        "label": "list inquiries",
        "module": "scripts.naver.smartstore.NaverSmartStore.list_inquiries",
        "risk": "read",
        "status": "implemented",
    },
    {
        "action_id": "stats.collect",
        "label": "collect seller stats",
        "module": "scripts.naver.smartstore.NaverSmartStore.stats",
        "risk": "read",
        "status": "implemented",
    },
    {
        "action_id": "store.info",
        "label": "read store information",
        "module": "scripts.naver.smartstore.NaverSmartStore.store_info",
        "risk": "read",
        "status": "implemented",
    },
]

PREPARE_ACTIONS = [
    {
        "action_id": "product.general.prepare",
        "label": "prepare general product fields",
        "module": "scripts.naver.smartstore.general_product.GeneralProductRegister.register_product",
        "risk": "prepare",
        "status": "implemented",
        "required_fields": ["name", "price", "stock"],
        "optional_fields": ["category", "main_image", "brand", "manufacturer", "model_name", "description"],
    },
    {
        "action_id": "product.group.prepare",
        "label": "prepare group product fields",
        "module": "scripts.naver.smartstore.product.ProductRegister.register_product",
        "risk": "prepare",
        "status": "implemented",
        "required_fields": ["name"],
        "optional_fields": [
            "category",
            "model_name",
            "brand",
            "manufacturer",
            "main_image",
            "additional_images",
            "description",
        ],
    },
    {
        "action_id": "product.bulk.prepare",
        "label": "validate and prepare bulk products",
        "module": "scripts.naver.smartstore.bulk.BulkRegister.register_all",
        "risk": "prepare",
        "status": "implemented",
        "required_fields": ["products"],
        "optional_fields": ["product_type", "max_retries", "stop_on_error"],
    },
]

APPROVAL_ACTIONS = [
    {
        "action_id": "product.general.save",
        "label": "save general product",
        "module": "scripts.naver.smartstore.general_product.GeneralProductRegister.save",
        "risk": "approval",
        "status": "complete_baseline",
        "requires": ["--approved", f"--confirm={APPROVAL_CONFIRM_TEXT}"],
    },
    {
        "action_id": "product.group.save",
        "label": "save group product",
        "module": "scripts.naver.smartstore.product.ProductRegister.save",
        "risk": "approval",
        "status": "complete_baseline",
        "requires": ["--approved", f"--confirm={APPROVAL_CONFIRM_TEXT}"],
    },
    {
        "action_id": "product.bulk.save",
        "label": "save bulk product registration",
        "module": "scripts.naver.smartstore.bulk.BulkRegister.register_all",
        "risk": "approval",
        "status": "complete_baseline",
        "requires": ["--approved", f"--confirm={APPROVAL_CONFIRM_TEXT}"],
    },
    {
        "action_id": "review.reply.send",
        "label": "send SmartStore review reply (AI auto-draft)",
        "module": "scripts.naver.smartstore.product.review_reply.ReviewAutoResponder",
        "risk": "approval",
        "status": "implemented",
        "requires": ["--approved", f"--confirm={APPROVAL_CONFIRM_TEXT}"],
    },
    {
        "action_id": "order.shipping.process",
        "label": "process order shipping (input tracking number)",
        "module": "scripts.naver.smartstore.product.order_shipping.OrderShippingProcessor",
        "risk": "approval",
        "status": "implemented",
        "requires": ["--approved", f"--confirm={APPROVAL_CONFIRM_TEXT}"],
    },
    {
        "action_id": "product.delete",
        "label": "delete product(s) from smartstore",
        "module": "scripts.naver.smartstore.product.product_delete.ProductDeleter",
        "risk": "approval",
        "status": "implemented",
        "requires": ["--approved", f"--confirm={APPROVAL_CONFIRM_TEXT}"],
    },
]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _section(name: str, actions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": name,
        "actions": actions,
        "summary": {
            "total": len(actions),
            "implemented": sum(1 for item in actions if item.get("status") in {"implemented", "complete_baseline"}),
            "approval_gated": sum(1 for item in actions if item.get("risk") == "approval"),
        },
    }


def build_action_catalog() -> dict[str, Any]:
    return {
        "generated_at": _now(),
        "site_id": "smartstore",
        "contract": {
            "read": "may read/list only after normal navigation gate",
            "prepare": "may fill/prepare explicit product data but must not save by default",
            "submit": f"requires --approved and --confirm={APPROVAL_CONFIRM_TEXT}",
            "live_explore": "paused after Naver robot detection; prefer dry-run/static catalog first",
        },
        "sections": [
            _section("read", READ_ACTIONS),
            _section("prepare", PREPARE_ACTIONS),
            _section("approval", APPROVAL_ACTIONS),
        ],
    }


def save_action_catalog(catalog: dict[str, Any] | None = None, output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_ACTION_CATALOG_PATH
    path.write_text(json.dumps(catalog or build_action_catalog(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_action_catalog(path: str | Path | None = None) -> dict[str, Any]:
    return load_or_build_catalog(path, LATEST_ACTION_CATALOG_PATH, build_action_catalog, save_action_catalog)


def _all_actions(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for section in catalog.get("sections") or []:
        result.extend(section.get("actions") or [])
    return result


def get_action(catalog: dict[str, Any], action_id: str) -> dict[str, Any]:
    for action in _all_actions(catalog):
        if action.get("action_id") == action_id:
            return action
    raise KeyError(f"unknown SmartStore action: {action_id}")


def load_product_data(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("SmartStore product data must be a JSON object")
    return data


def _validate_product_data(product_type: str, data: dict[str, Any]) -> dict[str, Any]:
    if product_type == "general":
        required = ["name", "price", "stock"]
    elif product_type == "group":
        required = ["name"]
    else:
        raise ValueError("product_type must be general or group")
    missing = [field for field in required if data.get(field) in (None, "")]
    return {"required": required, "missing": missing, "ok": not missing}


def build_prepare_plan(
    data: dict[str, Any],
    *,
    product_type: str = "general",
    save_after: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    validation = _validate_product_data(product_type, data)
    fields = sorted(str(key) for key in data)
    action_id = f"product.{product_type}.prepare"
    save_action_id = f"product.{product_type}.save"
    return {
        "generated_at": _now(),
        "site_id": "smartstore",
        "workflow": "product_register",
        "product_type": product_type,
        "prepare_action_id": action_id,
        "save_action_id": save_action_id if save_after else "",
        "data_fields": fields,
        "validation": validation,
        "approval": {
            "required": bool(save_after),
            "confirm_text_required": APPROVAL_CONFIRM_TEXT if save_after else "",
        },
        "dry_run": dry_run,
        "prepared": False,
        "saved": False,
        "submit_executed": False,
    }


def save_prepare_plan(plan: dict[str, Any], output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_PREPARE_PLAN_PATH
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_submit_plan(
    *,
    action_id: str,
    product_type: str = "general",
    approved_by: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    catalog = load_action_catalog()
    action = get_action(catalog, action_id)
    if action.get("risk") != "approval":
        raise ValueError(f"SmartStore action is not approval-gated: {action_id}")
    return {
        "generated_at": _now(),
        "site_id": "smartstore",
        "workflow": "product_register",
        "product_type": product_type,
        "action": action,
        "approval": {
            "required": True,
            "approved_by": approved_by,
            "confirm_text_required": APPROVAL_CONFIRM_TEXT,
        },
        "dry_run": dry_run,
        "prepared": False,
        "saved": False,
        "submit_executed": False,
    }


def save_submit_record(record: dict[str, Any], output: str | Path | None = None) -> Path:
    SUBMIT_RECORD_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(output) if output else SUBMIT_RECORD_DIR / f"smartstore_submit_{stamp}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    LATEST_SUBMIT_RECORD_PATH.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from scripts.common.realtime_audit import emit_event

        emit_event(
            "SMARTSTORE_SUBMIT_EXECUTED" if record.get("submit_executed") else "SMARTSTORE_DRY_RUN",
            site="smartstore",
            workflow=record.get("workflow") or "product_register",
            status="ok" if record.get("ok", True) else "failed",
            risk="approval" if record.get("approval", {}).get("required") else "prepare",
            message="SmartStore workflow recorded",
            artifact_path=str(path),
            metadata={
                "product_type": record.get("product_type"),
                "action_id": (record.get("action") or {}).get("action_id"),
                "dry_run": record.get("dry_run"),
            },
        )
    except Exception:  # noqa: BLE001 - 스마트스토어 제출 기록 저장(save_submit_record) 후 부가적인 실시간 감사 이벤트 전송(emit_event) 실패를 흡수하는 except — 기록 파일 저장은 이미 완료된 뒤이며, 이 except가 실제 제출/결제 동작에 영향을 주지 않음.
        pass
    return path


def print_action_catalog_summary(catalog: dict[str, Any], path: Path | None = None) -> None:
    print("=" * 60)
    print("SmartStore action catalog")
    print("=" * 60)
    for section in catalog.get("sections") or []:
        summary = section.get("summary") or {}
        print(
            f"- {section.get('name')}: total={summary.get('total', 0)} "
            f"implemented={summary.get('implemented', 0)} "
            f"approval_gated={summary.get('approval_gated', 0)}"
        )
    if path:
        print(f"saved: {path}")


def print_prepare_plan_summary(plan: dict[str, Any], path: Path | None = None) -> None:
    print("=" * 60)
    print("SmartStore prepare plan")
    print("=" * 60)
    validation = plan.get("validation") or {}
    print(f"product_type={plan.get('product_type')}")
    print(f"fields={','.join(plan.get('data_fields') or [])}")
    print(f"validation_ok={validation.get('ok')} missing={','.join(validation.get('missing') or [])}")
    print(f"save_after={bool(plan.get('save_action_id'))} dry_run={plan.get('dry_run')}")
    if path:
        print(f"saved: {path}")
