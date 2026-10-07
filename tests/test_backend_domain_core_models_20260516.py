"""ASSISTANT_BACKEND_DOMAIN_CORE_MODELS_BASELINE_01 — Domain Core 모델 기준선 테스트.

검증 범위:
  1. Task 모델 필수 필드 생성 가능
  2. WorkTrade 모델 범위 표현
  3. ExternalWork 분류 표현
  4. Integration 상태 표현
  5. Artifact safe ref 표현
  6. SafetyPolicy 결정 표현
  7. ExternalAppBridge 핸드오프 표현
  8. AuditEvent 표준 필드 11개
  9. to_safe_dict secret 필드 없음
  10. model_adapters 동작
  11. CAD/HWPX/Excel = EXTERNAL_APP_HOLD
  12. 기존 계약 충돌 없음

DB/서버/브라우저/외부 API 실행 없음.
"""

from __future__ import annotations

import pytest

# ===========================================================================
# 1. Task 모델
# ===========================================================================


class TestTaskModel:
    """Task 도메인 모델 테스트."""

    def _make_task(self, **kwargs):
        from ai_orchestrator.domain.models import Task

        defaults = {
            "task_id": "task-001",
            "title": "Naver 블로그 포스팅",
            "provider": "naver",
            "action_type": "blog_post",
            "execution_location": "LOCAL_AGENT_REQUIRED",
            "risk_level": "high",
            "approval_required": True,
            "status": "pending",
            "summary": "테스트 포스팅",
        }
        defaults.update(kwargs)
        return Task(**defaults)

    def test_task_creation(self):
        """Task 모델을 생성할 수 있다."""
        t = self._make_task()
        assert t.task_id == "task-001"
        assert t.provider == "naver"
        assert t.approval_required is True

    def test_task_to_safe_dict_no_secret(self):
        """to_safe_dict 에 secret 필드가 없다."""
        from ai_orchestrator.domain.models import DOMAIN_FORBIDDEN_FIELDS

        t = self._make_task()
        d = t.to_safe_dict()
        for key in d:
            assert key.lower() not in DOMAIN_FORBIDDEN_FIELDS, f"Task.to_safe_dict에 금지 필드 발견: {key}"

    def test_task_is_frozen(self):
        """Task는 불변 모델 (frozen=True) 이다."""
        t = self._make_task()
        with pytest.raises((AttributeError, TypeError)):
            t.status = "approved"  # type: ignore

    def test_task_artifact_refs_default_empty(self):
        """artifact_refs 기본값은 빈 tuple 이다."""
        t = self._make_task()
        assert t.artifact_refs == ()

    def test_make_task_factory(self):
        """make_task 팩토리로 task_id를 자동 생성한다."""
        from ai_orchestrator.domain.models import make_task

        t = make_task(
            title="검색 작업",
            provider="naver",
            action_type="search",
            execution_location="SERVER_INTERNAL_ONLY",
            risk_level="low",
            approval_required=False,
        )
        assert t.task_id.startswith("task-")
        assert t.status == "pending"

    def test_task_required_fields_in_safe_dict(self):
        """to_safe_dict에 핵심 필드가 모두 포함된다."""
        t = self._make_task()
        d = t.to_safe_dict()
        for key in (
            "task_id",
            "title",
            "provider",
            "action_type",
            "execution_location",
            "risk_level",
            "approval_required",
            "status",
            "requested_at",
        ):
            assert key in d, f"Task.to_safe_dict에 필드 누락: {key}"


# ===========================================================================
# 2. WorkTrade 모델
# ===========================================================================


