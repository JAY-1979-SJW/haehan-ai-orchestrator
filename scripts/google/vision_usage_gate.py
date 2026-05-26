"""Google Cloud Vision monthly free-unit gate.

Cloud Vision API pricing is unit-based. The first 1,000 units used each month
are free for most Vision features, so this gate estimates requested units and
blocks work that would exceed the monthly free boundary unless cost approval is
explicitly present.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "data" / "google_vision_usage_gate"
LATEST_REPORT = ROOT / "data" / "google_vision_usage_gate_latest.json"

MONTHLY_FREE_LIMIT_UNITS = 1000
WARNING_THRESHOLD_UNITS = 800

VISION_FEATURES = (
    "label_detection",
    "text_detection",
    "document_text_detection",
    "safe_search_detection",
    "face_detection",
    "landmark_detection",
    "logo_detection",
    "image_properties",
    "crop_hints",
    "web_detection",
    "object_localization",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def normalize_features(features: list[str] | tuple[str, ...] | None) -> list[str]:
    normalized: list[str] = []
    for item in features or ["text_detection"]:
        key = item.strip().lower().replace("-", "_")
        if not key:
            continue
        if key not in VISION_FEATURES:
            key = "custom_or_unknown_feature"
        if key not in normalized:
            normalized.append(key)
    return normalized or ["text_detection"]


def estimate_vision_units(*, image_count: int = 0, page_count: int = 0, features: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    safe_images = max(0, int(image_count))
    safe_pages = max(0, int(page_count))
    normalized_features = normalize_features(features)
    billable_items = safe_images + safe_pages
    requested_units = billable_items * len(normalized_features)
    return {
        "image_count": safe_images,
        "page_count": safe_pages,
        "billable_items": billable_items,
        "features": normalized_features,
        "feature_count": len(normalized_features),
        "requested_units": requested_units,
        "unit_formula": "(image_count + page_count) * feature_count",
    }


def evaluate_vision_monthly_free_gate(
    *,
    current_month_units: int,
    image_count: int = 0,
    page_count: int = 0,
    features: list[str] | tuple[str, ...] | None = None,
    cost_approved: bool = False,
) -> dict[str, Any]:
    estimate = estimate_vision_units(image_count=image_count, page_count=page_count, features=features)
    current = max(0, int(current_month_units))
    projected = current + estimate["requested_units"]
    status = "ok"
    failed: list[str] = []
    if projected > MONTHLY_FREE_LIMIT_UNITS and not cost_approved:
        status = "blocked"
        failed.append("google_vision_monthly_free_units_exceeded")
    elif projected > WARNING_THRESHOLD_UNITS:
        status = "warn"
    return {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "google_vision_monthly_free_unit_gate",
        "ok": status != "blocked",
        "status": status,
        "failed_check_ids": failed,
        "current_month_units": current,
        "requested_units": estimate["requested_units"],
        "projected_month_units": projected,
        "monthly_free_limit_units": MONTHLY_FREE_LIMIT_UNITS,
        "warning_threshold_units": WARNING_THRESHOLD_UNITS,
        "cost_approved": bool(cost_approved),
        "cost_approval_required": projected > MONTHLY_FREE_LIMIT_UNITS,
        "secret_values_output": False,
        "estimate": estimate,
        "policy": {
            "free_boundary": "first 1000 units each month",
            "warn_at_units": WARNING_THRESHOLD_UNITS,
            "block_without_cost_approval_above_units": MONTHLY_FREE_LIMIT_UNITS,
            "api_key_or_service_account_required": "secret_action_mode_gate",
            "raw_secret_output": "blocked",
        },
        "next_step": (
            "Request explicit cost approval or reduce images/pages/features."
            if status == "blocked"
            else "Proceed within the monthly free-unit gate."
        ),
    }


def save_vision_monthly_free_gate(payload: dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"google_vision_usage_gate_{_stamp()}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    LATEST_REPORT.write_text(text, encoding="utf-8")
    return path


def _parse_features(value: str) -> list[str]:
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Google Vision monthly free-unit gate.")
    parser.add_argument("--current-month-units", type=int, default=0)
    parser.add_argument("--images", type=int, default=0)
    parser.add_argument("--pages", type=int, default=0)
    parser.add_argument("--features", default="text_detection")
    parser.add_argument("--cost-approved", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = evaluate_vision_monthly_free_gate(
        current_month_units=args.current_month_units,
        image_count=args.images,
        page_count=args.pages,
        features=_parse_features(args.features),
        cost_approved=args.cost_approved,
    )
    path = save_vision_monthly_free_gate(payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "google_vision_usage_gate "
            f"status={payload['status']} ok={payload['ok']} "
            f"current={payload['current_month_units']} requested={payload['requested_units']} "
            f"projected={payload['projected_month_units']} limit={payload['monthly_free_limit_units']} "
            f"report={path}"
        )
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
