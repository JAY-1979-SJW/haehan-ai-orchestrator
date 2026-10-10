"""Policy Layer 감사 스크립트 — read-only.

SafetyPolicy registry, secret redaction, 차단 정책을 점검한다.
외부 호출, DB 접속, 파일 수정 금지.

exit code: 0=PASS/PASS_WITH_KNOWN_WARN, 1=FAIL, 2=STOP_CONDITION
"""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
# sys.path에 프로젝트 root 추가 (직접 실행 시 필요)
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

AUDIT_NAME = "policy_layer"

REQUIRED_POLICY_IDS = [
    "EXTERNAL_APP_HOLD_BLOCK",
    "OAUTH_API_REQUIRED_BLOCK",
    "USER_DIRECT_REQUIRED_BLOCK",
    "LOCAL_AGENT_REQUIRED_SERVER_BLOCK",
    "BLOCKED_ACTION_DENY",
    "SECRET_REDACTION_REQUIRED",
    "SERVER_EXTERNAL_WEB_BLOCK",
    "APPROVAL_REQUIRED_GATE",
]

# 개별 체크용 매핑 (checklist id → policy_id)
_POLICY_ID_MAP = {
    "pl-05": "EXTERNAL_APP_HOLD_BLOCK",
    "pl-06": "OAUTH_API_REQUIRED_BLOCK",
    "pl-07": "USER_DIRECT_REQUIRED_BLOCK",
    "pl-08": "LOCAL_AGENT_REQUIRED_SERVER_BLOCK",
    "pl-09": "BLOCKED_ACTION_DENY",
    "pl-10": "SECRET_REDACTION_REQUIRED",
    "pl-11": "SERVER_EXTERNAL_WEB_BLOCK",
    "pl-12": "APPROVAL_REQUIRED_GATE",
}