class TestWorkTradeModel:
    """WorkTrade 도메인 모델 테스트."""

    def test_in_scope_work_trade(self):
        """IN_SCOPE WorkTrade를 표현할 수 있다."""
        from ai_orchestrator.domain.models import WorkTrade, WorkTradeScope

        wt = WorkTrade(
            work_trade_id="wt-search-001",
            name="Naver 검색 조회",
            description="Naver 공개 검색 API 조회",
            scope=WorkTradeScope.SERVER_READONLY_ALLOWED,
            execution_location="SERVER_INTERNAL_ONLY",
            external_app_hold=False,
        )
        assert not wt.is_external_app_hold()
        assert not wt.is_future_integration()

    def test_external_app_hold_work_trade(self):
        """EXTERNAL_APP_HOLD WorkTrade를 표현할 수 있다."""
        from ai_orchestrator.domain.models import WorkTrade, WorkTradeScope

        wt = WorkTrade(
            work_trade_id="wt-cad-001",
            name="CAD 도면 작성",
            description="AutoCAD 도면 작성 (외부 전문 앱 필요)",
            scope=WorkTradeScope.EXTERNAL_APP_HOLD,
            execution_location="LOCAL_AGENT_REQUIRED",
            external_app_hold=True,
            next_phase="5단계 External App Bridge 계약",
        )
        assert wt.is_external_app_hold()

    def test_future_integration_work_trade(self):
        """FUTURE_INTEGRATION WorkTrade를 표현할 수 있다."""
        from ai_orchestrator.domain.models import WorkTrade, WorkTradeScope

        wt = WorkTrade(
            work_trade_id="wt-tax-001",
            name="세금계산서 조회",
            description="공식 API 연동 후 지원 예정",
            scope=WorkTradeScope.FUTURE_INTEGRATION,
            execution_location="SERVER_INTERNAL_ONLY",
        )
        assert wt.is_future_integration()

    def test_work_trade_to_safe_dict(self):
        """WorkTrade.to_safe_dict에 secret 없음."""
        from ai_orchestrator.domain.models import DOMAIN_FORBIDDEN_FIELDS, WorkTrade, WorkTradeScope

        wt = WorkTrade(
            work_trade_id="wt-test",
            name="테스트",
            description="테스트",
            scope=WorkTradeScope.IN_SCOPE,
            execution_location="SERVER_INTERNAL_ONLY",
        )
        d = wt.to_safe_dict()
        for key in d:
            assert key.lower() not in DOMAIN_FORBIDDEN_FIELDS


# ===========================================================================
# 3. ExternalWork 모델
# ===========================================================================


class TestExternalWorkModel:
    """ExternalWork 도메인 모델 테스트."""

    def test_naver_search_external_work(self):
        """Naver 검색 ExternalWork를 표현할 수 있다."""
        from ai_orchestrator.domain.models import ExternalWork, WorkTradeScope

        ew = ExternalWork(
            external_work_id="ew-naver-search",
            provider="naver",
            action_type="search",
            category=WorkTradeScope.SERVER_READONLY_ALLOWED,
            execution_location="SERVER_INTERNAL_ONLY",
            risk_level="low",
            approval_required=False,
            auth_mode="none",
            status="active",
        )
        assert ew.is_executable()
        assert not ew.requires_local_agent()

    def test_naver_local_agent_external_work(self):
        """Naver 로컬 에이전트 작업을 표현할 수 있다."""
        from ai_orchestrator.domain.models import ExternalWork, WorkTradeScope

        ew = ExternalWork(
            external_work_id="ew-naver-blog-post",
            provider="naver",
            action_type="blog_post",
            category=WorkTradeScope.LOCAL_AGENT_REQUIRED,
            execution_location="LOCAL_AGENT_REQUIRED",
            risk_level="high",
            approval_required=True,
            auth_mode="browser_session",
            status="active",
        )
        assert ew.requires_local_agent()
        assert ew.is_executable() is not False  # LOCAL_AGENT는 실행 가능

    def test_oauth_required_external_work(self):
        """OAuth 필요 작업은 setup_required 상태다."""
        from ai_orchestrator.domain.models import ExternalWork, WorkTradeScope

        ew = ExternalWork(
            external_work_id="ew-google-calendar",
            provider="google",
            action_type="calendar_read",
            category=WorkTradeScope.OFFICIAL_API_OR_OAUTH_REQUIRED,
            execution_location="SERVER_INTERNAL_ONLY",
            risk_level="medium",
            approval_required=False,
            auth_mode="oauth",
            status="setup_required",
        )
        assert not ew.is_executable()

    def test_external_app_hold_not_executable(self):
        """EXTERNAL_APP_HOLD 항목은 실행 불가다."""
        from ai_orchestrator.domain.models import ExternalWork, WorkTradeScope

        ew = ExternalWork(
            external_work_id="ew-cad",
            provider="cad",
            action_type="draw",
            category=WorkTradeScope.EXTERNAL_APP_HOLD,
            execution_location="LOCAL_AGENT_REQUIRED",
            risk_level="high",
            approval_required=True,
            auth_mode="user_direct",
            status="hold",
        )
        assert not ew.is_executable()

    def test_external_work_no_secret_in_safe_dict(self):
        """ExternalWork.to_safe_dict에 secret 없음."""
        from ai_orchestrator.domain.models import DOMAIN_FORBIDDEN_FIELDS, ExternalWork, WorkTradeScope

        ew = ExternalWork(
            external_work_id="ew-test",
            provider="test",
            action_type="test",
            category=WorkTradeScope.IN_SCOPE,
            execution_location="SERVER_INTERNAL_ONLY",
            risk_level="low",
            approval_required=False,
            auth_mode="none",
            status="active",
        )
        d = ew.to_safe_dict()
        for key in d:
            assert key.lower() not in DOMAIN_FORBIDDEN_FIELDS


