"""Phase 1-F adapter skeleton only 테스트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1F_ADAPTER_SKELETON_ONLY_01

검증 범위:
- package/module import 가능
- SkeletonOnlyAdapterError / AdapterSkeletonMetadata 존재 및 동작
- inbox / task_approval adapter skeleton 구조
- path template 정확성 (double slash 없음, Flask/FastAPI 표기)
- 금지 import (HTTP/DB/subprocess/route decorator) 없음
- adapt 함수 호출 시 SkeletonOnlyAdapterError raise
- Phase 1-E/D/B 일관성, 감사 스크립트 verdict

절대 금지:
    실제 HTTP 호출 금지 / DB write 금지 / secret 값 출력 금지
    5050 route 수정 금지 / 8400 handler 수정 금지
    route 연결 금지 / nginx 변경 금지 / 서버 반영 금지
"""
from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ── import ────────────────────────────────────────────────────────────────────

import backend.compat.legacy_5050.adapters.common as _common
import backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter as _inbox
import backend.compat.legacy_5050.adapters.task_approval_adapter as _task


# ═════════════════════════════════════════════════════════════════════════════
# 1. Package import 가능
# ═════════════════════════════════════════════════════════════════════════════

class TestPackageImport:
    def test_compat_package_importable(self):
        import backend.compat

    def test_legacy_5050_package_importable(self):
        import backend.compat.legacy_5050

    def test_adapters_package_importable(self):
        import backend.compat.legacy_5050.adapters

    def test_common_module_importable(self):
        import backend.compat.legacy_5050.adapters.common

    def test_inbox_module_importable(self):
        import backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter

    def test_task_approval_module_importable(self):
        import backend.compat.legacy_5050.adapters.task_approval_adapter


# ═════════════════════════════════════════════════════════════════════════════
# 2. common.py 상수 및 클래스
# ═════════════════════════════════════════════════════════════════════════════

class TestCommonConstants:
    def test_phase_is_phase_1f(self):
        assert _common.PHASE == "PHASE_1F"

    def test_skeleton_only_true(self):
        assert _common.SKELETON_ONLY is True

    def test_implementation_allowed_false(self):
        assert _common.IMPLEMENTATION_ALLOWED is False

    def test_live_call_allowed_false(self):
        assert _common.LIVE_CALL_ALLOWED is False

    def test_side_effect_allowed_false(self):
        assert _common.SIDE_EFFECT_ALLOWED is False

    def test_db_write_allowed_false(self):
        assert _common.DB_WRITE_ALLOWED is False

    def test_secret_value_allowed_false(self):
        assert _common.SECRET_VALUE_ALLOWED is False

    def test_route_handler_change_allowed_false(self):
        assert _common.ROUTE_HANDLER_CHANGE_ALLOWED is False

    def test_server_apply_allowed_false(self):
        assert _common.SERVER_APPLY_ALLOWED is False

    def test_nginx_change_allowed_false(self):
        assert _common.NGINX_CHANGE_ALLOWED is False

    def test_skeleton_only_adapter_error_exists(self):
        assert hasattr(_common, "SkeletonOnlyAdapterError")

    def test_adapter_skeleton_metadata_exists(self):
        assert hasattr(_common, "AdapterSkeletonMetadata")


# ═════════════════════════════════════════════════════════════════════════════
# 3. SkeletonOnlyAdapterError 동작
# ═════════════════════════════════════════════════════════════════════════════