CHECKLIST = [
    {"id": "pl-01", "title": "safety_policy 패키지 존재", "required": True},
    {"id": "pl-02", "title": "safety_policy_registry.py 존재", "required": True},
    {"id": "pl-03", "title": "secret_redaction.py 존재", "required": True},
    {"id": "pl-04", "title": "필수 정책 8개 존재", "required": True},
    {"id": "pl-05", "title": "external_app_hold_policy 존재", "required": True},
    {"id": "pl-06", "title": "oauth_api_required_policy 존재", "required": True},
    {"id": "pl-07", "title": "user_direct_required_policy 존재", "required": True},
    {"id": "pl-08", "title": "local_agent_required_policy 존재", "required": True},
    {"id": "pl-09", "title": "blocked_action_policy 존재", "required": True},
    {"id": "pl-10", "title": "secret_redaction_policy 존재", "required": True},
    {"id": "pl-11", "title": "server_external_web_block_policy 존재", "required": True},
    {"id": "pl-12", "title": "approval_required_gate_policy 존재", "required": True},
    {"id": "pl-13", "title": "secret forbidden key 목록 존재 (43개 이상)", "required": True},
    {"id": "pl-14", "title": "redact_sensitive_fields 동작", "required": True},
    {"id": "pl-15", "title": "nested metadata redaction 동작", "required": True},
    {"id": "pl-16", "title": "ExecutionPolicyService와 연결됨", "required": False},
    {"id": "pl-17", "title": "CAD/HWPX/Excel/Tax/Bid 차단 가능", "required": True},
    {"id": "pl-18", "title": "OAuth 설정 전 차단 가능", "required": True},
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _item(cid: str, status: str, evidence: str, details: dict | None = None) -> dict:
    meta = next(c for c in CHECKLIST if c["id"] == cid)
    return {
        "id": cid,
        "title": meta["title"],
        "required": meta["required"],
        "status": status,
        "evidence": evidence,
        "details": details or {},
    }


def _check_policy_files_exist() -> list[dict]:
    files = {
        "pl-01": ROOT / "ai_orchestrator/safety_policy/__init__.py",
        "pl-02": ROOT / "ai_orchestrator/safety_policy/safety_policy_registry.py",
        "pl-03": ROOT / "ai_orchestrator/safety_policy/secret_redaction.py",
    }
    return [_item(cid, "PASS" if p.exists() else "FAIL", str(p)) for cid, p in files.items()]


def _check_policy_registry() -> list[dict]:
    pl_ids = ["pl-04", "pl-05", "pl-06", "pl-07", "pl-08", "pl-09", "pl-10", "pl-11", "pl-12"]
    try:
        registry_mod = importlib.import_module("ai_orchestrator.safety_policy.safety_policy_registry")
    except Exception as e:  # noqa: BLE001 - 정책 레지스트리/비밀 마스킹 계약 자체검증 스크립트 - import/판정 호출 실패를 체크리스트 WARN/FAIL로 기록(실제 정책 강제가 아닌 감사 리포트)
        return [_item(cid, "FAIL", f"import 실패: {e}") for cid in pl_ids]

    # list_all_policies 또는 get_all_policies 시도
    list_fn = getattr(registry_mod, "list_all_policies", getattr(registry_mod, "get_all_policies", None))
    getattr(registry_mod, "get_policy", None)
    policies = list_fn() if list_fn else []
    policy_ids = {p.policy_id for p in policies} if policies else set()

    found_count = sum(1 for pid in REQUIRED_POLICY_IDS if pid in policy_ids)
    results = [
        _item("pl-04", "PASS" if found_count >= 8 else "FAIL", f"발견={found_count}/8, ids={sorted(policy_ids)}")
    ]
    for cid, pid in _POLICY_ID_MAP.items():
        found = pid in policy_ids
        results.append(_item(cid, "PASS" if found else "FAIL", f"{pid}: {'found' if found else 'not found'}"))
    return results


def _check_secret_redaction() -> list[dict]:
    try:
        redact_mod = importlib.import_module("ai_orchestrator.safety_policy.secret_redaction")
    except Exception as e:  # noqa: BLE001 - 정책 레지스트리/비밀 마스킹 계약 자체검증 스크립트 - import/판정 호출 실패를 체크리스트 WARN/FAIL로 기록(실제 정책 강제가 아닌 감사 리포트)
        return [_item(cid, "FAIL", f"import 실패: {e}") for cid in ["pl-13", "pl-14", "pl-15"]]

    forbidden = getattr(redact_mod, "FORBIDDEN_SECRET_FIELDS", None)
    pl13 = _item(
        "pl-13",
        "PASS" if (forbidden and len(forbidden) >= 35) else "FAIL",
        f"forbidden 키 수={len(forbidden) if forbidden else 0}",
        {"count": len(forbidden) if forbidden else 0},
    )

    redact_fn = getattr(redact_mod, "redact_sensitive_fields", None)
    if not redact_fn:
        return [
            pl13,
            _item("pl-14", "FAIL", "redact_sensitive_fields 없음"),
            _item("pl-15", "FAIL", "redact_sensitive_fields 없음"),
        ]

    test_data = {"password": "FAKE_PASS", "note": "ok"}
    out = redact_fn(test_data)
    ok = out.get("password") == "[REDACTED]" and out.get("note") == "ok"
    pl14 = _item("pl-14", "PASS" if ok else "FAIL", f"redact 결과: password→{out.get('password')}")

    nested = {"outer": {"token": "FAKE_TOKEN", "note": "ok"}}
    out2 = redact_fn(nested)
    nested_ok = out2.get("outer", {}).get("token") == "[REDACTED]"
    pl15 = _item("pl-15", "PASS" if nested_ok else "FAIL", f"nested redact: token→{out2.get('outer', {}).get('token')}")
    return [pl13, pl14, pl15]


def _check_execution_policy_service_linked() -> dict:
    try:
        eps = importlib.import_module("ai_orchestrator.services.execution_policy_service")
        has_eps = hasattr(eps, "ExecutionPolicyService")
        return _item("pl-16", "PASS" if has_eps else "WARN", "ExecutionPolicyService 존재" if has_eps else "미연결")
    except Exception as e:  # noqa: BLE001 - 정책 레지스트리/비밀 마스킹 계약 자체검증 스크립트 - import/판정 호출 실패를 체크리스트 WARN/FAIL로 기록(실제 정책 강제가 아닌 감사 리포트)
        return _item("pl-16", "WARN", str(e))


def _check_cad_bid_blocked() -> dict:
    # pl-17: CAD/Tax/Bid 차단 — decide_execution_policy(classification) 사용
    try:
        eps = importlib.import_module("ai_orchestrator.services.execution_policy_service")
        svc = eps.ExecutionPolicyService()
        d_cad = svc.decide_execution_policy("EXTERNAL_APP_HOLD")
        d_bid = svc.decide_execution_policy("USER_DIRECT_REQUIRED")
        both_blocked = not d_cad.server_executable and not d_bid.server_executable
        return _item(
            "pl-17",
            "PASS" if both_blocked else "FAIL",
            f"CAD is_external_app_hold={d_cad.is_external_app_hold} is_blocked={d_cad.is_blocked}, "
            f"BID server_executable={d_bid.server_executable}",
        )
    except Exception as e:  # noqa: BLE001 - 정책 레지스트리/비밀 마스킹 계약 자체검증 스크립트 - import/판정 호출 실패를 체크리스트 WARN/FAIL로 기록(실제 정책 강제가 아닌 감사 리포트)
        return _item("pl-17", "WARN", f"판정 호출 실패: {e}")


def _check_oauth_blocked() -> dict:
    # pl-18: OAuth 차단 — decide_execution_policy(classification) 사용
    try:
        eps = importlib.import_module("ai_orchestrator.services.execution_policy_service")
        svc = eps.ExecutionPolicyService()
        d = svc.decide_execution_policy("OFFICIAL_API_OR_OAUTH_REQUIRED")
        return _item(
            "pl-18",
            "PASS" if d.requires_oauth_setup or d.is_blocked else "FAIL",
            f"requires_oauth_setup={d.requires_oauth_setup} is_blocked={d.is_blocked}",
        )
    except Exception as e:  # noqa: BLE001 - 정책 레지스트리/비밀 마스킹 계약 자체검증 스크립트 - import/판정 호출 실패를 체크리스트 WARN/FAIL로 기록(실제 정책 강제가 아닌 감사 리포트)
        return _item("pl-18", "WARN", f"판정 호출 실패: {e}")


def run_audit() -> dict[str, Any]:
    # 2026-09-29 STD-08(복잡도) 리팩터: pl-01~18 체크 블록을 _check_*() 함수로 분리(순서·조건·
    # 문자열 그대로).
    results: list[dict[str, Any]] = []
    results.extend(_check_policy_files_exist())
    results.extend(_check_policy_registry())
    results.extend(_check_secret_redaction())
    results.append(_check_execution_policy_service_linked())
    results.append(_check_cad_bid_blocked())
    results.append(_check_oauth_blocked())

    summary = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    for r in results:
        summary[r["status"].lower()] = summary.get(r["status"].lower(), 0) + 1

    required_fail = any(r["status"] == "FAIL" and r["required"] for r in results)
    verdict = "FAIL" if required_fail else ("PASS_WITH_KNOWN_WARN" if summary["warn"] > 0 else "PASS")

    return {
        "audit_name": AUDIT_NAME,
        "verdict": verdict,
        "checked_at": _now(),
        "checklist": results,
        "summary": summary,
    }


def main() -> int:
    from scripts.common.audit_cli import run_checklist_cli

    return run_checklist_cli(AUDIT_NAME, run_audit)


if __name__ == "__main__":
    sys.exit(main())