# ===========================================================================
# 4. Integration 모델
# ===========================================================================


class TestIntegrationModel:
    """Integration 도메인 모델 테스트."""

    def test_connected_integration(self):
        """연결된 Integration을 표현할 수 있다."""
        from ai_orchestrator.domain.models import Integration, IntegrationStatus

        intg = Integration(
            integration_id="int-telegram",
            name="Telegram 알림",
            provider="telegram",
            integration_type="bot",
            status=IntegrationStatus.CONNECTED,
            auth_mode="bot_token",
            connected=True,
            health="healthy",
        )
        assert intg.is_ready()

    def test_oauth_setup_required_integration(self):
        """OAuth 설정 필요 Integration을 표현할 수 있다."""
        from ai_orchestrator.domain.models import Integration, IntegrationStatus

        intg = Integration(
            integration_id="int-google-oauth",
            name="Google OAuth",
            provider="google",
            integration_type="oauth",
            status=IntegrationStatus.SETUP_REQUIRED,
            auth_mode="oauth",
            connected=False,
            required_setup="credentials.json + token.json 설정 필요",
        )
        assert not intg.is_ready()

    def test_integration_no_secret_in_safe_dict(self):
        """Integration.to_safe_dict에 secret 없음."""
        from ai_orchestrator.domain.models import DOMAIN_FORBIDDEN_FIELDS, Integration, IntegrationStatus

        intg = Integration(
            integration_id="int-test",
            name="test",
            provider="test",
            integration_type="generic",
            status=IntegrationStatus.CONNECTED,
            auth_mode="none",
            connected=True,
        )
        d = intg.to_safe_dict()
        for key in d:
            assert key.lower() not in DOMAIN_FORBIDDEN_FIELDS


# ===========================================================================
# 5. Artifact 모델
# ===========================================================================


class TestArtifactModel:
    """Artifact 도메인 모델 테스트."""

    def test_artifact_has_storage_ref_not_content(self):
        """Artifact는 storage_ref(경로 참조)를 갖고 파일 내용은 없다."""
        from ai_orchestrator.domain.models import Artifact, ArtifactType, EvidenceLevel

        a = Artifact(
            artifact_id="art-001",
            artifact_type=ArtifactType.SCREENSHOT_REF,
            content_type="image/png-ref",
            storage_ref="data/audit/screenshots/task-001-001.png.ref",
            safe_name="결과_스크린샷_참조",
            source_task_id="task-001",
            evidence_level=EvidenceLevel.CONFIRMED,
            summary="실행 완료 확인 스크린샷 경로 참조",
        )
        d = a.to_safe_dict()
        assert "storage_ref" in d
        # 바이너리 내용 없음
        assert "file_content" not in d
        assert "file_bytes" not in d
        assert "base64" not in d

    def test_artifact_no_secret_fields(self):
        """Artifact.to_safe_dict에 금지 필드 없음."""
        from ai_orchestrator.domain.models import DOMAIN_FORBIDDEN_FIELDS, Artifact, ArtifactType, EvidenceLevel

        a = Artifact(
            artifact_id="art-002",
            artifact_type=ArtifactType.JSON_SUMMARY,
            content_type="application/json",
            storage_ref="ref://summary/task-002",
            safe_name="요약",
            evidence_level=EvidenceLevel.PARTIAL,
        )
        d = a.to_safe_dict()
        for key in d:
            assert key.lower() not in DOMAIN_FORBIDDEN_FIELDS


# ===========================================================================
# 6. SafetyPolicy 모델
# ===========================================================================