class TestSkeletonOnlyAdapterError:
    def test_is_subclass_of_not_implemented_error(self):
        assert issubclass(_common.SkeletonOnlyAdapterError, NotImplementedError)

    def test_raise_with_adapter_id(self):
        with pytest.raises(_common.SkeletonOnlyAdapterError) as exc_info:
            raise _common.SkeletonOnlyAdapterError(adapter_id="TEST_ID")
        assert "TEST_ID" in str(exc_info.value)

    def test_default_message_contains_phase_1f(self):
        err = _common.SkeletonOnlyAdapterError(adapter_id="X")
        assert "PHASE_1F" in str(err)

    def test_default_message_contains_no_live_call(self):
        err = _common.SkeletonOnlyAdapterError(adapter_id="X")
        assert "no live call" in str(err)

    def test_custom_message_respected(self):
        err = _common.SkeletonOnlyAdapterError(adapter_id="X", message="custom msg")
        assert "custom msg" in str(err)

    def test_adapter_id_attribute(self):
        err = _common.SkeletonOnlyAdapterError(adapter_id="MY_ADAPTER")
        assert err.adapter_id == "MY_ADAPTER"


# ═════════════════════════════════════════════════════════════════════════════
# 4. AdapterSkeletonMetadata 동작
# ═════════════════════════════════════════════════════════════════════════════

class TestAdapterSkeletonMetadata:
    def _make_meta(self, **overrides):
        defaults = dict(
            phase="PHASE_1F",
            adapter_id="TEST",
            legacy_method="POST",
            legacy_path_template="/test/<id>",
            fastapi_method="POST",
            fastapi_path_template="/test/{id}",
            adapter_type="TEST_ADAPTER",
            risk_level="LOW",
            required_feature_flag="TEST_FLAG",
            required_safety_gate="TEST_GATE",
        )
        defaults.update(overrides)
        return _common.AdapterSkeletonMetadata(**defaults)

    def test_skeleton_only_default_true(self):
        meta = self._make_meta()
        assert meta.skeleton_only is True

    def test_implementation_allowed_default_false(self):
        meta = self._make_meta()
        assert meta.implementation_allowed is False

    def test_live_call_allowed_default_false(self):
        meta = self._make_meta()
        assert meta.live_call_allowed is False

    def test_db_write_allowed_default_false(self):
        meta = self._make_meta()
        assert meta.db_write_allowed is False

    def test_as_dict_returns_dict(self):
        meta = self._make_meta()
        d = meta.as_dict()
        assert isinstance(d, dict)
        assert d["phase"] == "PHASE_1F"
        assert d["skeleton_only"] is True


# ═════════════════════════════════════════════════════════════════════════════
# 5. inbox_email_fetch_adapter 상수
# ═════════════════════════════════════════════════════════════════════════════

class TestInboxAdapterConstants:
    def test_adapter_id(self):
        assert _inbox.ADAPTER_ID == "INBOX_EMAIL_FETCH_ADAPTER"

    def test_legacy_method_post(self):
        assert _inbox.LEGACY_METHOD == "POST"

    def test_legacy_path_template(self):
        assert _inbox.LEGACY_PATH_TEMPLATE == "/api/v1/inbox/email/fetch"

    def test_fastapi_method_post(self):
        assert _inbox.FASTAPI_METHOD == "POST"

    def test_fastapi_path_template(self):
        assert _inbox.FASTAPI_PATH_TEMPLATE == "/api/v1/inbox/email/fetch"

    def test_no_double_slash_legacy(self):
        assert "//" not in _inbox.LEGACY_PATH_TEMPLATE

    def test_no_double_slash_fastapi(self):
        assert "//" not in _inbox.FASTAPI_PATH_TEMPLATE

    def test_risk_level_medium(self):
        assert _inbox.RISK_LEVEL == "MEDIUM"

    def test_feature_flag(self):
        assert _inbox.REQUIRED_FEATURE_FLAG == "LEGACY_5050_INBOX_EMAIL_FETCH_ADAPTER_ENABLED"

    def test_safety_gate(self):
        assert _inbox.REQUIRED_SAFETY_GATE == "NO_LIVE_EMAIL_FETCH_IN_TESTS"

    def test_no_forbidden_path_execute(self):
        assert "execute" not in _inbox.LEGACY_PATH_TEMPLATE

    def test_no_forbidden_path_webhook(self):
        assert "webhook" not in _inbox.LEGACY_PATH_TEMPLATE

    def test_no_forbidden_path_dashboard(self):
        assert "/dashboard" not in _inbox.LEGACY_PATH_TEMPLATE


