"""Audit locked Google domain/module/page/action/input/control/evidence boundaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_COUNTS = {
    "submodule_count": 10,
    "domain_module_count": 50,
    "page_tab_module_count": 185,
    "work_action_module_count": 96,
    "input_field_module_count": 140,
    "final_control_module_count": 143,
    "evidence_module_count": 96,
    "surface_count": 50,
}


def _check_counts(payload: dict) -> list[str]:
    return [
        f"{key} {payload.get(key)} != {expected}"
        for key, expected in EXPECTED_COUNTS.items()
        if payload.get(key) != expected
    ]


def _check_required_true_checks(checks: dict) -> list[str]:
    required_true_checks = (
        "catalog_matches_taxonomy",
        "all_groups_have_owner",
        "all_owner_modules_exist",
        "all_domain_modules_have_implementation",
        "all_domain_modules_have_page_tabs",
        "all_action_modules_have_domain_module",
        "all_domain_modules_have_read_action",
        "all_page_tab_modules_have_gate",
        "no_input_field_allows_secret_value",
        "no_final_control_allows_ai_click",
        "no_evidence_module_stores_raw_secret",
    )
    return [f"check failed: {key}" for key in required_true_checks if checks.get(key) is not True]


def _check_final_controls(final_controls: list) -> list[str]:
    bad_controls = [
        item["key"] for item in final_controls if item.get("ai_click_allowed") or not item.get("user_click_required")
    ]
    if bad_controls:
        return ["unsafe final controls: " + ", ".join(bad_controls[:20])]
    return []


def _check_raw_secret_evidence(evidence_modules: list) -> list[str]:
    raw_secret_evidence = [item["key"] for item in evidence_modules if item.get("store_raw_secret")]
    if raw_secret_evidence:
        return ["raw secret evidence modules: " + ", ".join(raw_secret_evidence[:20])]
    return []


def _check_approval_actions_have_final_controls(payload: dict, final_controls: list) -> list[str]:
    approval_actions = [item for item in payload.get("work_action_modules", []) if item.get("requires_approval")]
    control_keys = {item["key"] for item in final_controls}
    missing_controls = [
        f"{action['key']}.final_control"
        for action in approval_actions
        if f"{action['key']}.final_control" not in control_keys
    ]
    if missing_controls:
        return ["approval actions missing final controls: " + ", ".join(missing_controls[:20])]
    return []


def _check_secret_tabs_gate(payload: dict) -> list[str]:
    secret_tabs = [
        item["key"]
        for item in payload.get("page_tab_modules", [])
        if item.get("secret_sensitive") and item.get("gate") != "secret_value_export_blocked"
    ]
    if secret_tabs:
        return ["secret tabs without export block gate: " + ", ".join(secret_tabs[:20])]
    return []


def _check_non_empty_module_lists(payload: dict) -> list[str]:
    return [
        f"{key} empty" for key in ("domain_modules", "page_tab_modules", "work_action_modules") if not payload.get(key)
    ]


def audit() -> dict[str, Any]:
    # 2026-09-29 STD-08(복잡도) 리팩터: 독립 체크들을 _check_*() 함수로 분리(순서·조건·문자열
    # 그대로) — #48 과 같은 계열.
    from scripts.google import module_check

    payload = module_check.build_google_module_index()
    failures: list[str] = []
    warnings: list[str] = []

    if not payload.get("ok"):
        failures.append("google module index ok=false")

    failures.extend(_check_counts(payload))
    failures.extend(_check_required_true_checks(payload.get("checks") or {}))

    final_controls = payload.get("final_control_modules") or []
    failures.extend(_check_final_controls(final_controls))
    failures.extend(_check_raw_secret_evidence(payload.get("evidence_modules") or []))
    failures.extend(_check_approval_actions_have_final_controls(payload, final_controls))
    failures.extend(_check_secret_tabs_gate(payload))
    failures.extend(_check_non_empty_module_lists(payload))

    return {
        "ok": not failures,
        "counts": {key: payload.get(key) for key in EXPECTED_COUNTS},
        "failures": failures,
        "warnings": warnings,
        "lock": {
            "top_module": payload.get("top_module", {}).get("key"),
            "login_boundary": payload.get("login_boundary"),
            "approval_boundary": payload.get("approval_boundary"),
            "secret_boundary": payload.get("secret_boundary"),
        },
    }


def main() -> int:
    report = audit()
    try:
        from scripts.google import work_records

        work_records.checkpoint(
            step=(
                "google domain module boundary audit: "
                + ("PASS" if report["ok"] else "FAIL")
                + f", counts={report['counts']}"
            ),
            command="python tools/audits/google/audit_google_domain_module_boundaries.py",
            verification=(
                "RESULT="
                + ("PASS_GOOGLE_DOMAIN_MODULE_BOUNDARIES" if report["ok"] else "FAIL_GOOGLE_DOMAIN_MODULE_BOUNDARIES")
            ),
            report="data/runtime/ai_work_records/google/latest.json",
            touched=[
                "tools/audits/google/audit_google_domain_module_boundaries.py",
                "scripts/google/work_records.py",
            ],
            next_step="keep google boundary changes inside google lane and rerun boundary audit",
        )
    except Exception as exc:  # noqa: BLE001 - 구글 도메인 모듈 경계 감사 — 메인 판정(report)은 이미 계산된 뒤, 부가적인 작업기록 체크포인트(work_records.checkpoint) 실패만 흡수해 warnings에 남기고 report['ok']에는 영향 없음.
        report.setdefault("warnings", []).append(f"work_record_checkpoint_failed:{type(exc).__name__}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        "RESULT=" + ("PASS_GOOGLE_DOMAIN_MODULE_BOUNDARIES" if report["ok"] else "FAIL_GOOGLE_DOMAIN_MODULE_BOUNDARIES")
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