class TestSafetyPolicyModel:
    """SafetyPolicy 도메인 모델 테스트."""

    def test_block_policy(self):
        """BLOCK 결정 SafetyPolicy를 표현할 수 있다."""
        from ai_orchestrator.domain.models import SafetyDecision, SafetyPolicy

        p = SafetyPolicy(
            policy_id="pol-block-auto-submit",
            name="자동 제출 금지",
            category="execution",
            severity="block",
            applies_to=("action_type:submit", "action_type:bid"),
            decision=SafetyDecision.BLOCK,
            reason="자동 투찰/서명 금지",
        )
        assert p.blocks_execution()

    def test_hold_policy(self):
        """HOLD 결정 SafetyPolicy는 실행을 차단한다."""
        from ai_orchestrator.domain.models import SafetyDecision, SafetyPolicy

        p = SafetyPolicy(
            policy_id="pol-external-app-hold",
            name="외부 앱 보류",
            category="hold",
            severity="warn",
            applies_to=("app_type:CAD",),
            decision=SafetyDecision.HOLD,
            reason="전문 앱 계약 미완료",
        )
        assert p.blocks_execution()

    def test_user_direct_policy(self):
        """USER_DIRECT 결정 SafetyPolicy를 표현할 수 있다."""
        from ai_orchestrator.domain.models import SafetyDecision, SafetyPolicy

        p = SafetyPolicy(
            policy_id="pol-user-direct",
            name="사용자 직접 조작 필요",
            category="execution",
            severity="warn",
            applies_to=("execution_location:USER_DIRECT_REQUIRED",),
            decision=SafetyDecision.REQUIRE_USER_DIRECT,
            reason="비밀번호/OTP는 사용자가 직접 입력",
            required_execution_location="USER_DIRECT_REQUIRED",
        )
        assert p.requires_user_direct()
        assert not p.blocks_execution()

    def test_safety_policy_no_secret_fields(self):
        """SafetyPolicy.to_safe_dict에 금지 필드 없음."""
        from ai_orchestrator.domain.models import DOMAIN_FORBIDDEN_FIELDS, SafetyDecision, SafetyPolicy

        p = SafetyPolicy(
            policy_id="pol-test",
            name="테스트",
            category="execution",
            severity="info",
            applies_to=("*",),
            decision=SafetyDecision.ALLOW,
            reason="테스트용",
        )
        d = p.to_safe_dict()
        for key in d:
            assert key.lower() not in DOMAIN_FORBIDDEN_FIELDS


# ===========================================================================
# 7. ExternalAppBridge 모델
# ===========================================================================


class TestExternalAppBridgeModel:
    """ExternalAppBridge 도메인 모델 테스트."""

    def _make_bridge(
        self, app_type: str, handoff_mode: str, exec_loc: str = "LOCAL_AGENT_REQUIRED"
    ) -> ExternalAppBridge:  # noqa: F821
        from ai_orchestrator.domain.models import ExternalAppBridge

        return ExternalAppBridge(
            bridge_id=f"{app_type.lower()}-bridge",
            app_type=app_type,
            capability=("기능1", "기능2"),
            handoff_mode=handoff_mode,
            execution_location=exec_loc,
            approval_required=True,
            status="FUTURE_INTEGRATION",
        )

    def test_cad_bridge(self):
        """CAD 브릿지를 표현할 수 있다."""
        from ai_orchestrator.domain.models import HandoffMode

        b = self._make_bridge("CAD", HandoffMode.FILE_HANDOFF)
        assert b.app_type == "CAD"
        assert b.handoff_mode == HandoffMode.FILE_HANDOFF
        assert not b.is_implemented()

    def test_hwpx_bridge(self):
        """HWPX 브릿지를 표현할 수 있다."""
        from ai_orchestrator.domain.models import HandoffMode

        b = self._make_bridge("HWPX", HandoffMode.FILE_HANDOFF)
        assert b.app_type == "HWPX"
        assert not b.is_implemented()

    def test_excel_office_bridge(self):
        """Excel/Office 브릿지를 표현할 수 있다."""
        from ai_orchestrator.domain.models import HandoffMode

        b = self._make_bridge("OFFICE", HandoffMode.FILE_HANDOFF)
        assert b.app_type == "OFFICE"
        assert not b.is_implemented()

    def test_tax_bridge_user_direct(self):
        """Tax 브릿지는 USER_DIRECT_REQUIRED 위치다."""
        from ai_orchestrator.domain.models import HandoffMode

        b = self._make_bridge("TAX", HandoffMode.USER_HANDOFF, "USER_DIRECT_REQUIRED")
        assert b.execution_location == "USER_DIRECT_REQUIRED"
        assert b.approval_required is True

    def test_bid_bridge_user_direct(self):
        """Bid 브릿지는 USER_DIRECT_REQUIRED 위치다."""
        from ai_orchestrator.domain.models import HandoffMode

        b = self._make_bridge("BID", HandoffMode.USER_HANDOFF, "USER_DIRECT_REQUIRED")
        assert b.execution_location == "USER_DIRECT_REQUIRED"

    def test_all_bridges_approval_required(self):
        """모든 브릿지는 approval_required=True다."""
        from ai_orchestrator.domain.model_adapters import get_all_bridges

        bridges = get_all_bridges()
        assert len(bridges) == 6
        for b in bridges:
            assert b.approval_required is True, f"{b.bridge_id}.approval_required=False"

    def test_bridge_no_secret_in_safe_dict(self):
        """ExternalAppBridge.to_safe_dict에 금지 필드 없음."""
        from ai_orchestrator.domain.models import DOMAIN_FORBIDDEN_FIELDS, HandoffMode

        b = self._make_bridge("CAD", HandoffMode.FILE_HANDOFF)
        d = b.to_safe_dict()
        for key in d:
            assert key.lower() not in DOMAIN_FORBIDDEN_FIELDS

    def test_all_bridges_are_future_integration(self):
        """adapter가 반환하는 모든 브릿지는 FUTURE_INTEGRATION 상태다."""
        from ai_orchestrator.domain.model_adapters import get_all_bridges

        for b in get_all_bridges():
            assert b.status == "FUTURE_INTEGRATION", f"{b.bridge_id}.status={b.status}"


