"""External App Bridge 계약 기준선 테스트.

ASSISTANT_BACKEND_PREMIUM_INTEGRATED_CLOSEOUT_01 STEP 7 검측.

금지:
- 실제 CAD/HWPX/Excel/세무/입찰 앱 실행 금지
- 실제 파일 수정 금지
- 외부 사이트 접속 금지
- DB write 금지
- skip/xfail 금지
"""

from __future__ import annotations

from ai_orchestrator.audit_evidence.adapters import build_external_app_handoff
from ai_orchestrator.domain.model_adapters import get_all_bridges, get_bridge
from ai_orchestrator.safety_policy.secret_redaction import (
    FORBIDDEN_SECRET_FIELDS,
)

# ---------------------------------------------------------------------------
# 금지 필드 헬퍼
# ---------------------------------------------------------------------------


def _has_forbidden(d: dict) -> list[str]:
    found = []
    for k, v in d.items():
        if k.lower() in FORBIDDEN_SECRET_FIELDS:
            found.append(k)
        if isinstance(v, dict):
            found.extend(_has_forbidden(v))
    return found


# ---------------------------------------------------------------------------
# STEP 7.1 — bridge registry 6개 전문 앱 포함
# ---------------------------------------------------------------------------


class TestBridgeRegistry:
    """bridge registry 계약 검측."""

    def test_registry_has_six_bridges(self):
        bridges = get_all_bridges()
        assert len(bridges) == 6, f"bridge 수={len(bridges)}"

    def test_bridge_types_cover_all_domains(self):
        bridges = get_all_bridges()
        types = {b.app_type for b in bridges}
        required = {"CAD", "HWPX", "OFFICE", "TAX", "BID", "DOCUMENT_AUTOMATION"}
        assert required == types, f"누락: {required - types}"

    def test_all_bridges_approval_required(self):
        for b in get_all_bridges():
            assert b.approval_required is True, f"{b.bridge_id}: approval_required=False"

    def test_cad_hwpx_office_doc_are_local_agent_required(self):
        local_types = {"CAD", "HWPX", "OFFICE", "DOCUMENT_AUTOMATION"}
        for b in get_all_bridges():
            if b.app_type in local_types:
                assert "LOCAL_AGENT_REQUIRED" in b.execution_location, (
                    f"{b.app_type}: execution_location={b.execution_location}"
                )

    def test_tax_bid_are_user_direct_required(self):
        user_types = {"TAX", "BID"}
        for b in get_all_bridges():
            if b.app_type in user_types:
                assert "USER_DIRECT_REQUIRED" in b.execution_location, (
                    f"{b.app_type}: execution_location={b.execution_location}"
                )

    def test_bid_has_no_bid_auto_execute_policy(self):
        bid = get_bridge("bid-bridge")
        assert bid is not None
        policy_str = " ".join(bid.safety_policy_ids)
        assert "no-bid-auto-execute" in policy_str or "no_bid_auto_execute" in policy_str, (
            f"bid safety_policy_ids={bid.safety_policy_ids}"
        )

    def test_all_bridges_status_future_or_hold(self):
        allowed_statuses = {"FUTURE_INTEGRATION", "EXTERNAL_APP_HOLD"}
        for b in get_all_bridges():
            assert b.status in allowed_statuses, f"{b.bridge_id}: status={b.status} (is_implemented=True는 금지)"

    def test_all_bridges_not_implemented(self):
        for b in get_all_bridges():
            assert not b.is_implemented(), f"{b.bridge_id}: is_implemented()=True"

    def test_no_forbidden_fields_in_safe_dict(self):
        for b in get_all_bridges():
            assert _has_forbidden(b.to_safe_dict()) == [], f"{b.bridge_id}: 금지 필드 노출"


# ---------------------------------------------------------------------------
# STEP 7.2 — ExternalAppHandoff 생성 가능, 실행 아님
# ---------------------------------------------------------------------------


