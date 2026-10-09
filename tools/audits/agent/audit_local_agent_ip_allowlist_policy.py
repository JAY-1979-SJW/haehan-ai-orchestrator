"""IP_ALLOWLIST_USER_DESKTOP_POLICY_01 audit.

정책 문서 + nginx 변경 계획서가 spec 요구를 충족하는지 자기검증.
실제 nginx 는 건드리지 않음 — 문서/룰 정합성만 검사.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

POLICY_DOC = Path("docs/ops/local_agent_ip_allowlist_policy.md")
NGINX_PLAN = Path("docs/ops/local_agent_public_ws_nginx_plan.md")


# 공개 허용 가능 endpoint (C/D안 모두)
ALLOWED_PUBLIC_PATHS = frozenset(
    {
        "/orchestrator/api/v1/local-agents/register-with-code",
        "/orchestrator/api/v1/local-agents/ws",
        "/public/local-agent/register",
        "/public/local-agent/ws",
    }
)

# 절대 공개 금지 (admin/owner) — 정확 매칭용 (path 경계 포함)
FORBIDDEN_PUBLIC_PATHS = frozenset(
    {
        "/orchestrator/api/v1/local-agents/registration-codes",
        "/orchestrator/admin-web/",
    }
)


# 매칭 시 어느 한쪽 경계만 path 일치하도록 — register-with-code 같은 정상 path 와 충돌 방지
def _forbidden_in_section(section: str) -> list[str]:
    """공개 섹션 안에 FORBIDDEN 경로가 명시되어 있으면 반환. 경계 단어 매칭."""
    hits = []
    for p in FORBIDDEN_PUBLIC_PATHS:
        # 다음 문자가 공백/줄바꿈/표끝/괄호 등이어야 정확 매칭
        if re.search(re.escape(p) + r"(?:[\s\)`*\|<]|$)", section):
            hits.append(p)
    return hits


@dataclass
class PolicyVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _find_secrets_in_text(text: str) -> list[str]:
    """문서 본문에 실제 secret 값이 들어갔는지 (예시 외)."""
    leaks = []
    # 토큰 패턴 (32자 이상 hex/base64)
    if re.search(r"\b[A-Fa-f0-9]{32,}\b", text):
        leaks.append("hex_secret_like")
    if re.search(r"\b[A-Za-z0-9+/=]{40,}\b", text):
        # 단, "registration_code" / "device_token" 같은 문서 키워드는 OK
        # 실제 secret 값은 코드블록 내 "registration_code":"실값" 형태
        if re.search(r'"(registration_code|device_token|token|password)"\s*:\s*"[^"]{8,}"', text):
            leaks.append("token_value_in_quoted")
    return leaks


def _check_secret_leak(policy_text: str, nginx_text: str, metrics: dict) -> PolicyVerdict | None:
    """1) FAIL_SECRET_LEAK — 문서 본문 secret 값."""
    leaks = _find_secrets_in_text(policy_text) + _find_secrets_in_text(nginx_text)
    metrics["secret_leak_markers"] = leaks
    if leaks:
        return PolicyVerdict(False, "FAIL_SECRET_LEAK", reasons=[f"secret_value_in_docs:{leaks[:3]}"], metrics=metrics)
    return None


def _check_recommendation_present(policy_text: str, metrics: dict) -> PolicyVerdict | None:
    """2) FAIL_RECOMMENDATION_MISSING — 권장안 C 또는 D."""
    rec_c = "권장안" in policy_text and ("C안" in policy_text or "C." in policy_text)
    rec_d = "권장안" in policy_text and ("D안" in policy_text or "D." in policy_text)
    has_recommendation = rec_c or rec_d or "권장 = C" in policy_text or "권장안 = C" in policy_text
    metrics["has_recommendation"] = has_recommendation
    if not policy_text:
        return PolicyVerdict(False, "FAIL_RECOMMENDATION_MISSING", reasons=["policy doc not found"], metrics=metrics)
    if not has_recommendation:
        return PolicyVerdict(
            False, "FAIL_RECOMMENDATION_MISSING", reasons=["권장안 (C 또는 D) 명시 없음"], metrics=metrics
        )
    return None


def _find_public_section(policy_text: str) -> str:
    # 정책 문서의 "공개 허용 후보" 섹션에 admin path 가 있는지
    m = re.search(r"공개 ?(허용|후보|endpoint)[^\n]*\n(.+?)(?=\n## |\Z)", policy_text, re.DOTALL)
    return m.group(2) if m else ""


def _check_admin_endpoint_public(public_section: str, metrics: dict) -> PolicyVerdict | None:
    """3) FAIL_ADMIN_ENDPOINT_PUBLIC — admin endpoint 가 공개 후보에 들어감."""
    bad_in_public = _forbidden_in_section(public_section)
    if bad_in_public:
        return PolicyVerdict(
            False, "FAIL_ADMIN_ENDPOINT_PUBLIC", reasons=[f"admin_in_public_section:{bad_in_public}"], metrics=metrics
        )
    return None


def _check_registration_code_issue_public(public_section: str, metrics: dict) -> PolicyVerdict | None:
    """4) FAIL_REGISTRATION_CODE_ISSUE_PUBLIC — registration-codes 발급이 공개되면 FAIL."""
    if "/orchestrator/api/v1/local-agents/registration-codes" in public_section:
        return PolicyVerdict(
            False, "FAIL_REGISTRATION_CODE_ISSUE_PUBLIC", reasons=["registration-codes 발급이 공개됨"], metrics=metrics
        )
    return None


def _check_ws_security_layer(public_section: str, policy_text: str, metrics: dict) -> PolicyVerdict | None:
    """5) FAIL_WS_SECURITY_LAYER_MISSING — ws 가 공개되는데 device_token auth 명시 없음."""
    if "/local-agents/ws" in public_section and not (
        re.search(r"device_token.{0,40}auth", policy_text)
        or "auth.{0,8}필수" in policy_text
        or "device_token auth" in policy_text
    ):
        return PolicyVerdict(
            False,
            "FAIL_WS_SECURITY_LAYER_MISSING",
            reasons=["ws 공개 but device_token auth 명시 없음"],
            metrics=metrics,
        )
    return None


def _check_rollback_plan(policy_text: str, nginx_text: str, metrics: dict) -> PolicyVerdict | None:
    """6) FAIL_ROLLBACK_PLAN_MISSING."""
    has_rollback_policy = "rollback" in policy_text.lower() or "롤백" in policy_text
    has_rollback_nginx = "rollback" in nginx_text.lower() or "롤백" in nginx_text
    metrics["has_rollback_in_policy_or_plan"] = has_rollback_policy or has_rollback_nginx
    if not (has_rollback_policy or has_rollback_nginx):
        return PolicyVerdict(False, "FAIL_ROLLBACK_PLAN_MISSING", reasons=["rollback 계획 부재"], metrics=metrics)
    return None


def _check_ws_upgrade_headers(nginx_text: str, metrics: dict) -> PolicyVerdict | None:
    """8) Upgrade/Connection 헤더 유지 확인 (nginx plan). (7=WARN_NGINX_CHANGE_NOT_APPLIED 는 spec 허용이라 검사 없음)"""
    ws_block_has_upgrade = "Upgrade" in nginx_text and "$http_upgrade" in nginx_text
    ws_block_has_connection_upgrade = re.search(r"Connection\s+\"upgrade\"", nginx_text)
    metrics["ws_upgrade_headers_preserved"] = bool(ws_block_has_upgrade and ws_block_has_connection_upgrade)
    if not (ws_block_has_upgrade and ws_block_has_connection_upgrade):
        return PolicyVerdict(
            False,
            "FAIL_WS_SECURITY_LAYER_MISSING",
            reasons=["nginx plan 에 WebSocket Upgrade 헤더 유지 표기 없음"],
            metrics=metrics,
        )
    return None


def judge_policy(
    *,
    policy_doc_path: Path | None = None,
    nginx_plan_path: Path | None = None,
) -> PolicyVerdict:
    # 2026-09-29 STD-08(복잡도) 리팩터: 1)~8) 번호 단계(각각 즉시 FAIL 반환하는 게이트)를
    # _check_*() 함수로 분리 — 순서·조건·문자열 그대로, 첫 실패에서 즉시 반환하는 방식도 동일.
    p_path = policy_doc_path or POLICY_DOC
    n_path = nginx_plan_path or NGINX_PLAN
    policy_text = _read(p_path)
    nginx_text = _read(n_path)
    metrics = {
        "policy_doc_exists": bool(policy_text),
        "nginx_plan_exists": bool(nginx_text),
    }

    result = _check_secret_leak(policy_text, nginx_text, metrics)
    if result:
        return result
    result = _check_recommendation_present(policy_text, metrics)
    if result:
        return result

    public_section = _find_public_section(policy_text)

    result = _check_admin_endpoint_public(public_section, metrics)
    if result:
        return result
    result = _check_registration_code_issue_public(public_section, metrics)
    if result:
        return result
    result = _check_ws_security_layer(public_section, policy_text, metrics)
    if result:
        return result
    result = _check_rollback_plan(policy_text, nginx_text, metrics)
    if result:
        return result
    result = _check_ws_upgrade_headers(nginx_text, metrics)
    if result:
        return result

    # 9) PASS (실제 변경 미적용은 spec 허용 WARN)
    metrics["has_recommendation"] = True
    return PolicyVerdict(True, "PASS_IP_ALLOWLIST_USER_DESKTOP_POLICY_READY", reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", type=Path, default=POLICY_DOC)
    ap.add_argument("--plan", type=Path, default=NGINX_PLAN)
    args = ap.parse_args(argv)
    v = judge_policy(policy_doc_path=args.policy, nginx_plan_path=args.plan)
    print(
        json.dumps(
            {"verdict": v.code, "passed": v.passed, "reasons": v.reasons, "metrics": v.metrics},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