# ===========================================================================
# 8. AuditEvent 모델 — 표준 필드 11개
# ===========================================================================


class TestAuditEventModel:
    """AuditEvent 도메인 모델 테스트."""

    REQUIRED_FIELDS = (
        "event_id",
        "event_type",
        "task_id",
        "provider",
        "action_type",
        "risk_level",
        "execution_location",
        "actor",
        "timestamp",
        "verdict",
        "summary",
    )

    def _make_event(self, **kwargs):
        from ai_orchestrator.domain.models import AuditEvent, _now_iso

        defaults = {
            "event_id": "evt-001",
            "event_type": "TASK_RECEIVED",
            "task_id": "task-001",
            "provider": "naver",
            "action_type": "search",
            "risk_level": "low",
            "execution_location": "SERVER_INTERNAL_ONLY",
            "actor": "server",
            "timestamp": _now_iso(),
            "verdict": "PASS",
            "summary": "검색 작업 수신",
        }
        defaults.update(kwargs)
        return AuditEvent(**defaults)

    def test_audit_event_has_11_required_fields(self):
        """AuditEvent에 표준 필드 11개가 존재한다."""
        e = self._make_event()
        d = e.to_safe_dict()
        for f in self.REQUIRED_FIELDS:
            assert f in d, f"AuditEvent.to_safe_dict에 필드 누락: {f}"

    def test_audit_event_no_secret_fields(self):
        """AuditEvent.to_safe_dict에 금지 필드 없음."""
        from ai_orchestrator.domain.models import DOMAIN_FORBIDDEN_FIELDS

        e = self._make_event()
        d = e.to_safe_dict()
        for key in d:
            assert key.lower() not in DOMAIN_FORBIDDEN_FIELDS, f"AuditEvent.to_safe_dict에 금지 필드 발견: {key}"

    def test_make_audit_event_factory(self):
        """make_audit_event 팩토리로 event_id/timestamp를 자동 생성한다."""
        from ai_orchestrator.domain.models import make_audit_event

        e = make_audit_event(
            event_type="APPROVAL_ISSUED",
            task_id="task-002",
            provider="naver",
            action_type="blog_post",
            risk_level="high",
            execution_location="LOCAL_AGENT_REQUIRED",
            actor="server",
            verdict="PASS",
            summary="승인 토큰 발급",
        )
        assert e.event_id.startswith("evt-")
        assert e.timestamp != ""

    def test_audit_event_redaction_applied_field(self):
        """AuditEvent에 redaction_applied 필드가 있다."""
        e = self._make_event(redaction_applied=True)
        assert e.redaction_applied is True


# ===========================================================================
# 9. assert_no_forbidden_fields 유틸리티
# ===========================================================================


