"""HAEHAN_SINGLE_EXE_MODE_CONSOLIDATION_SPEC_01 회귀 테스트.

설계 공정 검증:
- 설계서 존재
- 단일 exe 원칙
- Tray/Admin 모드 정의
- 두 앱 기능 맵
- role guard 정책
- deprecated 분류
- 보안 정책
- 단계별 구현 계획
- 즉시 삭제 금지
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SPEC = ROOT / "docs/design/HAEHAN_SINGLE_EXE_MODE_CONSOLIDATION_SPEC_01.md"
AUDIT = ROOT / "tools/audits/agent/audit_haehan_single_exe_mode_consolidation_spec.py"


def _spec_text() -> str:
    assert SPEC.exists(), f"설계서 없음: {SPEC}"
    return SPEC.read_text(encoding="utf-8")


# ── 존재 ──────────────────────────────────────────────────────────────────

def test_spec_exists():
    assert SPEC.exists()


def test_audit_exists():
    assert AUDIT.exists()


def test_spec_has_minimum_size():
    text = _spec_text()
    assert len(text) > 5000, f"설계서가 너무 짧음: {len(text)} bytes"


# ── 단일 exe 원칙 ─────────────────────────────────────────────────────────

def test_single_exe_principle():
    text = _spec_text()
    assert "HaehanAI.exe" in text
    assert "단일 exe" in text


def test_two_app_strategy_resolved():
    text = _spec_text()
    assert "A안 통합" in text


# ── Tray Mode ─────────────────────────────────────────────────────────────

def test_tray_mode_defined():
    text = _spec_text()
    assert "Tray Mode" in text
    assert "wizard" in text
    assert "트레이" in text


def test_tray_mode_heartbeat():
    text = _spec_text()
    assert "heartbeat" in text


def test_tray_mode_registration_wizard():
    text = _spec_text()
    assert "wizard" in text
    assert "등록" in text


# ── Admin Mode ────────────────────────────────────────────────────────────

def test_admin_mode_defined():
    text = _spec_text()
    assert "Admin Mode" in text
    assert "--admin" in text
    assert "pywebview" in text


def test_admin_mode_lazy_load():
    text = _spec_text()
    assert "lazy load" in text


def test_admin_mode_react_ui():
    text = _spec_text()
    assert "React" in text
    assert "ui_dist" in text


# ── 두 앱 기능 맵 ────────────────────────────────────────────────────────

def test_feature_map_exists():
    text = _spec_text()
    assert "기능 맵" in text


def test_feature_map_categorization():
    text = _spec_text()
    assert "흡수" in text
    assert "유지" in text
    assert "폐기" in text


def test_local_agent_modules_listed():
    text = _spec_text()
    for mod in ["agent.py", "gui_tray.py", "token_store", "registration_client"]:
        assert mod in text, f"local_agent {mod} 미언급"


def test_desktop_modules_listed():
    text = _spec_text()
    for mod in ["webview_app_pywebview", "local_server", "ui_dist"]:
        assert mod in text, f"desktop {mod} 미언급"


# ── role guard ────────────────────────────────────────────────────────────

def test_role_guard_policy():
    text = _spec_text()
    assert "role guard" in text
    assert "admin/owner" in text or "admin, owner" in text


def test_role_guard_layers():
    text = _spec_text()
    # 최소 4개 guard 위치
    layers = ["트레이", "CLI", "미들웨어", "WS", "사이드바"]
    matched = sum(1 for l in layers if l in text)
    assert matched >= 4, f"guard layer 부족: {matched}/5"


def test_local_only_bypass_forbidden():
    text = _spec_text()
    assert "bypass 금지" in text or "bypass" in text.lower()


# ── deprecated 분류 ──────────────────────────────────────────────────────

def test_deprecated_marked():
    text = _spec_text()
    assert "deprecated" in text.lower() or "DEPRECATED" in text


def test_agent_spec_marked_deprecated():
    text = _spec_text()
    assert "HaehanAI-Agent.spec" in text


def test_immediate_delete_forbidden():
    text = _spec_text()
    assert ("즉시 삭제 금지" in text
            or "즉시 폐기 금지" in text
            or "즉시 Agent.exe 삭제" in text)


def test_cleanup_in_separate_process():
    text = _spec_text()
    assert "cleanup 공정" in text or "별도 cleanup" in text


# ── 보안 정책 ────────────────────────────────────────────────────────────

def test_security_device_token():
    text = _spec_text()
    assert "device_token" in text
    assert "원문" in text and "금지" in text


def test_security_registration_code():
    text = _spec_text()
    assert "registration_code" in text


def test_security_openai_proxy():
    text = _spec_text()
    assert "server proxy" in text


def test_security_redaction():
    text = _spec_text()
    assert "redaction" in text


def test_security_cookie_forbidden():
    text = _spec_text()
    assert "cookie" in text.lower() and "금지" in text


# ── lifecycle ────────────────────────────────────────────────────────────

def test_lifecycle_defined():
    text = _spec_text()
    assert "lifecycle" in text


def test_lifecycle_steps():
    text = _spec_text()
    for step in ["consent", "token 로드", "local_server", "heartbeat"]:
        assert step in text, f"lifecycle {step} 미언급"


def test_lifecycle_single_instance():
    text = _spec_text()
    assert "단일 인스턴스" in text


# ── build policy ────────────────────────────────────────────────────────

def test_build_policy_onefolder():
    text = _spec_text()
    assert "onefolder" in text


def test_build_policy_playwright_bundled():
    text = _spec_text()
    assert "playwright" in text.lower() or "Playwright" in text


def test_build_policy_ui_dist_included():
    text = _spec_text()
    assert "ui_dist" in text


# ── 위험 분석 ────────────────────────────────────────────────────────────

def test_risk_analysis():
    text = _spec_text()
    assert "위험 분석" in text


def test_risk_exe_size():
    text = _spec_text()
    assert "exe 크기" in text


def test_risk_migration():
    text = _spec_text()
    assert "migration" in text or "마이그레이션" in text


def test_risk_role_guard_missing():
    text = _spec_text()
    assert "role guard" in text and "누락" in text


# ── 단계별 구현 계획 ──────────────────────────────────────────────────────

def test_next_plan_launcher_foundation():
    text = _spec_text()
    assert "HAEHAN_SINGLE_EXE_LAUNCHER_FOUNDATION_01" in text


def test_next_plan_tray_merge():
    text = _spec_text()
    assert "HAEHAN_TRAY_REGISTRATION_MERGE_01" in text


def test_next_plan_admin_webview():
    text = _spec_text()
    assert "HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01" in text


def test_next_plan_build():
    text = _spec_text()
    assert "HAEHAN_SINGLE_EXE_BUILD_01" in text


def test_next_plan_deprecation():
    text = _spec_text()
    assert "HAEHAN_AGENT_EXE_DEPRECATION_01" in text


def test_next_plan_field_test():
    text = _spec_text()
    assert "HAEHAN_SINGLE_EXE_USER_FIELD_TEST_01" in text


# ── OUT_OF_SCOPE ─────────────────────────────────────────────────────────

def test_out_of_scope_listed():
    text = _spec_text()
    assert "OUT_OF_SCOPE" in text or "본 공정에서 하지 않음" in text


def test_out_of_scope_no_rebuild():
    text = _spec_text()
    assert "PyInstaller 재빌드" in text


# ── 누출 검사 ────────────────────────────────────────────────────────────

def test_no_secret_value_leak():
    """설계서에 실제 토큰/키 값이 적혀있지 않은지 확인."""
    text = _spec_text()
    # 정책/예시 컨텍스트는 허용, 실제 값(sk-로 시작하는 OpenAI 키 등)은 금지
    bad_patterns = ["sk-proj-", "sk-ant-", "Bearer eyJ"]
    for pat in bad_patterns:
        assert pat not in text, f"실제 secret 의심 패턴: {pat}"


def test_no_personal_credential():
    text = _spec_text()
    # 실제 사용자 ID/email 가 적혀있는지
    assert "skyjwsin@" not in text
    assert "@gmail.com" not in text