# ═════════════════════════════════════════════════════════════════════════════
# 6. inbox metadata 함수
# ═════════════════════════════════════════════════════════════════════════════

class TestInboxMetadata:
    def test_get_adapter_metadata_callable(self):
        assert callable(getattr(_inbox, "get_adapter_metadata", None))

    def test_get_adapter_metadata_returns_metadata(self):
        meta = _inbox.get_adapter_metadata()
        assert isinstance(meta, _common.AdapterSkeletonMetadata)

    def test_metadata_phase_1f(self):
        meta = _inbox.get_adapter_metadata()
        assert meta.phase == "PHASE_1F"

    def test_metadata_skeleton_only_true(self):
        meta = _inbox.get_adapter_metadata()
        assert meta.skeleton_only is True

    def test_metadata_implementation_allowed_false(self):
        meta = _inbox.get_adapter_metadata()
        assert meta.implementation_allowed is False

    def test_metadata_live_call_allowed_false(self):
        meta = _inbox.get_adapter_metadata()
        assert meta.live_call_allowed is False


# ═════════════════════════════════════════════════════════════════════════════
# 7. inbox adapt 함수 — 호출 시 SkeletonOnlyAdapterError raise
# ═════════════════════════════════════════════════════════════════════════════

class TestInboxAdaptFunction:
    def test_adapt_function_exists(self):
        assert callable(getattr(_inbox, "adapt_inbox_email_fetch_request_response", None))

    def test_adapt_raises_skeleton_error(self):
        with pytest.raises(_common.SkeletonOnlyAdapterError):
            _inbox.adapt_inbox_email_fetch_request_response()

    def test_adapt_raises_skeleton_error_with_args(self):
        with pytest.raises(_common.SkeletonOnlyAdapterError):
            _inbox.adapt_inbox_email_fetch_request_response({"key": "val"})

    def test_adapt_error_contains_adapter_id(self):
        with pytest.raises(_common.SkeletonOnlyAdapterError) as exc_info:
            _inbox.adapt_inbox_email_fetch_request_response()
        assert "INBOX_EMAIL_FETCH_ADAPTER" in str(exc_info.value)

    def test_adapt_error_contains_phase_1f(self):
        with pytest.raises(_common.SkeletonOnlyAdapterError) as exc_info:
            _inbox.adapt_inbox_email_fetch_request_response()
        assert "PHASE_1F" in str(exc_info.value)

    def test_adapt_error_contains_no_live_email(self):
        with pytest.raises(_common.SkeletonOnlyAdapterError) as exc_info:
            _inbox.adapt_inbox_email_fetch_request_response()
        assert "no live email fetch" in str(exc_info.value)


# ═════════════════════════════════════════════════════════════════════════════
# 8. task_approval_adapter 상수
# ═════════════════════════════════════════════════════════════════════════════