class TestAssertNoForbiddenFields:
    """금지 필드 검증 유틸리티 테스트."""

    def test_clean_dict_passes(self):
        """금지 필드 없는 dict는 위반 없음."""
        from ai_orchestrator.domain.models import assert_no_forbidden_fields

        d = {"task_id": "t1", "provider": "naver", "status": "ok"}
        assert assert_no_forbidden_fields(d) == []

    def test_password_field_detected(self):
        """password 필드가 포함된 dict는 위반으로 감지된다."""
        from ai_orchestrator.domain.models import assert_no_forbidden_fields

        d = {"task_id": "t1", "password": "secret123"}
        violations = assert_no_forbidden_fields(d)
        assert "password" in violations

    def test_token_field_detected(self):
        """token 필드가 포함된 dict는 위반으로 감지된다."""
        from ai_orchestrator.domain.models import assert_no_forbidden_fields

        d = {"task_id": "t1", "token": "abc123"}
        violations = assert_no_forbidden_fields(d)
        assert "token" in violations

    def test_multiple_forbidden_fields_detected(self):
        """복수의 금지 필드가 모두 감지된다."""
        from ai_orchestrator.domain.models import assert_no_forbidden_fields

        d = {"password": "x", "cookie": "y", "otp": "z", "name": "ok"}
        violations = assert_no_forbidden_fields(d)
        assert "password" in violations
        assert "cookie" in violations
        assert "otp" in violations
        assert "name" not in violations


# ===========================================================================
# 10. model_adapters 동작 검증
# ===========================================================================


class TestModelAdapters:
    """model_adapters 동작 테스트."""

    def test_list_external_works_as_models(self):
        """external_work_registry → ExternalWork 변환이 동작한다."""
        from ai_orchestrator.domain.model_adapters import list_external_works_as_models

        works = list_external_works_as_models()
        assert isinstance(works, list)
        # 하나라도 변환되면 기준 통과
        if works:
            from ai_orchestrator.domain.models import ExternalWork

            assert isinstance(works[0], ExternalWork)

    def test_list_integrations_as_models(self):
        """ops_router._STATIC_INTEGRATIONS → Integration 변환이 동작한다."""
        from ai_orchestrator.domain.model_adapters import list_integrations_as_models

        intgs = list_integrations_as_models()
        assert isinstance(intgs, list)
        assert len(intgs) > 0
        from ai_orchestrator.domain.models import Integration

        assert isinstance(intgs[0], Integration)

    def test_get_all_bridges_returns_6(self):
        """get_all_bridges가 6개 브릿지를 반환한다."""
        from ai_orchestrator.domain.model_adapters import get_all_bridges

        bridges = get_all_bridges()
        assert len(bridges) == 6

    def test_get_bridge_by_id(self):
        """특정 bridge_id로 브릿지를 가져올 수 있다."""
        from ai_orchestrator.domain.model_adapters import get_bridge

        b = get_bridge("cad-bridge")
        assert b is not None
        assert b.app_type == "CAD"
        b_missing = get_bridge("nonexistent-bridge")
        assert b_missing is None

    def test_list_safety_policies(self):
        """list_safety_policies가 정책 목록을 반환한다."""
        from ai_orchestrator.domain.model_adapters import list_safety_policies
        from ai_orchestrator.domain.models import SafetyPolicy

        policies = list_safety_policies()
        assert len(policies) >= 4
        assert all(isinstance(p, SafetyPolicy) for p in policies)

    def test_integration_no_secret_in_safe_dict(self):
        """adapter 반환 Integration.to_safe_dict에 secret 없음."""
        from ai_orchestrator.domain.model_adapters import list_integrations_as_models
        from ai_orchestrator.domain.models import DOMAIN_FORBIDDEN_FIELDS

        for intg in list_integrations_as_models():
            d = intg.to_safe_dict()
            for key in d:
                assert key.lower() not in DOMAIN_FORBIDDEN_FIELDS, (
                    f"Integration[{intg.integration_id}].to_safe_dict 금지 필드: {key}"
                )


# ===========================================================================
# 11. CAD/HWPX/Excel = EXTERNAL_APP_HOLD 표현 검증
# ===========================================================================


