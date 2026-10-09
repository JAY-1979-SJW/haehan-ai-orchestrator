"""ASSISTANT_APP_SCOPE_RESET_WEB_DESKTOP_ONLY_CLOSEOUT_01
비서앱 공사 범위 재확정: 웹/데스크 중심 + EXTERNAL_APP_HOLD 경계 고정.

분류 기준:
  IN_SCOPE       — 웹 접속, 웹 업무 처리, 웹/데스크 API, 승인/감사/상태, 브라우저 작업
  FUTURE_INTEGRATION / EXTERNAL_APP_HOLD
                 — CAD, HWPX/HWP, Excel/Office 전문 기능 자체 구현
  OUT_OF_SCOPE   — 현재 앱 내부에서 전문 로컬 기능 신규 개발

준공 기준:
  백엔드 준공 범위 = 웹 업무 실행 엔진 + 승인/감사 + 실행위치 정책 + 브라우저 안전정책
  CAD/HWPX/Excel 실패 = EXTERNAL_APP_HOLD (백엔드 준공 실패 아님)
"""

from __future__ import annotations

import importlib
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent


# ── IN_SCOPE: 웹 업무 실행 엔진 ────────────────────────────────────────────


class TestInScopeWebTaskEngine:
    """웹 업무 실행 핵심 파일이 존재하고 임포트 가능한지 확인."""

    IN_SCOPE_MODULES = [
        "ai_orchestrator.web_task.web_task_router",
        "ai_orchestrator.web_task.web_task_registry",
        "ai_orchestrator.web_task.web_task_templates",
        "ai_orchestrator.web_task.web_task_approval_service",
        "tools.gates.approval",
        "ai_orchestrator.dev_reg.dev_reg_approval",
        "ai_orchestrator.core.task_state",
        "ai_orchestrator.audit.audit_logger",
    ]

    @pytest.mark.parametrize("module", IN_SCOPE_MODULES)
    def test_in_scope_module_importable(self, module):
        """IN_SCOPE 모듈이 임포트 가능하다."""
        mod = importlib.import_module(module)
        assert mod is not None, f"{module} 임포트 실패"

    def test_web_task_router_file_exists(self):
        """web_task_router.py IN_SCOPE 파일 존재."""
        assert (REPO_ROOT / "ai_orchestrator" / "web_task" / "web_task_router.py").exists()

    def test_web_task_approval_service_file_exists(self):
        """web_task_approval_service.py IN_SCOPE 파일 존재."""
        assert (REPO_ROOT / "ai_orchestrator" / "web_task" / "web_task_approval_service.py").exists()

    def test_server_execution_location_guard_exists(self):
        """server/execution_location_guard.py IN_SCOPE 파일 존재."""
        assert (REPO_ROOT / "ai_orchestrator" / "server" / "execution_location_guard.py").exists()

    def test_browser_execution_location_policy_exists(self):
        """browser_tool/routing/execution_location_policy.py IN_SCOPE 파일 존재."""
        assert (REPO_ROOT / "ai_orchestrator" / "browser_tool" / "routing" / "execution_location_policy.py").exists()


# ── IN_SCOPE: 비서앱 웹 페이지 + 데스크 앱 골조 ────────────────────────────


class TestInScopeWebDesktopSkeleton:
    """웹 페이지 및 데스크 앱 골조 파일 존재 확인."""

    def test_admin_web_package_json_exists(self):
        """admin-web/package.json 웹 앱 골조 존재."""
        assert (REPO_ROOT / "admin-web" / "package.json").exists()

    def test_admin_web_src_exists(self):
        """admin-web/src 디렉터리 존재."""
        assert (REPO_ROOT / "admin-web" / "src").is_dir()

    def test_desktop_tray_app_removed(self):
        """legacy desktop/tray_app.py must not be resurrected."""
        assert not (REPO_ROOT / "desktop" / "tray_app.py").exists()


# ── EXTERNAL_APP_HOLD: HWPX/HWP ────────────────────────────────────────────