class TestTaskApprovalAdapterConstants:
    def test_approve_adapter_id(self):
        assert _task.APPROVE_ADAPTER_ID == "TASK_APPROVE_PATH_AUTH_ADAPTER"

    def test_reject_adapter_id(self):
        assert _task.REJECT_ADAPTER_ID == "TASK_REJECT_PATH_AUTH_ADAPTER"

    def test_approve_legacy_path_flask_notation(self):
        assert "<id>" in _task.APPROVE_LEGACY_PATH_TEMPLATE

    def test_approve_fastapi_path_fastapi_notation(self):
        assert "{id}" in _task.APPROVE_FASTAPI_PATH_TEMPLATE

    def test_reject_legacy_path_flask_notation(self):
        assert "<id>" in _task.REJECT_LEGACY_PATH_TEMPLATE

    def test_reject_fastapi_path_fastapi_notation(self):
        assert "{id}" in _task.REJECT_FASTAPI_PATH_TEMPLATE

    def test_approve_legacy_path_template(self):
        assert _task.APPROVE_LEGACY_PATH_TEMPLATE == "/api/v1/tasks/<id>/approve"

    def test_approve_fastapi_path_template(self):
        assert _task.APPROVE_FASTAPI_PATH_TEMPLATE == "/api/v1/tasks/{id}/approve"

    def test_reject_legacy_path_template(self):
        assert _task.REJECT_LEGACY_PATH_TEMPLATE == "/api/v1/tasks/<id>/reject"

    def test_reject_fastapi_path_template(self):
        assert _task.REJECT_FASTAPI_PATH_TEMPLATE == "/api/v1/tasks/{id}/reject"

    def test_no_double_slash_approve_legacy(self):
        assert "//" not in _task.APPROVE_LEGACY_PATH_TEMPLATE

    def test_no_double_slash_approve_fastapi(self):
        assert "//" not in _task.APPROVE_FASTAPI_PATH_TEMPLATE

    def test_no_double_slash_reject_legacy(self):
        assert "//" not in _task.REJECT_LEGACY_PATH_TEMPLATE

    def test_no_double_slash_reject_fastapi(self):
        assert "//" not in _task.REJECT_FASTAPI_PATH_TEMPLATE

    def test_approve_risk_level_high(self):
        assert _task.APPROVE_RISK_LEVEL == "HIGH"

    def test_reject_risk_level_high(self):
        assert _task.REJECT_RISK_LEVEL == "HIGH"

    def test_approve_feature_flag(self):
        assert _task.APPROVE_REQUIRED_FEATURE_FLAG == "LEGACY_5050_TASK_APPROVE_ADAPTER_ENABLED"

    def test_reject_feature_flag(self):
        assert _task.REJECT_REQUIRED_FEATURE_FLAG == "LEGACY_5050_TASK_REJECT_ADAPTER_ENABLED"

    def test_approve_safety_gate(self):
        assert _task.APPROVE_REQUIRED_SAFETY_GATE == "APPROVAL_GATE_REQUIRED_BUT_NOT_EXECUTED_IN_TESTS"

    def test_reject_safety_gate(self):
        assert _task.REJECT_REQUIRED_SAFETY_GATE == "APPROVAL_GATE_REQUIRED_BUT_NOT_EXECUTED_IN_TESTS"


# ═════════════════════════════════════════════════════════════════════════════
# 9. task metadata 함수
# ═════════════════════════════════════════════════════════════════════════════

class TestTaskMetadataFunctions:
    def test_get_task_approve_metadata_callable(self):
        assert callable(getattr(_task, "get_task_approve_adapter_metadata", None))

    def test_get_task_reject_metadata_callable(self):
        assert callable(getattr(_task, "get_task_reject_adapter_metadata", None))

    def test_approve_metadata_returns_metadata(self):
        meta = _task.get_task_approve_adapter_metadata()
        assert isinstance(meta, _common.AdapterSkeletonMetadata)

    def test_reject_metadata_returns_metadata(self):
        meta = _task.get_task_reject_adapter_metadata()
        assert isinstance(meta, _common.AdapterSkeletonMetadata)

    def test_approve_metadata_phase_1f(self):
        meta = _task.get_task_approve_adapter_metadata()
        assert meta.phase == "PHASE_1F"

    def test_approve_metadata_skeleton_only_true(self):
        meta = _task.get_task_approve_adapter_metadata()
        assert meta.skeleton_only is True

    def test_approve_metadata_implementation_allowed_false(self):
        meta = _task.get_task_approve_adapter_metadata()
        assert meta.implementation_allowed is False

    def test_reject_metadata_skeleton_only_true(self):
        meta = _task.get_task_reject_adapter_metadata()
        assert meta.skeleton_only is True


# ═════════════════════════════════════════════════════════════════════════════
# 10. task adapt 함수 — 호출 시 SkeletonOnlyAdapterError raise
# ═════════════════════════════════════════════════════════════════════════════