class TestExternalAppHoldClassification:
    """CAD/HWPX/Excel EXTERNAL_APP_HOLD 분류 테스트."""

    def test_cad_bridge_not_implemented(self):
        """CAD 브릿지는 미구현(FUTURE_INTEGRATION) 상태다."""
        from ai_orchestrator.domain.model_adapters import get_bridge

        b = get_bridge("cad-bridge")
        assert b is not None
        assert not b.is_implemented()

    def test_hwpx_bridge_not_implemented(self):
        """HWPX 브릿지는 미구현 상태다."""
        from ai_orchestrator.domain.model_adapters import get_bridge

        b = get_bridge("hwpx-bridge")
        assert b is not None
        assert not b.is_implemented()

    def test_office_bridge_not_implemented(self):
        """Office/Excel 브릿지는 미구현 상태다."""
        from ai_orchestrator.domain.model_adapters import get_bridge

        b = get_bridge("office-bridge")
        assert b is not None
        assert not b.is_implemented()

    def test_external_app_hold_work_trade_classification(self):
        """WorkTrade 모델로 CAD/HWPX/Excel HOLD를 표현할 수 있다."""
        from ai_orchestrator.domain.models import WorkTrade, WorkTradeScope

        for app in ["CAD", "HWPX", "Excel"]:
            wt = WorkTrade(
                work_trade_id=f"wt-{app.lower()}",
                name=f"{app} 작업",
                description=f"{app} 외부 앱 필요",
                scope=WorkTradeScope.EXTERNAL_APP_HOLD,
                execution_location="LOCAL_AGENT_REQUIRED",
                external_app_hold=True,
            )
            assert wt.is_external_app_hold(), f"{app} HOLD 표현 실패"

    def test_bid_and_tax_user_direct_required(self):
        """입찰/세무는 USER_DIRECT_REQUIRED 위치다."""
        from ai_orchestrator.domain.model_adapters import get_bridge

        bid = get_bridge("bid-bridge")
        tax = get_bridge("tax-bridge")
        assert bid.execution_location == "USER_DIRECT_REQUIRED"
        assert tax.execution_location == "USER_DIRECT_REQUIRED"


# ===========================================================================
# 12. 기존 API contract / 테스트 충돌 없음 검증
# ===========================================================================


class TestNoContractBreak:
    """기존 API 계약 영향 없음 테스트."""

    def test_existing_domain_enums_still_importable(self):
        """기존 domain/enums.py가 변경 없이 import된다."""
        from ai_orchestrator.domain.enums import RiskLevel, TaskStatus, Verdict

        assert RiskLevel.LOW == "low"
        assert TaskStatus.PENDING == "pending"
        assert Verdict.PASS == "PASS"

    def test_existing_response_envelope_still_importable(self):
        """기존 domain/response_envelope.py가 변경 없이 동작한다."""
        from ai_orchestrator.domain.response_envelope import api_success

        r = api_success(data={"x": 1})
        assert r.success is True

    def test_existing_response_adapter_still_importable(self):
        """기존 domain/response_adapter.py가 변경 없이 동작한다."""
        from ai_orchestrator.domain.response_adapter import wrap_legacy_dict

        r = wrap_legacy_dict({"y": 2})
        assert r.data == {"y": 2}

    def test_new_domain_init_exports_all(self):
        """domain/__init__.py가 모든 모델을 export한다."""
        import ai_orchestrator.domain as d

        for name in (
            "Task",
            "WorkTrade",
            "ExternalWork",
            "Integration",
            "Artifact",
            "SafetyPolicy",
            "ExternalAppBridge",
            "AuditEvent",
        ):
            assert hasattr(d, name), f"domain.__init__ 누락: {name}"

    def test_runtime_endpoint_count_unchanged(self):
        """runtime endpoint 수가 60개로 변경되지 않았다."""
        from tests.app_routes import EXPECTED_RUNTIME_ROUTES, runtime_routes

        routes = runtime_routes()
        # APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_01: app_status_router GET 3개 추가 → 60+3=63
        # 2026-10-05 갱신(63→425): 저장소 성장·FastAPI 0.142 로 지연 include 래퍼를 펼쳐 실제 라우트를 보게 됨(EXPECTED_RUNTIME_ROUTES 와 일치)
        assert len(routes) == EXPECTED_RUNTIME_ROUTES, f"endpoint 수 변경 감지: {len(routes)}"  # 기대값 정본: configs/route_count_expectation.json (라우트를 추가·삭제하면 그 파일만 고친다)

    def test_health_endpoint_unchanged(self):
        """health endpoint 응답 구조가 변경되지 않았다."""
        from fastapi.testclient import TestClient

        from ai_orchestrator.asgi import app

        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        assert "success" not in data
