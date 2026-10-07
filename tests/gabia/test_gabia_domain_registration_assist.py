"""Gabia 도메인 개설 보조 모듈 테스트."""
from __future__ import annotations


# ── 1. normalize_domain_candidate ────────────────────────────────────────────

def test_normalize_strips_protocol():
    from scripts.gabia.domain_assist import normalize_domain_candidate
    r = normalize_domain_candidate("https://example.co.kr/path?q=1")
    assert r["normalized"] == "example.co.kr"
    assert r["ok"] is True


def test_normalize_strips_www():
    from scripts.gabia.domain_assist import normalize_domain_candidate
    r = normalize_domain_candidate("www.haehan-ai.kr")
    assert r["label"] == "haehan-ai"
    assert r["tld"] == ".kr"
    assert r["ok"] is True


def test_normalize_lowercases():
    from scripts.gabia.domain_assist import normalize_domain_candidate
    r = normalize_domain_candidate("MyDomain.KR")
    assert r["normalized"] == "mydomain.kr"


def test_normalize_korean_warning():
    from scripts.gabia.domain_assist import normalize_domain_candidate
    r = normalize_domain_candidate("한글도메인.kr")
    assert any("한글" in w or "punycode" in w for w in r["warnings"])


def test_normalize_invalid_chars_error():
    from scripts.gabia.domain_assist import normalize_domain_candidate
    r = normalize_domain_candidate("invalid_name.kr")
    assert r["ok"] is False
    assert r["errors"]


def test_normalize_leading_hyphen_error():
    from scripts.gabia.domain_assist import normalize_domain_candidate
    r = normalize_domain_candidate("-bad.kr")
    assert r["ok"] is False


def test_normalize_unknown_tld_warning():
    from scripts.gabia.domain_assist import normalize_domain_candidate
    r = normalize_domain_candidate("example.xyz")
    assert any("TLD" in w for w in r["warnings"])


def test_normalize_co_kr_preferred():
    from scripts.gabia.domain_assist import normalize_domain_candidate
    r = normalize_domain_candidate("test.co.kr")
    assert r["tld"] == ".co.kr"
    assert r["label"] == "test"


# ── 2. build_domain_registration_draft ───────────────────────────────────────

def test_draft_final_action_user_direct():
    from scripts.gabia.domain_assist import build_domain_registration_draft
    draft = build_domain_registration_draft({"domain": "haehan-ai", "tld": ".kr"})
    assert draft["final_action"] == "USER_DIRECT_REQUIRED"


def test_draft_availability_check_required():
    from scripts.gabia.domain_assist import build_domain_registration_draft
    draft = build_domain_registration_draft({"domain": "testdomain", "tld": ".com"})
    assert draft["availability"] == "CHECK_REQUIRED"


def test_draft_contains_gate_policy():
    from scripts.gabia.domain_assist import build_domain_registration_draft
    draft = build_domain_registration_draft({"domain": "x", "tld": ".kr"})
    assert "gate_policy" in draft
    assert draft["gate_policy"]["login_session_cookie"] == "BLOCKED"


def test_draft_years_clamped():
    from scripts.gabia.domain_assist import build_domain_registration_draft
    draft = build_domain_registration_draft({"domain": "x", "tld": ".kr", "years": 99})
    assert draft["registration_years"] == 10


# ── 3. evaluate_domain_registration_gate ─────────────────────────────────────

def test_gate_draft_allowed():
    from scripts.gabia.domain_assist import evaluate_domain_registration_gate
    g = evaluate_domain_registration_gate("draft")
    assert g["decision"] == "ALLOWED"


def test_gate_apply_dns_approval_required():
    from scripts.gabia.domain_assist import evaluate_domain_registration_gate
    g = evaluate_domain_registration_gate("apply_dns")
    assert g["requires_approval"] is True


def test_gate_final_register_user_direct():
    from scripts.gabia.domain_assist import evaluate_domain_registration_gate
    g = evaluate_domain_registration_gate("final_register")
    assert "USER_DIRECT" in g["decision"]


def test_gate_payment_user_direct():
    from scripts.gabia.domain_assist import evaluate_domain_registration_gate
    g = evaluate_domain_registration_gate("payment")
    assert "USER_DIRECT" in g["decision"]


def test_gate_login_blocked():
    from scripts.gabia.domain_assist import evaluate_domain_registration_gate
    g = evaluate_domain_registration_gate("login")
    assert g["is_blocked_or_restricted"] is True


def test_gate_session_blocked():
    from scripts.gabia.domain_assist import evaluate_domain_registration_gate
    g = evaluate_domain_registration_gate("session")
    assert g["is_blocked_or_restricted"] is True


def test_gate_cookie_blocked():
    from scripts.gabia.domain_assist import evaluate_domain_registration_gate
    g = evaluate_domain_registration_gate("cookie")
    assert g["is_blocked_or_restricted"] is True


def test_gate_password_blocked():
    from scripts.gabia.domain_assist import evaluate_domain_registration_gate
    g = evaluate_domain_registration_gate("password")
    assert g["is_blocked_or_restricted"] is True


def test_gate_otp_blocked():
    from scripts.gabia.domain_assist import evaluate_domain_registration_gate
    g = evaluate_domain_registration_gate("otp")
    assert g["is_blocked_or_restricted"] is True


# ── 4. data/sessions 경로 접근 금지 검증 ────────────────────────────────────

def test_domain_assist_does_not_read_session_files():
    """domain_assist 모듈 소스에 session 파일 read 호출이 없어야 한다."""
    import ast
    from pathlib import Path
    src = Path("scripts/gabia/domain_assist.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # open("data/sessions/...") 형태 감지
            if isinstance(func, ast.Name) and func.id == "open":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and "sessions" in str(arg.value):
                        raise AssertionError(f"session file open detected: {arg.value}")
            # Path(...).read_text() 체인 감지는 간단히 소스 스캔으로 보완
    assert "read_text" not in src or "sessions" not in src.split("read_text")[0].split("\n")[-1]


# ── 5. router domain-assist import smoke ────────────────────────────────────

def test_router_domain_assist_import():
    from scripts.gabia import router  # noqa: F401
    assert hasattr(router, "domain_assist")


# ── 6. suggest_tld_candidates ────────────────────────────────────────────────

def test_suggest_tld_candidates_contains_check_required():
    from scripts.gabia.domain_assist import suggest_tld_candidates
    candidates = suggest_tld_candidates("haehan-ai")
    assert len(candidates) > 0
    for c in candidates:
        assert c["availability"] == "CHECK_REQUIRED"


# ── 7. gate/audit regression ─────────────────────────────────────────────────

def test_forbidden_import_gate_zero():
    import json
    from pathlib import Path
    report_path = Path("data/codebase_layer_audit_latest.json")
    if not report_path.exists():
        return
    d = json.loads(report_path.read_text(encoding="utf-8"))
    fi = [i for i in d.get("issues", []) if i["code"] == "FORBIDDEN_IMPORT"]
    assert len(fi) == 0, f"FORBIDDEN_IMPORT violations: {fi}"


def test_security_pattern_gate_zero():
    import json
    from pathlib import Path
    report_path = Path("data/codebase_layer_audit_latest.json")
    if not report_path.exists():
        return
    d = json.loads(report_path.read_text(encoding="utf-8"))
    sp = [i for i in d.get("issues", []) if i["code"] == "SECURITY_PATTERN"]
    assert len(sp) == 0, f"SECURITY_PATTERN violations: {sp}"