class TestTaskAdaptFunctions:
    def test_approve_adapt_function_exists(self):
        assert callable(getattr(_task, "adapt_task_approve_path_auth_response", None))

    def test_reject_adapt_function_exists(self):
        assert callable(getattr(_task, "adapt_task_reject_path_auth_response", None))

    def test_approve_adapt_raises_skeleton_error(self):
        with pytest.raises(_common.SkeletonOnlyAdapterError):
            _task.adapt_task_approve_path_auth_response()

    def test_reject_adapt_raises_skeleton_error(self):
        with pytest.raises(_common.SkeletonOnlyAdapterError):
            _task.adapt_task_reject_path_auth_response()

    def test_approve_adapt_error_contains_adapter_id(self):
        with pytest.raises(_common.SkeletonOnlyAdapterError) as exc_info:
            _task.adapt_task_approve_path_auth_response()
        assert "TASK_APPROVE_PATH_AUTH_ADAPTER" in str(exc_info.value)

    def test_reject_adapt_error_contains_adapter_id(self):
        with pytest.raises(_common.SkeletonOnlyAdapterError) as exc_info:
            _task.adapt_task_reject_path_auth_response()
        assert "TASK_REJECT_PATH_AUTH_ADAPTER" in str(exc_info.value)

    def test_approve_adapt_error_contains_phase_1f(self):
        with pytest.raises(_common.SkeletonOnlyAdapterError) as exc_info:
            _task.adapt_task_approve_path_auth_response()
        assert "PHASE_1F" in str(exc_info.value)

    def test_approve_adapt_error_no_actual_approve(self):
        with pytest.raises(_common.SkeletonOnlyAdapterError) as exc_info:
            _task.adapt_task_approve_path_auth_response()
        assert "no actual approve execution" in str(exc_info.value)

    def test_reject_adapt_error_no_actual_reject(self):
        with pytest.raises(_common.SkeletonOnlyAdapterError) as exc_info:
            _task.adapt_task_reject_path_auth_response()
        assert "no actual reject execution" in str(exc_info.value)

    def test_approve_adapt_error_no_db_write(self):
        with pytest.raises(_common.SkeletonOnlyAdapterError) as exc_info:
            _task.adapt_task_approve_path_auth_response()
        assert "no DB write" in str(exc_info.value)


# ═════════════════════════════════════════════════════════════════════════════
# 11. 금지 import 정적 검사
# ═════════════════════════════════════════════════════════════════════════════

FORBIDDEN_IMPORT_MODULES = [
    "requests", "httpx", "urllib.request",
    "sqlite3", "psycopg", "psycopg2",
    "sqlalchemy",
    "subprocess", "socket",
]

FORBIDDEN_DECORATOR_PATTERNS = [
    "@app.route", "@router.get", "@router.post",
    "@router.put", "@router.delete", "@router.patch",
    "@app.get", "@app.post",
]

ADAPTER_FILES = [
    ROOT / "backend/compat/legacy_5050/adapters/common.py",
    ROOT / "backend/compat/legacy_5050/adapters/inbox_email_fetch_adapter.py",
    ROOT / "backend/compat/legacy_5050/adapters/task_approval_adapter.py",
]


def _get_import_lines(src: str) -> list[str]:
    """실제 import 문 행만 추출 (docstring/주석 제외)."""
    lines = []
    in_docstring = False
    quote = None
    for line in src.splitlines():
        stripped = line.strip()
        # 멀티라인 docstring 감지
        for q in ('"""', "'''"):
            if q in stripped:
                count = stripped.count(q)
                if not in_docstring:
                    in_docstring = True
                    quote = q
                    if count >= 2:
                        in_docstring = False
                        quote = None
                elif quote == q:
                    in_docstring = False
                    quote = None
                break
        if in_docstring:
            continue
        if stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


