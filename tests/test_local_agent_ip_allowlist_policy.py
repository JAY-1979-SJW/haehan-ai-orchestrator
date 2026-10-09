"""IP_ALLOWLIST_USER_DESKTOP_POLICY_01 — 12+ 테스트."""

from __future__ import annotations

from pathlib import Path

from tools.audits.agent import audit_local_agent_ip_allowlist_policy as audit

POLICY_DOC = Path("docs/ops/local_agent_ip_allowlist_policy.md")
NGINX_PLAN = Path("docs/ops/local_agent_public_ws_nginx_plan.md")


# ── 1) 문서 존재 ────────────────────────────────────────────────


def test_policy_doc_exists():
    assert POLICY_DOC.exists(), f"missing: {POLICY_DOC}"


def test_nginx_plan_doc_exists():
    assert NGINX_PLAN.exists(), f"missing: {NGINX_PLAN}"


# ── 2) A/B/C/D 비교안 작성 ─────────────────────────────────────


def test_policy_doc_has_all_four_options():
    text = POLICY_DOC.read_text(encoding="utf-8")
    for tag in ("A안", "B안", "C안", "D안"):
        assert tag in text, f"missing option: {tag}"


# ── 3) 권장안 C 또는 D ─────────────────────────────────────────


def test_recommended_option_is_c_or_d():
    text = POLICY_DOC.read_text(encoding="utf-8")
    assert "권장안" in text
    # C 또는 D 가 권장으로 명시
    has_c = "C안" in text and "권장" in text
    has_d = "D안" in text and ("중장기" in text or "권장" in text)
    assert has_c or has_d


# ── 4) admin endpoint 공개 금지 ────────────────────────────────


def test_admin_endpoints_not_in_public_section():
    text = POLICY_DOC.read_text(encoding="utf-8")
    # 공개 허용 후보 섹션 추출
    import re

    m = re.search(r"## 5\. 공개 허용 후보.+?(?=## )", text, re.DOTALL)
    assert m, "공개 허용 후보 섹션 없음"
    public_section = m.group(0)
    # admin 경로 부재 확인
    forbidden = [
        "/orchestrator/admin-web",
        "/orchestrator/api/v1/local-agents/registration-codes",
    ]
    for p in forbidden:
        assert p not in public_section, f"admin path in public: {p}"


# ── 5) registration-codes 발급 endpoint 보호 ──────────────────


def test_registration_codes_endpoint_protected():
    text = POLICY_DOC.read_text(encoding="utf-8")
    # allowlist 유지 섹션에 명시
    import re

    m = re.search(r"## 6\. allowlist 유지.+?(?=## )", text, re.DOTALL)
    assert m, "allowlist 유지 섹션 없음"
    protected = m.group(0)
    assert "/orchestrator/api/v1/local-agents/registration-codes" in protected


# ── 6) register-with-code public 후보 명시 ───────────────────


def test_register_with_code_in_public_candidate():
    text = POLICY_DOC.read_text(encoding="utf-8")
    assert "/orchestrator/api/v1/local-agents/register-with-code" in text
    # 공개 허용 섹션에 들어있어야 함
    import re

    m = re.search(r"## 5\. 공개 허용 후보.+?(?=## )", text, re.DOTALL)
    public_section = m.group(0) if m else ""
    assert "/register-with-code" in public_section


# ── 7) ws public 후보 명시 ───────────────────────────────────


def test_ws_endpoint_in_public_candidate():
    text = POLICY_DOC.read_text(encoding="utf-8")
    import re

    m = re.search(r"## 5\. 공개 허용 후보.+?(?=## )", text, re.DOTALL)
    public_section = m.group(0) if m else ""
    assert "/orchestrator/api/v1/local-agents/ws" in public_section


# ── 8) rollback plan 존재 ───────────────────────────────────


def test_rollback_plan_in_policy_doc():
    text = POLICY_DOC.read_text(encoding="utf-8")
    assert "rollback" in text.lower() or "롤백" in text


def test_rollback_in_nginx_plan():
    text = NGINX_PLAN.read_text(encoding="utf-8")
    assert "rollback" in text.lower() or "롤백" in text


# ── 9) token/secret 출력 금지 ─────────────────────────────


def test_no_real_secrets_in_policy_doc():
    text = POLICY_DOC.read_text(encoding="utf-8")
    leaks = audit._find_secrets_in_text(text)
    # 운영 secret 값이 들어가면 leak. 문서 키워드는 OK.
    assert leaks == [], f"secret-like value in policy doc: {leaks}"


def test_no_real_secrets_in_nginx_plan():
    text = NGINX_PLAN.read_text(encoding="utf-8")
    leaks = audit._find_secrets_in_text(text)
    assert leaks == [], f"secret-like value in nginx plan: {leaks}"


# ── 10) nginx websocket header 유지 ─────────────────────────