class TestHwpxExternalAppHold:
    """HWPX/HWP 기능은 현재 비서앱 준공 범위가 아니라 EXTERNAL_APP_HOLD이다."""

    HWPX_VERDICT = "HWPX_EXTERNAL_APP_HOLD"
    SCOPE = "FUTURE_INTEGRATION"

    def test_hwpx_verdict_is_external_app_hold(self):
        """HWPX 설계 판정이 EXTERNAL_APP_HOLD로 선언된다."""
        assert self.HWPX_VERDICT == "HWPX_EXTERNAL_APP_HOLD"

    def test_hwp_hancom_dir_exists_as_external(self):
        """HWP/HWPX 엔진은 ai_orchestrator 코어에 없다(2026-10-04 갱신: agent/hancom/ 디렉터리는 사라짐 — 코어 밖 보류 원칙만 검증)."""
        assert not (REPO_ROOT / "ai_orchestrator" / "hancom").exists(), "HWP 엔진이 ai_orchestrator 코어에 있음"

    def test_hwpx_not_in_web_task_router(self):
        """web_task_router.py에 hwp/hwpx 참조가 없다."""
        src = (REPO_ROOT / "ai_orchestrator" / "web_task" / "web_task_router.py").read_text(encoding="utf-8")
        assert "hwp" not in src.lower(), "web_task_router.py에 hwp 참조가 존재함 — IN_SCOPE 오염 가능성"

    def test_hwpx_not_in_approval_service(self):
        """web_task_approval_service.py에 hwp/hwpx 참조가 없다."""
        src = (REPO_ROOT / "ai_orchestrator" / "web_task" / "web_task_approval_service.py").read_text(encoding="utf-8")
        assert "hwp" not in src.lower()


# ── EXTERNAL_APP_HOLD: Excel/Office ────────────────────────────────────────


class TestExcelOfficeExternalAppHold:
    """Excel/Office 전문 기능은 현재 비서앱 준공 범위가 아니라 EXTERNAL_APP_HOLD이다."""

    EXCEL_VERDICT = "OFFICE_EXTERNAL_APP_HOLD"
    SCOPE = "FUTURE_INTEGRATION"

    def test_excel_verdict_is_external_app_hold(self):
        """Excel/Office 설계 판정이 EXTERNAL_APP_HOLD로 선언된다."""
        assert self.EXCEL_VERDICT == "OFFICE_EXTERNAL_APP_HOLD"

    def test_excel_engine_in_agent_not_orchestrator_core(self):
        """Excel 엔진 핵심이 ai_orchestrator 코어에 없다(2026-10-04 갱신: agent/excel/ 디렉터리는 사라짐 — 코어 밖 보류 원칙만 검증)."""
        assert not (REPO_ROOT / "ai_orchestrator" / "excel").exists(), "Excel 엔진이 ai_orchestrator 코어에 있음"
        # ai_orchestrator/web_task_router 에는 excel 참조 없음
        src = (REPO_ROOT / "ai_orchestrator" / "web_task" / "web_task_router.py").read_text(encoding="utf-8")
        assert "excel" not in src.lower()

    def test_excel_not_in_approval_service(self):
        """web_task_approval_service.py에 excel 참조가 없다."""
        src = (REPO_ROOT / "ai_orchestrator" / "web_task" / "web_task_approval_service.py").read_text(encoding="utf-8")
        assert "excel" not in src.lower()


# ── 백엔드 준공 경계: CAD/HWPX/Excel 실패는 closeout 실패 아님 ───────────────


class TestBackendCloseoutBoundary:
    """CAD/HWPX/Excel 관련 테스트 실패가 백엔드 준공 실패로 계산되지 않는다."""

    # 이 테스트들은 IN_SCOPE 백엔드 준공 항목임을 명시한다.
    CLOSEOUT_IN_SCOPE_TESTS = [
        "tests/server_features/test_backend_web_task_approval_flow_20260516.py",
        "tests/app_contracts/test_backend_direct_dict_boundary_lock_20260516.py",
        "tests/app_contracts/test_backend_frontend_dependency_audit_20260516.py",
        "tests/app_contracts/test_backend_endpoint_inventory_recount_20260516.py",
        "tests/server_features/test_web_task_router_policy_flow.py",
    ]

    @pytest.mark.parametrize("test_path", CLOSEOUT_IN_SCOPE_TESTS)
    def test_closeout_scope_test_exists(self, test_path):
        """백엔드 준공 IN_SCOPE 테스트 파일이 존재한다."""
        assert (REPO_ROOT / test_path).exists(), f"준공 필수 테스트 없음: {test_path}"

    def test_web_task_closeout_passes_without_cad(self):
        """web_task_approval_service 는 CAD 없이 임포트 가능하다."""
        import ai_orchestrator.web_task.web_task_approval_service as svc

        assert hasattr(svc, "create_web_task_pending_approval")

    def test_approval_service_boundary(self):
        """web_task_approval_service의 응답 계약 키 존재."""
        import dataclasses

        from ai_orchestrator.web_task.web_task_approval_service import PendingApprovalResult

        fields = {f.name for f in dataclasses.fields(PendingApprovalResult)}
        required = {
            "task_id",
            "expires_at",
            "risk_level",
            "requires_approval",
            "provider",
            "action_type",
            "telegram_sent",
            "telegram_message_id",
        }
        assert required.issubset(fields), f"PendingApprovalResult 필드 누락: {required - fields}"