class TestForbiddenImports:
    @pytest.mark.parametrize("adapter_file", ADAPTER_FILES, ids=lambda p: p.name)
    @pytest.mark.parametrize("module", FORBIDDEN_IMPORT_MODULES)
    def test_no_forbidden_import(self, adapter_file, module):
        src = adapter_file.read_text(encoding="utf-8")
        import_lines = _get_import_lines(src)
        for line in import_lines:
            assert not (
                line.startswith(f"import {module}") or
                line.startswith(f"from {module}") or
                f"import {module}" == line
            ), f"{adapter_file.name} has forbidden import: {line}"

    @pytest.mark.parametrize("adapter_file", ADAPTER_FILES, ids=lambda p: p.name)
    @pytest.mark.parametrize("pattern", FORBIDDEN_DECORATOR_PATTERNS)
    def test_no_forbidden_decorator(self, adapter_file, pattern):
        src = adapter_file.read_text(encoding="utf-8")
        assert pattern not in src, f"{adapter_file.name} contains forbidden decorator: {pattern}"


# ═════════════════════════════════════════════════════════════════════════════
# 12. 감사 스크립트 verdict
# ═════════════════════════════════════════════════════════════════════════════

class TestAuditScriptVerdict:
    def test_audit_script_exists(self):
        p = ROOT / "scripts/ops/audit_5050_phase1f_adapter_skeleton_only.py"
        assert p.exists()

    def test_audit_run_returns_success(self):
        from scripts.ops.audit_5050_phase1f_adapter_skeleton_only import run_audit
        result = run_audit()
        assert result["success"] is True, f"audit failed: {result['issues']}"

    def test_audit_verdict_phase1f_ready(self):
        from scripts.ops.audit_5050_phase1f_adapter_skeleton_only import run_audit
        result = run_audit()
        assert result["verdict"] == "PHASE1F_ADAPTER_SKELETON_ONLY_READY"

    def test_audit_no_issues(self):
        from scripts.ops.audit_5050_phase1f_adapter_skeleton_only import run_audit
        result = run_audit()
        assert result["issues"] == []

    def test_audit_safe_boundary_no_violations(self):
        from scripts.ops.audit_5050_phase1f_adapter_skeleton_only import run_audit
        result = run_audit()
        assert result["safe_boundary"]["violations"] == []

    def test_audit_known_baseline_failures_documented(self):
        from scripts.ops.audit_5050_phase1f_adapter_skeleton_only import run_audit
        result = run_audit()
        assert len(result["known_baseline_failures"]) >= 6

    def test_audit_files_exist(self):
        from scripts.ops.audit_5050_phase1f_adapter_skeleton_only import run_audit
        result = run_audit()
        assert result["checks"]["files_exist"] is True

    def test_audit_all_imports_ok(self):
        from scripts.ops.audit_5050_phase1f_adapter_skeleton_only import run_audit
        result = run_audit()
        assert all(result["checks"]["import_ok"].values())

    def test_audit_all_metadata_ok(self):
        from scripts.ops.audit_5050_phase1f_adapter_skeleton_only import run_audit
        result = run_audit()
        assert all(result["checks"]["metadata_ok"].values())

    def test_audit_all_adapt_raise(self):
        from scripts.ops.audit_5050_phase1f_adapter_skeleton_only import run_audit
        result = run_audit()
        assert all(result["checks"]["adapt_raises"].values())

    def test_audit_no_double_slash(self):
        from scripts.ops.audit_5050_phase1f_adapter_skeleton_only import run_audit
        result = run_audit()
        assert result["checks"]["no_double_slash"] is True

    def test_audit_no_forbidden_paths(self):
        from scripts.ops.audit_5050_phase1f_adapter_skeleton_only import run_audit
        result = run_audit()
        assert result["checks"]["no_forbidden_paths"] is True


# ═════════════════════════════════════════════════════════════════════════════
# 13. Phase 1-E / D / B 일관성
# ═════════════════════════════════════════════════════════════════════════════