class TestExternalAppHandoff:
    """handoff 기록 계약 — 실제 앱 실행 없음."""

    def test_cad_handoff_creation(self):
        hf = build_external_app_handoff(
            task_id="t_cad_001",
            bridge_id="cad-bridge",
            app_type="CAD",
            handoff_mode="file_drop",
            approval_required=True,
            user_direct_required=False,
            safety_policy_ids=("external_app_hold_policy",),
            auto_execute_allowed=False,
        )
        assert hf.status == "handoff_recorded"
        assert hf.completed_at is None

    def test_hwpx_handoff_approval_required(self):
        hf = build_external_app_handoff(
            task_id="t_hwpx_001",
            bridge_id="hwpx-bridge",
            app_type="HWPX",
            handoff_mode="file_drop",
            approval_required=True,
            user_direct_required=False,
            auto_execute_allowed=False,
        )
        assert hf.approval_required is True

    def test_excel_handoff(self):
        hf = build_external_app_handoff(
            task_id="t_excel_001",
            bridge_id="office-bridge",
            app_type="OFFICE",
            handoff_mode="file_drop",
            approval_required=True,
            user_direct_required=False,
            auto_execute_allowed=False,
        )
        assert hf.app_type == "OFFICE"

    def test_tax_handoff_user_direct(self):
        hf = build_external_app_handoff(
            task_id="t_tax_001",
            bridge_id="tax-bridge",
            app_type="TAX",
            handoff_mode="user_manual",
            approval_required=True,
            user_direct_required=True,
            auto_execute_allowed=False,
        )
        assert hf.user_direct_required is True
        assert hf.auto_execute_allowed is False

    def test_bid_handoff_no_auto_execute(self):
        hf = build_external_app_handoff(
            task_id="t_bid_001",
            bridge_id="bid-bridge",
            app_type="BID",
            handoff_mode="user_manual",
            approval_required=True,
            user_direct_required=True,
            safety_policy_ids=("no_bid_auto_execute",),
            auto_execute_allowed=False,
        )
        d = hf.to_safe_dict()
        assert d["auto_execute_allowed"] is False
        assert "no_bid_auto_execute" in d["safety_policy_ids"]

    def test_doc_auto_handoff(self):
        hf = build_external_app_handoff(
            task_id="t_doc_001",
            bridge_id="doc-auto-bridge",
            app_type="DOCUMENT_AUTOMATION",
            handoff_mode="file_drop",
            approval_required=True,
            user_direct_required=False,
            auto_execute_allowed=False,
        )
        assert hf.app_type == "DOCUMENT_AUTOMATION"

    def test_all_handoffs_no_forbidden_fields(self):
        cases = [
            ("t_1", "cad-bridge", "CAD", "file_drop", False),
            ("t_2", "tax-bridge", "TAX", "user_manual", True),
            ("t_3", "bid-bridge", "BID", "user_manual", True),
        ]
        for task_id, bridge_id, app_type, mode, user_direct in cases:
            hf = build_external_app_handoff(
                task_id=task_id,
                bridge_id=bridge_id,
                app_type=app_type,
                handoff_mode=mode,
                approval_required=True,
                user_direct_required=user_direct,
                auto_execute_allowed=False,
            )
            assert _has_forbidden(hf.to_safe_dict()) == []

    def test_handoff_input_artifact_refs_expressible(self):
        from ai_orchestrator.audit_evidence.models import ExternalAppHandoff

        hf = ExternalAppHandoff.create(
            task_id="t_art_001",
            bridge_id="cad-bridge",
            app_type="CAD",
            handoff_mode="file_drop",
            status="handoff_recorded",
            approval_required=True,
            user_direct_required=False,
            input_artifact_refs=("ar_abc123",),
            auto_execute_allowed=False,
        )
        assert "ar_abc123" in hf.input_artifact_refs

    def test_handoff_output_artifact_refs_empty_before_execution(self):
        hf = build_external_app_handoff(
            task_id="t_out_001",
            bridge_id="cad-bridge",
            app_type="CAD",
            handoff_mode="file_drop",
            approval_required=True,
            user_direct_required=False,
            auto_execute_allowed=False,
        )
        assert hf.output_artifact_refs == ()


# ---------------------------------------------------------------------------
# STEP 7.3 — ExecutionPolicyService bridge 차단 확인
# ---------------------------------------------------------------------------


class TestExecutionPolicyBridgeBlock:
    """ExecutionPolicyService가 CAD/Tax/Bid를 서버에서 차단한다."""

    def test_cad_blocked_on_server(self):
        from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

        svc = ExecutionPolicyService()
        # provider="local_app", work_type="cad" → QUARANTINE/EXTERNAL_APP_HOLD 분류
        decision = svc.decide_for_external_work(provider="local_app", work_type="cad")
        assert not decision.server_executable, "CAD는 서버 직접 실행 불가"

    def test_bid_blocked_user_direct(self):
        from ai_orchestrator.services.execution_policy_service import ExecutionPolicyService

        svc = ExecutionPolicyService()
        decision = svc.decide_for_external_work(provider="local_app", work_type="bid")
        assert not decision.server_executable, "BID는 서버 직접 실행 불가"

    def test_no_real_app_import(self):
        import sys

        # 실제 CAD/HWPX 앱 SDK가 import되지 않았음을 확인
        cad_modules = [k for k in sys.modules if "autocad" in k.lower() or "zwcad" in k.lower() or "hwpx" in k.lower()]
        assert sys.modules, "sys.modules 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
        assert cad_modules == [], f"실제 앱 import 감지: {cad_modules}"