def test_nginx_plan_preserves_websocket_upgrade_headers():
    text = NGINX_PLAN.read_text(encoding="utf-8")
    assert "Upgrade" in text and "$http_upgrade" in text
    import re

    assert re.search(r"Connection\s+\"upgrade\"", text), "Connection upgrade 헤더 명시 없음"
    assert "proxy_read_timeout" in text


# ── 11) device_token auth 보안 layer 명시 ──────────────────


def test_ws_security_layer_device_token_auth_mentioned():
    text = POLICY_DOC.read_text(encoding="utf-8")
    # ws 공개 시 device_token auth 가 보안 layer 인 점 명시
    assert "device_token" in text
    assert "auth" in text.lower()
    # 4401 close 정책
    assert "4401" in text


# ── 12) audit verdict ───────────────────────────────────────


def test_audit_pass_on_real_docs():
    v = audit.judge_policy()
    assert v.code == "PASS_IP_ALLOWLIST_USER_DESKTOP_POLICY_READY", v.reasons


def test_audit_fail_recommendation_missing(tmp_path):
    p = tmp_path / "policy.md"
    p.write_text("## 정책\n내용만 있고 권장안 없음", encoding="utf-8")
    n = tmp_path / "plan.md"
    n.write_text('rollback Upgrade $http_upgrade Connection "upgrade" proxy_read_timeout', encoding="utf-8")
    v = audit.judge_policy(policy_doc_path=p, nginx_plan_path=n)
    assert v.code == "FAIL_RECOMMENDATION_MISSING"


def test_audit_fail_admin_endpoint_public(tmp_path):
    """공개 섹션에 admin endpoint 가 있으면 FAIL."""
    p = tmp_path / "policy.md"
    p.write_text(
        "권장안: C안\n\n"
        "## 5. 공개 허용 후보\n"
        "- /orchestrator/admin-web/ 공개\n"
        "- /orchestrator/api/v1/local-agents/ws (device_token auth, 4401)\n\n"
        "## 6. allowlist 유지\n- 없음\n\n"
        "## rollback\n- 롤백 절차\n",
        encoding="utf-8",
    )
    n = tmp_path / "plan.md"
    n.write_text('Upgrade $http_upgrade Connection "upgrade" rollback proxy_read_timeout', encoding="utf-8")
    v = audit.judge_policy(policy_doc_path=p, nginx_plan_path=n)
    assert v.code == "FAIL_ADMIN_ENDPOINT_PUBLIC"


def test_audit_fail_registration_code_issue_public(tmp_path):
    p = tmp_path / "policy.md"
    p.write_text(
        "권장안: C안\n\n"
        "## 5. 공개 허용 후보\n"
        "- /orchestrator/api/v1/local-agents/registration-codes (4401 device_token auth)\n\n"
        "## 6. allowlist\n- 없음\n\n## rollback\n- 롤백",
        encoding="utf-8",
    )
    n = tmp_path / "plan.md"
    n.write_text('Upgrade $http_upgrade Connection "upgrade" rollback proxy_read_timeout', encoding="utf-8")
    v = audit.judge_policy(policy_doc_path=p, nginx_plan_path=n)
    # admin endpoint check 가 먼저 fail 또는 registration-codes public 이 둘 다 잡음
    assert v.code in ("FAIL_REGISTRATION_CODE_ISSUE_PUBLIC", "FAIL_ADMIN_ENDPOINT_PUBLIC")


def test_audit_fail_rollback_missing(tmp_path):
    p = tmp_path / "policy.md"
    p.write_text(
        "권장안: C안\n\n"
        "## 5. 공개 허용 후보\n"
        "- /orchestrator/api/v1/local-agents/ws device_token auth 4401\n\n"
        "## 6. allowlist 유지\n- /orchestrator/admin-web/\n",
        encoding="utf-8",
    )
    n = tmp_path / "plan.md"
    n.write_text('Upgrade $http_upgrade Connection "upgrade" proxy_read_timeout', encoding="utf-8")
    v = audit.judge_policy(policy_doc_path=p, nginx_plan_path=n)
    assert v.code == "FAIL_ROLLBACK_PLAN_MISSING"


# ── 13) 회귀 가드 ──────────────────────────────────────────


def test_regression_connection_diagnostics_imports():
    from core.agent_runtime.connection import connection_diagnostics as cd

    assert hasattr(cd, "normalize_ws_url")
    assert hasattr(cd, "build_diagnostics")


def test_regression_proxy_checklist_doc_exists():
    """직전 공정의 proxy checklist 가 본 공정 후에도 유지되는지."""
    p = Path("docs/ops/local_agent_proxy_checklist.md")
    assert p.exists()


def test_regression_local_agent_router_imports():
    from ai_orchestrator.agent_hub.router import registration as reg
    from ai_orchestrator.agent_hub.router import root as r

    assert hasattr(r, "local_agent_router")
    assert hasattr(reg, "register_with_code")