class TestPhaseConsistency:
    def _find_plan(self, plans, adapter_id):
        return next(p for p in plans if p["adapter_id"] == adapter_id)

    def _find_case(self, cases, case_id):
        return next(c for c in cases if c["dry_run_case_id"] == case_id)

    def _find_adapter(self, adapters, adapter_id):
        return next(a for a in adapters if a["adapter_id"] == adapter_id)

    def test_phase1e_plan_inbox_module_path_matches(self):
        from scripts.ops.audit_5050_phase1e_adapter_implementation_plan import PHASE1E_IMPLEMENTATION_PLANS
        plan = self._find_plan(PHASE1E_IMPLEMENTATION_PLANS, "INBOX_EMAIL_FETCH_ADAPTER")
        expected = "backend/compat/legacy_5050/adapters/inbox_email_fetch_adapter.py"
        assert plan["proposed_adapter_module"] == expected

    def test_phase1e_plan_approve_module_path_matches(self):
        from scripts.ops.audit_5050_phase1e_adapter_implementation_plan import PHASE1E_IMPLEMENTATION_PLANS
        plan = self._find_plan(PHASE1E_IMPLEMENTATION_PLANS, "TASK_APPROVE_PATH_AUTH_ADAPTER")
        expected = "backend/compat/legacy_5050/adapters/task_approval_adapter.py"
        assert plan["proposed_adapter_module"] == expected

    def test_phase1e_plan_inbox_function_name_matches(self):
        from scripts.ops.audit_5050_phase1e_adapter_implementation_plan import PHASE1E_IMPLEMENTATION_PLANS
        plan = self._find_plan(PHASE1E_IMPLEMENTATION_PLANS, "INBOX_EMAIL_FETCH_ADAPTER")
        assert plan["proposed_adapter_function"] == "adapt_inbox_email_fetch_request_response"

    def test_phase1e_plan_approve_function_name_matches(self):
        from scripts.ops.audit_5050_phase1e_adapter_implementation_plan import PHASE1E_IMPLEMENTATION_PLANS
        plan = self._find_plan(PHASE1E_IMPLEMENTATION_PLANS, "TASK_APPROVE_PATH_AUTH_ADAPTER")
        assert plan["proposed_adapter_function"] == "adapt_task_approve_path_auth_response"

    def test_phase1e_plan_reject_function_name_matches(self):
        from scripts.ops.audit_5050_phase1e_adapter_implementation_plan import PHASE1E_IMPLEMENTATION_PLANS
        plan = self._find_plan(PHASE1E_IMPLEMENTATION_PLANS, "TASK_REJECT_PATH_AUTH_ADAPTER")
        assert plan["proposed_adapter_function"] == "adapt_task_reject_path_auth_response"

    def test_phase1d_inbox_path_matches_adapter(self):
        from scripts.ops.audit_5050_phase1d_adapter_dry_run_compat import PHASE1D_DRY_RUN_CASES
        case = self._find_case(PHASE1D_DRY_RUN_CASES, "DRYRUN_INBOX_EMAIL_FETCH_COMPAT")
        assert case["legacy_path_template"] == _inbox.LEGACY_PATH_TEMPLATE

    def test_phase1b_inbox_adapter_id_matches(self):
        from scripts.ops.audit_5050_phase1b_adapter_contract_detail import PHASE1B_ADAPTERS
        adapter = self._find_adapter(PHASE1B_ADAPTERS, "INBOX_EMAIL_FETCH_ADAPTER")
        assert adapter["adapter_id"] == _inbox.ADAPTER_ID

    def test_phase1b_approve_adapter_id_matches(self):
        from scripts.ops.audit_5050_phase1b_adapter_contract_detail import PHASE1B_ADAPTERS
        adapter = self._find_adapter(PHASE1B_ADAPTERS, "TASK_APPROVE_PATH_AUTH_ADAPTER")
        assert adapter["adapter_id"] == _task.APPROVE_ADAPTER_ID

    def test_phase1b_reject_adapter_id_matches(self):
        from scripts.ops.audit_5050_phase1b_adapter_contract_detail import PHASE1B_ADAPTERS
        adapter = self._find_adapter(PHASE1B_ADAPTERS, "TASK_REJECT_PATH_AUTH_ADAPTER")
        assert adapter["adapter_id"] == _task.REJECT_ADAPTER_ID
