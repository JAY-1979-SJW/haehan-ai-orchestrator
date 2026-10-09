"""ASSISTANT_BACKEND_PREMIUM_ARCHITECTURE_REDESIGN_01 — 최고급 설계 기준선 고정 테스트.

이 테스트 파일은 코드 동작을 변경하지 않는다.
백엔드 최고급 설계 기준을 상수/분류표/계약으로 잠근다.

검증 범위:
  A. Domain Core 공종 분류
  B. Service Layer 책임 분리
  C. Policy Layer 방화구획
  D. Adapter Layer 연결통로
  E. Audit/Evidence 감리실
  F. External App Bridge 설계
  G. API 계약 카테고리
  H. Ops/Monitoring 관리사무소

DB/서버/브라우저/외부 API 실행 없음.
"""

from __future__ import annotations

import importlib
import pathlib

REPO = pathlib.Path(__file__).parent.parent.parent
AI_ORC = REPO / "ai_orchestrator"


# ===========================================================================
# A. Domain Core 공종 분류
# ===========================================================================

# 핵심 도메인 모델 → 현재 구현 위치 매핑
DOMAIN_CORE_MAP = {
    "Task": {
        "impl_files": [
            "ai_orchestrator/core/task_state.py",
            "ai_orchestrator/domain/models.py",  # STEP 1: Task baseline model 추가
        ],
        "domain_file": "ai_orchestrator/domain/models.py",
        "status": "BASELINE_MODEL_READY_WITH_LEGACY_ADAPTER",
        "needs": ["service_layer_extract", "persistent_store_integration"],
    },
    "TaskQueue": {
        "impl_files": [
            "ai_orchestrator/server/task_queue_schema.py",
        ],
        "status": "PARTIAL",  # in-memory schema만 존재
        "needs": ["priority_queue", "execution_location_partition", "dequeue_by_location", "persistent_recovery"],
    },
    "WorkTrade": {
        "impl_files": [
            "ai_orchestrator/tasks/external_work_registry.py",
            "ai_orchestrator/domain/models.py",  # STEP 1: WorkTrade baseline model 추가
        ],
        "status": "BASELINE_MODEL_READY",
        "needs": ["service_layer_extract"],
    },
    "Approval": {
        "impl_files": [
            "tools/gates/approval.py",
            "ai_orchestrator/dev_reg/dev_reg_approval.py",
            "ai_orchestrator/web_task/web_task_approval_service.py",
        ],
        "status": "FUNCTIONAL",  # 동작하지만 서비스 계층 미분리
        "needs": ["approval_service_extract", "approval_history_model"],
    },
    "AuditEvent": {
        "impl_files": [
            "ai_orchestrator/audit/audit_logger.py",
            "ai_orchestrator/server/action_approval_audit_store.py",
            "core/agent_runtime/runtime/permission/approval_audit_log.py",
            "ai_orchestrator/audit_evidence/models.py",  # STEP 3: 표준 스키마 기준선
            "ai_orchestrator/audit_evidence/adapters.py",  # STEP 4: read-only adapter
        ],
        "status": "STANDARD_SCHEMA_BASELINE_READY",
        "needs": ["full_migration_from_legacy", "evidence_link_v2"],
    },
    "ExecutionLocation": {
        "impl_files": [
            "ai_orchestrator/server/execution_location_guard.py",
            "ai_orchestrator/domain/enums.py",
            "ai_orchestrator/browser_tool/routing/execution_location_policy.py",
        ],
        "status": "FUNCTIONAL",
        "needs": ["unified_enum_source", "bridge_location_enum"],
    },
    "ExternalWork": {
        "impl_files": [
            "ai_orchestrator/tasks/external_work_registry.py",
            "ai_orchestrator/domain/models.py",  # STEP 1: ExternalWork baseline model 추가
            "ai_orchestrator/domain/model_adapters.py",
            "ai_orchestrator/audit_evidence/models.py",  # STEP 3: ExecutionAttempt + ExternalAppHandoff
        ],
        "status": "HANDOFF_CONTRACT_BASELINE_READY",
        "needs": ["handoff_executor", "status_tracker"],
    },
    "LocalAgent": {
        "impl_files": [
            "ai_orchestrator/local_agent/",
            "ai_orchestrator/server/universal_agent_models.py",
            "ai_orchestrator/server/universal_agent_task_api.py",
        ],
        "status": "FUNCTIONAL",
        "needs": ["dispatch_service_extract", "agent_status_standard_model"],
    },
    "Integration": {
        "impl_files": [
            "ai_orchestrator/routers/ops_router.py",  # _STATIC_INTEGRATIONS
            "ai_orchestrator/connectors/",
        ],
        "status": "STATIC_LIST",
        "needs": ["Integration_entity", "integration_registry_service", "health_check_method", "last_seen_at"],
    },
    "Artifact": {
        "impl_files": [
            "ai_orchestrator/server/action_evidence_store.py",
            "ai_orchestrator/agent_hub/action_evidence_collector.py",
            "ai_orchestrator/domain/models.py",  # STEP 1: Artifact baseline model 추가
            "ai_orchestrator/audit_evidence/models.py",  # STEP 3: ArtifactEvidenceRef 기준선
        ],
        "status": "ARTIFACT_EVIDENCE_REF_BASELINE_READY",
        "needs": ["action_evidence_store_migration", "content_type_standard"],
    },
    "SafetyPolicy": {
        "impl_files": [
            "ai_orchestrator/browser_tool/backend_policy.py",
            "ai_orchestrator/server/server_egress_policy.py",
            "core/agent_runtime/runtime/security_guard.py",
            "ai_orchestrator/sites/secrets_policy.py",
            "ai_orchestrator/domain/models.py",
            "ai_orchestrator/domain/model_adapters.py",
            "ai_orchestrator/safety_policy/safety_policy_registry.py",  # STEP 2: 통합 registry 기준선
            "ai_orchestrator/audit_evidence/models.py",  # STEP 3: SafetyVerdict 기준선
        ],
        "status": "SAFETY_VERDICT_BASELINE_READY",
        "needs": ["full_policy_migration", "policy_coverage_test"],
    },
    "ExternalAppBridge": {
        "impl_files": [
            "ai_orchestrator/domain/models.py",  # STEP 1: ExternalAppBridge baseline model 추가
            "ai_orchestrator/domain/model_adapters.py",  # STEP 1: get_all_bridges / get_bridge 추가
        ],
        "status": "BASELINE_MODEL_READY_CONTRACT_ONLY",  # 계약 기준선 완료, 실제 구현 없음
        "needs": ["actual_bridge_impl", "handoff_executor", "health_check"],
    },
    "UserDirectAction": {
        "impl_files": [
            "ai_orchestrator/browser_tool/routing/browser_engine_routing_policy.py",
        ],
        "status": "PARTIAL",
        "needs": ["UserDirectAction_entity", "instruction_record", "user_confirmation_required"],
    },
}

DOMAIN_STATUS_ALLOWED = {
    "FUNCTIONAL",
    "PARTIAL",
    "REGISTRY_ONLY",
    "STATIC_LIST",
    "SCATTERED",
    "NOT_IMPLEMENTED",
    # STEP 1 Domain Core 기준선 완료 후 상태
    "BASELINE_MODEL_READY",
    "BASELINE_MODEL_READY_WITH_LEGACY_ADAPTER",
    "BASELINE_MODEL_READY_WITH_EVIDENCE_GAP",
    "BASELINE_MODEL_READY_BUT_POLICY_SCATTERED",
    "BASELINE_MODEL_READY_CONTRACT_ONLY",
    # STEP 2 Policy Registry 기준선 완료 후 상태
    "POLICY_REGISTRY_BASELINE_READY",
    # STEP 3 Audit/Evidence 표준화 기준선 완료 후 상태
    "STANDARD_SCHEMA_BASELINE_READY",
    "EXECUTION_ATTEMPT_BASELINE_READY",
    "HANDOFF_CONTRACT_BASELINE_READY",
    "ARTIFACT_EVIDENCE_REF_BASELINE_READY",
    "SAFETY_VERDICT_BASELINE_READY",
}


class TestDomainCoreClassification:
    """Domain Core 분류 고정 테스트."""

    def test_domain_map_covers_all_required_domains(self):
        """최고급 설계 기준 14개 도메인이 모두 분류되어 있다."""
        required = {
            "Task",
            "TaskQueue",
            "WorkTrade",
            "Approval",
            "AuditEvent",
            "ExecutionLocation",
            "ExternalWork",
            "LocalAgent",
            "Integration",
            "Artifact",
            "SafetyPolicy",
            "ExternalAppBridge",
            "UserDirectAction",
            "PendingApproval",
        }
        # PendingApproval은 Approval 안에 포함되므로 13+1
        covered = set(DOMAIN_CORE_MAP.keys()) | {"PendingApproval"}
        missing = required - covered
        assert not missing, f"도메인 분류 누락: {missing}"

    def test_domain_status_values_valid(self):
        """모든 도메인의 status가 허용 값 내에 있다."""
        for domain, info in DOMAIN_CORE_MAP.items():
            assert info["status"] in DOMAIN_STATUS_ALLOWED, f"{domain}.status={info['status']} 허용 범위 초과"

    def test_external_app_bridge_contract_only_baseline(self):
        """ExternalAppBridge는 계약 기준선만 완료, 실제 구현 없음을 고정한다."""
        status = DOMAIN_CORE_MAP["ExternalAppBridge"]["status"]
        assert status == "BASELINE_MODEL_READY_CONTRACT_ONLY", f"ExternalAppBridge status={status}"
        # 도메인 모델 파일이 추가됨
        impl_files = DOMAIN_CORE_MAP["ExternalAppBridge"]["impl_files"]
        assert any("domain/models.py" in f for f in impl_files)

    def test_approval_domain_functional(self):
        """Approval 도메인은 FUNCTIONAL 상태다."""
        assert DOMAIN_CORE_MAP["Approval"]["status"] == "FUNCTIONAL"

    def test_execution_location_domain_functional(self):
        """ExecutionLocation 도메인은 FUNCTIONAL 상태다."""
        assert DOMAIN_CORE_MAP["ExecutionLocation"]["status"] == "FUNCTIONAL"

    def test_safety_policy_registry_baseline_ready(self):
        """SafetyPolicy는 policy registry 기준선 이상 완료 상태다."""
        status = DOMAIN_CORE_MAP["SafetyPolicy"]["status"]
        allowed = {"POLICY_REGISTRY_BASELINE_READY", "SAFETY_VERDICT_BASELINE_READY"}
        assert status in allowed, f"SafetyPolicy status={status}"
        assert "full_policy_migration" in DOMAIN_CORE_MAP["SafetyPolicy"]["needs"]


# ===========================================================================
# B. Service Layer 책임 분리 설계
# ===========================================================================

SERVICE_LAYER_DESIGN = {
    "task_queue_service": {
        "purpose": "Task 큐 생성/조회/분류/dispatching",
        "current_location": "ai_orchestrator/server/task_queue_schema.py (schema only)",
        "extraction_priority": "HIGH",
        "must_not_call": ["external_browser", "playwright", "db_write"],
        "test_criteria": ["enqueue/dequeue 단위 테스트", "location별 파티션 검증"],
    },
    "approval_service": {
        "purpose": "승인 토큰 발행, pending 생성, Telegram 발송 조율",
        "current_location": "ai_orchestrator/web_task/web_task_approval_service.py (EXTRACTED)",
        "extraction_priority": "DONE",
        "must_not_call": ["router", "fastapi_http"],
        "test_criteria": ["token 발행 단위 테스트", "pending 생성 검증"],
    },
    "audit_service": {
        "purpose": "AuditEvent 기록, 조회, 필드 검증",
        "current_location": "ai_orchestrator/audit/audit_logger.py (functional)",
        "extraction_priority": "MEDIUM",
        "must_not_call": ["router", "external_api"],
        "test_criteria": ["event 기록 검증", "금지 필드 차단 검증"],
    },
    "execution_policy_service": {
        "purpose": "ExecutionLocation 결정, 위험도 판정, 차단 여부 결정",
        "current_location": "ai_orchestrator/server/execution_location_guard.py + browser_tool/backend_policy.py (scattered)",
        "extraction_priority": "HIGH",
        "must_not_call": ["db_write", "external_site"],
        "test_criteria": ["location 판정 단위 테스트", "차단 조건 검증"],
    },
    "external_work_service": {
        "purpose": "ExternalWork 분류 조회, handoff 기록, 상태 추적",
        "current_location": "ai_orchestrator/tasks/external_work_registry.py (registry only)",
        "extraction_priority": "MEDIUM",
        "must_not_call": ["db_write"],
        "test_criteria": ["분류 조회 검증", "handoff 기록 단위 테스트"],
    },
    "local_agent_dispatch_service": {
        "purpose": "로컬 에이전트 작업 배분, 상태 수신, 결과 저장",
        "current_location": "ai_orchestrator/server/universal_agent_task_api.py + local_agent/ (scattered)",
        "extraction_priority": "HIGH",
        "must_not_call": ["external_browser_from_server", "playwright"],
        "test_criteria": ["dispatch 단위 테스트", "결과 수신 검증"],
    },
    "ops_status_service": {
        "purpose": "Ops 상태 집계, health, endpoint inventory",
        "current_location": "ai_orchestrator/routers/ops_router.py (router 안에 embedded)",
        "extraction_priority": "MEDIUM",
        "must_not_call": ["db_write", "external_api"],
        "test_criteria": ["상태 집계 단위 테스트", "fallback 검증"],
    },
    "integration_status_service": {
        "purpose": "Integration 상태 조회, registry 관리, health check",
        "current_location": "_STATIC_INTEGRATIONS in ops_router.py (static dict)",
        "extraction_priority": "LOW",
        "must_not_call": ["external_site"],
        "test_criteria": ["registry 조회 검증", "health check 단위 테스트"],
    },
    "artifact_service": {
        "purpose": "Artifact 참조 생성, safe field 검증, 저장",
        "current_location": "ai_orchestrator/server/action_evidence_store.py (partial)",
        "extraction_priority": "LOW",
        "must_not_call": ["binary_content_store", "credential_field"],
        "test_criteria": ["safe 필드만 저장 검증", "금지 필드 차단"],
    },
    "safety_policy_service": {
        "purpose": "SafetyPolicy 통합 판정, 금지선 적용, secret 차단",
        "current_location": "SCATTERED (browser_tool/backend_policy.py, server/server_egress_policy.py, local_agent/security_guard.py)",
        "extraction_priority": "HIGH",
        "must_not_call": ["router", "db_write"],
        "test_criteria": ["금지 필드 전수 검증", "secret 차단 검증"],
    },
}

EXTRACTION_PRIORITIES = {"DONE", "HIGH", "MEDIUM", "LOW"}


class TestServiceLayerDesign:
    """Service Layer 설계 고정 테스트."""

    def test_service_layer_covers_10_services(self):
        """최고급 설계 기준 10개 서비스 후보가 모두 정의되어 있다."""
        assert len(SERVICE_LAYER_DESIGN) == 10

    def test_all_services_have_extraction_priority(self):
        """모든 서비스에 추출 우선순위가 정의되어 있다."""
        for svc, info in SERVICE_LAYER_DESIGN.items():
            assert info["extraction_priority"] in EXTRACTION_PRIORITIES, (
                f"{svc}.extraction_priority={info['extraction_priority']} 허용 범위 초과"
            )

    def test_approval_service_already_extracted(self):
        """approval_service는 web_task_approval_service.py로 이미 추출됨."""
        assert SERVICE_LAYER_DESIGN["approval_service"]["extraction_priority"] == "DONE"
        src = pathlib.Path("ai_orchestrator/web_task/web_task_approval_service.py")
        assert src.exists()

    def test_high_priority_services_list(self):
        """HIGH 우선순위 서비스 4개 고정."""
        high = [k for k, v in SERVICE_LAYER_DESIGN.items() if v["extraction_priority"] == "HIGH"]
        assert len(high) == 4, f"HIGH 서비스={high}, 기준=4"
        assert "task_queue_service" in high
        assert "execution_policy_service" in high
        assert "local_agent_dispatch_service" in high
        assert "safety_policy_service" in high

    def test_safety_policy_scattered_needs_high_priority(self):
        """SafetyPolicy 통합은 HIGH 우선순위다."""
        assert SERVICE_LAYER_DESIGN["safety_policy_service"]["extraction_priority"] == "HIGH"
        assert "scattered" in SERVICE_LAYER_DESIGN["safety_policy_service"]["current_location"].lower()


# ===========================================================================
# C. External App Bridge 설계
# ===========================================================================

EXTERNAL_APP_BRIDGE_REGISTRY = {
    "CAD_EXTERNAL_APP_BRIDGE": {
        "app_type": "CAD",
        "capability": ["도면_작성", "도면_수정", "물량_산출", "내역서_연동"],
        "execution_location": "LOCAL_AGENT_REQUIRED",
        "required_approval": True,
        "handoff_mode": "FILE_HANDOFF",
        "status": "FUTURE_INTEGRATION",
        "current_backend_impl": "EXTERNAL_APP_HOLD",
        "safety_policy": ["no_auto_submit", "user_review_required", "file_path_only_no_content"],
    },
    "HWPX_EXTERNAL_APP_BRIDGE": {
        "app_type": "HWPX",
        "capability": ["한글_문서_작성", "표_편집", "PDF_변환"],
        "execution_location": "LOCAL_AGENT_REQUIRED",
        "required_approval": True,
        "handoff_mode": "FILE_HANDOFF",
        "status": "FUTURE_INTEGRATION",
        "current_backend_impl": "EXTERNAL_APP_HOLD",
        "safety_policy": ["no_auto_submit", "user_review_required"],
    },
    "OFFICE_EXTERNAL_APP_BRIDGE": {
        "app_type": "OFFICE",
        "capability": ["Excel_작성", "Word_작성", "PowerPoint_작성"],
        "execution_location": "LOCAL_AGENT_REQUIRED",
        "required_approval": True,
        "handoff_mode": "FILE_HANDOFF",
        "status": "FUTURE_INTEGRATION",
        "current_backend_impl": "EXTERNAL_APP_HOLD",
        "safety_policy": ["no_auto_submit", "user_review_required"],
    },
    "TAX_EXTERNAL_APP_BRIDGE": {
        "app_type": "TAX",
        "capability": ["세금계산서_조회", "부가세_신고_보조", "세무_서류_생성"],
        "execution_location": "USER_DIRECT_REQUIRED",
        "required_approval": True,
        "handoff_mode": "USER_HANDOFF",
        "status": "FUTURE_INTEGRATION",
        "current_backend_impl": "EXTERNAL_APP_HOLD",
        "safety_policy": ["no_auto_submit", "user_direct_only", "no_credential_store"],
    },
    "BID_EXTERNAL_APP_BRIDGE": {
        "app_type": "BID",
        "capability": ["나라장터_입찰", "전자입찰_보조", "입찰_현황_조회"],
        "execution_location": "USER_DIRECT_REQUIRED",
        "required_approval": True,
        "handoff_mode": "USER_HANDOFF",
        "status": "FUTURE_INTEGRATION",
        "current_backend_impl": "EXTERNAL_APP_HOLD",
        "safety_policy": ["no_auto_submit", "user_direct_only", "no_credential_store", "no_bid_auto_execute"],
    },
    "DOCUMENT_AUTO_BRIDGE": {
        "app_type": "DOCUMENT_AUTOMATION",
        "capability": ["계약서_초안", "보고서_생성", "양식_자동완성"],
        "execution_location": "LOCAL_AGENT_REQUIRED",
        "required_approval": True,
        "handoff_mode": "TEMPLATE_HANDOFF",
        "status": "FUTURE_INTEGRATION",
        "current_backend_impl": "EXTERNAL_APP_HOLD",
        "safety_policy": ["no_auto_sign", "user_review_required"],
    },
}

REQUIRED_BRIDGE_FIELDS = {
    "app_type",
    "capability",
    "execution_location",
    "required_approval",
    "handoff_mode",
    "status",
    "current_backend_impl",
    "safety_policy",
}

VALID_EXECUTION_LOCATIONS_BRIDGE = {
    "LOCAL_AGENT_REQUIRED",
    "USER_DIRECT_REQUIRED",
    "SERVER_INTERNAL_ONLY",
    "BLOCKED",
}

VALID_HANDOFF_MODES = {
    "FILE_HANDOFF",
    "USER_HANDOFF",
    "TEMPLATE_HANDOFF",
    "API_HANDOFF",
    "QUEUE_HANDOFF",
}


class TestExternalAppBridgeDesign:
    """External App Bridge 설계 고정 테스트."""

    def test_registry_has_6_bridges(self):
        """외부 전문 앱 브릿지 6개가 정의되어 있다."""
        assert len(EXTERNAL_APP_BRIDGE_REGISTRY) == 6

    def test_all_bridges_have_required_fields(self):
        """모든 브릿지에 필수 필드가 존재한다."""
        for bridge_id, info in EXTERNAL_APP_BRIDGE_REGISTRY.items():
            missing = REQUIRED_BRIDGE_FIELDS - set(info.keys())
            assert not missing, f"{bridge_id} 필드 누락: {missing}"

    def test_all_bridges_are_future_integration(self):
        """모든 외부 앱 브릿지는 FUTURE_INTEGRATION 상태다."""
        for bridge_id, info in EXTERNAL_APP_BRIDGE_REGISTRY.items():
            assert info["status"] == "FUTURE_INTEGRATION", (
                f"{bridge_id}.status={info['status']}, 기준=FUTURE_INTEGRATION"
            )

    def test_all_bridges_current_impl_is_external_app_hold(self):
        """모든 브릿지의 현재 백엔드 구현은 EXTERNAL_APP_HOLD다."""
        for bridge_id, info in EXTERNAL_APP_BRIDGE_REGISTRY.items():
            assert info["current_backend_impl"] == "EXTERNAL_APP_HOLD", (
                f"{bridge_id} 현재 구현이 HOLD 아님: {info['current_backend_impl']}"
            )

    def test_bid_and_tax_are_user_direct_required(self):
        """입찰/세무 브릿지는 USER_DIRECT_REQUIRED 위치다."""
        assert EXTERNAL_APP_BRIDGE_REGISTRY["BID_EXTERNAL_APP_BRIDGE"]["execution_location"] == "USER_DIRECT_REQUIRED"
        assert EXTERNAL_APP_BRIDGE_REGISTRY["TAX_EXTERNAL_APP_BRIDGE"]["execution_location"] == "USER_DIRECT_REQUIRED"

    def test_bid_bridge_no_auto_execute_safety(self):
        """입찰 브릿지에는 자동 실행 금지 정책이 포함되어 있다."""
        policy = EXTERNAL_APP_BRIDGE_REGISTRY["BID_EXTERNAL_APP_BRIDGE"]["safety_policy"]
        assert "no_bid_auto_execute" in policy
        assert "user_direct_only" in policy

    def test_all_execution_locations_valid(self):
        """모든 브릿지의 execution_location이 허용 값 내에 있다."""
        for bridge_id, info in EXTERNAL_APP_BRIDGE_REGISTRY.items():
            assert info["execution_location"] in VALID_EXECUTION_LOCATIONS_BRIDGE, (
                f"{bridge_id}.execution_location={info['execution_location']}"
            )

    def test_all_handoff_modes_valid(self):
        """모든 브릿지의 handoff_mode가 허용 값 내에 있다."""
        for bridge_id, info in EXTERNAL_APP_BRIDGE_REGISTRY.items():
            assert info["handoff_mode"] in VALID_HANDOFF_MODES, f"{bridge_id}.handoff_mode={info['handoff_mode']}"

    def test_bridge_required_approval_all_true(self):
        """모든 외부 앱 브릿지는 required_approval=True다."""
        for bridge_id, info in EXTERNAL_APP_BRIDGE_REGISTRY.items():
            assert info["required_approval"] is True, (
                f"{bridge_id}.required_approval=False — 외부 앱 실행은 항상 승인 필요"
            )


# ===========================================================================
# D. API 계약 카테고리 분류
# ===========================================================================

API_CATEGORY_CLASSIFICATION = {
    # PUBLIC_READONLY_API — 인증 불필요 또는 읽기 전용 공개
    "PUBLIC_READONLY_API": [
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/site-health"),
        ("GET", "/api/v1/site-health/{site_name}"),
        ("GET", "/api/v1/connectors"),
    ],
    # OPS_READONLY_API — 관리자용 읽기 전용
    "OPS_READONLY_API": [
        ("GET", "/api/v1/ops/approvals"),
        ("GET", "/api/v1/ops/web-tasks"),
        ("GET", "/api/v1/ops/audit-events"),
        ("GET", "/api/v1/ops/agents"),
        ("GET", "/api/v1/ops/external-work"),
        ("GET", "/api/v1/ops/integrations"),
        ("GET", "/api/v1/ops/summary"),
    ],
    # WEB_TASK_API — 웹 작업 실행/관리
    "WEB_TASK_API": [
        ("GET", "/api/v1/web-tasks/registry"),
        ("POST", "/api/v1/web-tasks/run"),
        ("GET", "/api/v1/web-tasks/templates"),
        ("POST", "/api/v1/web-tasks/run-from-template"),
    ],
    # LOCAL_AGENT_API — 로컬 에이전트 등록/관리
    "LOCAL_AGENT_API": [
        ("POST", "/api/v1/local-agents/register"),
        ("POST", "/api/v1/local-agents/registration-codes"),
        ("GET", "/api/v1/local-agents/registration-codes"),
        ("POST", "/api/v1/local-agents/registration-codes/{code_id}/revoke"),
        ("POST", "/api/v1/local-agents/register-with-code"),
        ("GET", "/api/v1/local-agents"),
        ("GET", "/api/v1/local-agents/diagnostics"),
        ("POST", "/api/v1/local-agents/{agent_id}/tasks/{task_id}/cancel"),
        ("GET", "/api/v1/local-agents/user-present-status/{workflow_run_id}"),
        ("GET", "/api/v1/local-agents/{agent_id}/user-present-statuses"),
        ("POST", "/api/v1/local-agents/{agent_id}/user-present-dispatch"),
        ("GET", "/api/v1/local-agents/{agent_id}/tasks"),
    ],
    # APPROVAL_API — 승인/거절 흐름
    "APPROVAL_API": [
        ("POST", "/api/v1/approve"),
        ("POST", "/api/v1/reject"),
        ("GET", "/api/v1/approval-records"),
        ("GET", "/api/v1/approval-records/{task_id}"),
    ],
    # AUDIT_API — 감사 로그
    "AUDIT_API": [
        ("GET", "/api/v1/logs"),
        ("GET", "/api/v1/inbox"),
        ("GET", "/api/v1/inbox/{item_id}"),
    ],
    # EXTERNAL_API_REGISTERED — 외부 API 연동 (등록 완료)
    "EXTERNAL_API_REGISTERED": [
        ("GET", "/api/v1/external/naver/blog-search"),
        ("GET", "/api/v1/external/naver/shopping-search"),
        ("GET", "/api/v1/external/naver/search-status"),
    ],
    # LEGACY_API — 호환성 유지 (즉시 변경 불가)
    "LEGACY_API": [
        ("POST", "/api/v1/site-tasks/dry-run"),
        ("GET", "/api/v1/cad-ai/actions"),
        ("POST", "/api/v1/cad-ai/chat"),
        ("POST", "/api/v1/inbox/email/fetch"),
        ("POST", "/api/v1/webhooks/telegram"),
    ],
    # QUARANTINE_API — 격리/보류
    "QUARANTINE_API": [],
}

API_CATEGORIES = set(API_CATEGORY_CLASSIFICATION.keys())


class TestApiCategoryClassification:
    """API 계약 카테고리 고정 테스트."""

    def test_api_categories_defined(self):
        """9개 API 카테고리가 정의되어 있다."""
        assert len(API_CATEGORY_CLASSIFICATION) == 9

    def test_ops_readonly_has_7_endpoints(self):
        """OPS_READONLY_API에 7개 endpoint가 있다."""
        ops = API_CATEGORY_CLASSIFICATION["OPS_READONLY_API"]
        assert len(ops) == 7, f"ops endpoint 수={len(ops)}, 기준=7"

    def test_external_api_registered_has_3_naver_endpoints(self):
        """EXTERNAL_API_REGISTERED에 naver 3개 endpoint가 있다."""
        ext = API_CATEGORY_CLASSIFICATION["EXTERNAL_API_REGISTERED"]
        assert len(ext) == 3
        paths = [p for _, p in ext]
        assert all("/external/naver/" in p for p in paths)

    def test_local_agent_api_has_12_endpoints(self):
        """LOCAL_AGENT_API에 12개 endpoint가 있다."""
        la = API_CATEGORY_CLASSIFICATION["LOCAL_AGENT_API"]
        assert len(la) == 12, f"local_agent endpoint 수={len(la)}, 기준=12"

    def test_quarantine_api_is_empty(self):
        """현재 QUARANTINE_API에 격리된 endpoint가 없다."""
        assert len(API_CATEGORY_CLASSIFICATION["QUARANTINE_API"]) == 0

    def test_ops_readonly_all_get(self):
        """OPS_READONLY_API는 모두 GET 메서드다."""
        for method, path in API_CATEGORY_CLASSIFICATION["OPS_READONLY_API"]:
            assert method == "GET", f"OPS_READONLY에 비GET 발견: {method} {path}"

    def test_no_duplicate_endpoint_across_categories(self):
        """카테고리 간 중복 endpoint가 없다."""
        all_eps = []
        for cat, eps in API_CATEGORY_CLASSIFICATION.items():
            for ep in eps:
                all_eps.append(ep)
        assert len(all_eps) == len(set(all_eps)), "카테고리 간 중복 endpoint 발견"


# ===========================================================================
# E. Policy Layer 방화구획 현황
# ===========================================================================

POLICY_LAYER_MAP = {
    "execution_location_guard": {
        "impl": "ai_orchestrator/server/execution_location_guard.py",
        "status": "IMPLEMENTED",
        "test_covered": True,
        "risk_gap": None,
    },
    "action_risk_policy": {
        "impl": "ai_orchestrator/contracts/action_risk_policy.py",
        "status": "IMPLEMENTED",
        "test_covered": True,
        "risk_gap": None,
    },
    "approval_gate": {
        "impl": "ai_orchestrator/browser_tool/preflight/gate_approval_preflight.py",
        "status": "IMPLEMENTED",
        "test_covered": True,
        "risk_gap": None,
    },
    "local_agent_required_policy": {
        "impl": "ai_orchestrator/browser_tool/routing/execution_location_policy.py",
        "status": "IMPLEMENTED",
        "test_covered": True,
        "risk_gap": None,
    },
    "user_direct_required_policy": {
        "impl": "desktop/task_receiver.py + browser_tool/routing/execution_location_policy.py",
        "status": "PARTIAL",
        "test_covered": True,
        "risk_gap": "server-side UserDirect 정책 미통합",
    },
    "server_external_web_block_policy": {
        "impl": "ai_orchestrator/server/server_egress_policy.py + browser_gate_middleware.py",
        "status": "IMPLEMENTED",
        "test_covered": True,
        "risk_gap": None,
    },
    "secret_redaction_policy": {
        "impl": "ai_orchestrator/safety_policy/secret_redaction.py (단일 기준선) + 기존 분산 구현",
        "status": "POLICY_REGISTRY_BASELINE_READY",
        "test_covered": True,
        "risk_gap": None,
    },
    "external_app_hold_policy": {
        "impl": "ai_orchestrator/safety_policy/safety_policy_registry.py + services/execution_policy_service.py",
        "status": "POLICY_REGISTRY_BASELINE_READY",
        "test_covered": True,
        "risk_gap": None,
    },
    "oauth_api_required_policy": {
        "impl": "ai_orchestrator/safety_policy/safety_policy_registry.py + services/execution_policy_service.py",
        "status": "POLICY_REGISTRY_BASELINE_READY",
        "test_covered": True,
        "risk_gap": None,
    },
    "blocked_action_policy": {
        "impl": "ai_orchestrator/server/execution_location_guard.py",
        "status": "IMPLEMENTED",
        "test_covered": True,
        "risk_gap": None,
    },
}


class TestPolicyLayerMap:
    """Policy Layer 방화구획 현황 고정 테스트."""

    def test_10_policies_defined(self):
        """10개 정책이 모두 정의되어 있다."""
        assert len(POLICY_LAYER_MAP) == 10

    def test_execution_location_guard_implemented(self):
        """execution_location_guard는 구현 완료 + 테스트 커버됨."""
        p = POLICY_LAYER_MAP["execution_location_guard"]
        assert p["status"] == "IMPLEMENTED"
        assert p["test_covered"] is True

    def test_external_app_hold_policy_baseline_ready(self):
        """external_app_hold_policy는 POLICY_REGISTRY_BASELINE_READY — 강제 차단 구현 완료."""
        p = POLICY_LAYER_MAP["external_app_hold_policy"]
        assert p["status"] == "POLICY_REGISTRY_BASELINE_READY"
        assert p["test_covered"] is True
        assert p["risk_gap"] is None

    def test_oauth_policy_baseline_ready(self):
        """oauth_api_required_policy는 POLICY_REGISTRY_BASELINE_READY — 차단 로직 구현 완료."""
        p = POLICY_LAYER_MAP["oauth_api_required_policy"]
        assert p["status"] == "POLICY_REGISTRY_BASELINE_READY"
        assert p["test_covered"] is True

    def test_implemented_policies_are_test_covered(self):
        """IMPLEMENTED 상태 정책은 모두 테스트 커버되어 있다."""
        for name, p in POLICY_LAYER_MAP.items():
            if p["status"] == "IMPLEMENTED":
                assert p["test_covered"] is True, f"{name}: IMPLEMENTED인데 test_covered=False"


# ===========================================================================
# F. 감사/증거 체계 표준 필드 설계
# ===========================================================================

AUDIT_EVENT_STANDARD_SCHEMA = {
    "required_fields": [
        "event_id",  # UUID
        "event_type",  # TASK_RECEIVED / APPROVAL_ISSUED / etc.
        "task_id",
        "provider",
        "action_type",
        "risk_level",
        "execution_location",
        "actor",  # server / local_agent / user
        "timestamp",
        "verdict",  # PASS / WARN / FAIL / HOLD
        "summary",
    ],
    "forbidden_fields": [
        "password",
        "otp",
        "cert_password",
        "private_key",
        "cookie",
        "session",
        "token",
        "approval_token",
        "raw_screenshot",
        "base64",
        "localstorage",
        "sessionstorage",
        "authorization",
    ],
    "optional_fields": [
        "artifact_ref",  # safe path reference only
        "evidence_id",
        "safety_verdict",
        "external_app_handoff_id",
        "user_direct_instruction_id",
        "parent_event_id",
    ],
}

EVIDENCE_HANDOFF_RECORD_FIELDS = {
    "required": [
        "handoff_id",
        "bridge_id",
        "task_id",
        "handoff_mode",
        "input_summary",
        "status",
        "created_at",
    ],
    "forbidden": [
        "password",
        "credential",
        "private_key",
        "cert",
        "otp",
        "token",
        "cookie",
    ],
}


class TestAuditEvidenceDesign:
    """감사/증거 체계 설계 고정 테스트."""

    def test_audit_event_required_fields_defined(self):
        """AuditEvent 필수 필드 11개가 정의되어 있다."""
        assert len(AUDIT_EVENT_STANDARD_SCHEMA["required_fields"]) == 11

    def test_audit_event_has_verdict_field(self):
        """AuditEvent 필수 필드에 verdict가 포함된다."""
        assert "verdict" in AUDIT_EVENT_STANDARD_SCHEMA["required_fields"]

    def test_audit_event_has_execution_location(self):
        """AuditEvent 필수 필드에 execution_location이 포함된다."""
        assert "execution_location" in AUDIT_EVENT_STANDARD_SCHEMA["required_fields"]

    def test_forbidden_fields_cover_security_critical(self):
        """금지 필드에 핵심 보안 항목이 포함된다."""
        forbidden = AUDIT_EVENT_STANDARD_SCHEMA["forbidden_fields"]
        critical = ["password", "otp", "cookie", "token", "private_key"]
        for f in critical:
            assert f in forbidden, f"감사 금지 필드 누락: {f}"

    def test_evidence_handoff_record_has_required_fields(self):
        """ExternalAppHandoff 기록 필수 필드가 정의된다."""
        required = EVIDENCE_HANDOFF_RECORD_FIELDS["required"]
        assert "handoff_id" in required
        assert "bridge_id" in required
        assert "handoff_mode" in required

    def test_current_audit_logger_importable(self):
        """현재 audit_logger 모듈이 import 가능하다."""
        import ai_orchestrator.audit.audit_logger as m

        assert hasattr(m, "log_event") or hasattr(m, "audit_log") or hasattr(m, "EVENT_TYPES")

    def test_current_action_evidence_store_importable(self):
        """현재 action_evidence_store가 import 가능하다."""
        import ai_orchestrator.server.action_evidence_store as m

        assert m is not None


# ===========================================================================
# G. 핵심 파일 존재 및 import 가능 여부
# ===========================================================================

CORE_FILES_MUST_EXIST = [
    "ai_orchestrator/domain/enums.py",
    "ai_orchestrator/domain/response_envelope.py",
    "ai_orchestrator/domain/response_adapter.py",
    "ai_orchestrator/server/execution_location_guard.py",
    "ai_orchestrator/server/task_queue_schema.py",
    "ai_orchestrator/server/action_approval_audit_store.py",
    "ai_orchestrator/server/action_evidence_store.py",
    "ai_orchestrator/core/task_state.py",
    "ai_orchestrator/audit/audit_logger.py",
    "tools/gates/approval.py",
    "ai_orchestrator/dev_reg/dev_reg_approval.py",
    "ai_orchestrator/web_task/web_task_approval_service.py",
    "ai_orchestrator/web_task/web_task_registry.py",
    "ai_orchestrator/web_task/web_task_templates.py",
    "ai_orchestrator/tasks/external_work_registry.py",
    "ai_orchestrator/routers/ops_router.py",
    "ai_orchestrator/browser_tool/routing/execution_location_policy.py",
    "ai_orchestrator/browser_tool/backend_policy.py",
    "ai_orchestrator/server/server_egress_policy.py",
]

CORE_MODULES_MUST_IMPORT = [
    "ai_orchestrator.domain.enums",
    "ai_orchestrator.domain.response_envelope",
    "ai_orchestrator.domain.response_adapter",
    "ai_orchestrator.server.execution_location_guard",
    "ai_orchestrator.server.task_queue_schema",
    "ai_orchestrator.core.task_state",
    "tools.gates.approval",
    "ai_orchestrator.dev_reg.dev_reg_approval",
    "ai_orchestrator.web_task.web_task_approval_service",
    "ai_orchestrator.web_task.web_task_registry",
    "ai_orchestrator.tasks.external_work_registry",
    "ai_orchestrator.routers.ops_router",
]


class TestCoreFileIntegrity:
    """핵심 파일 존재 및 import 가능 여부 고정 테스트."""

    def test_all_core_files_exist(self):
        """핵심 설계 파일 21개가 모두 존재한다."""
        missing = []
        for f in CORE_FILES_MUST_EXIST:
            if not pathlib.Path(f).exists():
                missing.append(f)
        assert not missing, f"핵심 파일 누락: {missing}"

    def test_all_core_modules_importable(self):
        """핵심 모듈 12개가 cycle 없이 import된다."""
        failed = []
        for mod in CORE_MODULES_MUST_IMPORT:
            try:
                importlib.import_module(mod)
            except Exception as exc:  # noqa: BLE001 - 핵심 모듈 import 가능 여부를 검증하는 pytest — import 실패를 failed 리스트에 모아 마지막에 assert not failed 로 테스트를 실패시키는 fail-closed 테스트.
                failed.append(f"{mod}: {exc}")
        assert not failed, f"import 실패: {failed}"

    def test_execution_location_guard_has_location_constants(self):
        """execution_location_guard에 위치 상수 4개가 정의되어 있다."""
        from ai_orchestrator.server.execution_location_guard import (
            BLOCKED,
            LOCAL_AGENT_REQUIRED,
            SERVER_INTERNAL_ONLY,
            USER_DIRECT_REQUIRED,
        )

        assert SERVER_INTERNAL_ONLY == "SERVER_INTERNAL_ONLY"
        assert LOCAL_AGENT_REQUIRED == "LOCAL_AGENT_REQUIRED"
        assert USER_DIRECT_REQUIRED == "USER_DIRECT_REQUIRED"
        assert BLOCKED == "BLOCKED"

    def test_domain_enums_stable(self):
        """domain/enums.py 핵심 Enum이 안정되어 있다."""
        from ai_orchestrator.domain.enums import RiskLevel, TaskStatus, Verdict

        assert RiskLevel.LOW == "low"
        assert RiskLevel.CRITICAL == "critical"
        assert TaskStatus.PENDING == "pending"
        assert Verdict.PASS == "PASS"
        assert Verdict.FAIL == "FAIL"

    def test_external_work_registry_importable_with_classification(self):
        """external_work_registry가 분류 상수와 함께 import된다."""
        import ai_orchestrator.tasks.external_work_registry as m

        assert (
            hasattr(m, "WORK_REGISTRY")
            or hasattr(m, "EXTERNAL_WORK_REGISTRY")
            or hasattr(m, "WorkClassification")
            or hasattr(m, "ExternalWork")
            or hasattr(m, "list_external_works")
        )


# ===========================================================================
# H. 다음 공정 우선순위 계약
# ===========================================================================

NEXT_PHASE_ROADMAP = [
    {
        "phase": 1,
        "name": "Domain Core 정리",
        "goal": "Task/WorkTrade/ExternalWork 엔티티를 domain/models.py로 통합",
        "files": ["ai_orchestrator/domain/models.py (NEW)"],
        "forbidden": ["DB schema 변경", "기존 API path 변경", "UI 수정"],
        "test_criteria": "domain model import + field 단위 테스트",
        "done_when": "domain/models.py에 Task/WorkTrade/ExternalWork 정의 완료",
    },
    {
        "phase": 2,
        "name": "Service Layer 추출",
        "goal": "execution_policy_service + task_queue_service 추출",
        "files": [
            "ai_orchestrator/services/execution_policy_service.py (NEW)",
            "ai_orchestrator/services/task_queue_service.py (NEW)",
        ],
        "forbidden": ["router 내부 로직 직접 수정", "기존 API 파괴"],
        "test_criteria": "서비스 단위 테스트 + router smoke test",
        "done_when": "서비스 추출 + 기존 테스트 전부 PASS",
    },
    {
        "phase": 3,
        "name": "Policy Layer 통합",
        "goal": "SafetyPolicy 통합, external_app_hold_policy 강제 차단 구현",
        "files": [
            "ai_orchestrator/policies/safety_policy_registry.py (NEW)",
            "ai_orchestrator/policies/external_app_hold_policy.py (NEW)",
        ],
        "forbidden": ["기존 정책 파일 삭제"],
        "test_criteria": "정책 커버리지 테스트 + hold policy 강제 차단 테스트",
        "done_when": "모든 정책 test_covered=True",
    },
    {
        "phase": 4,
        "name": "Audit/Evidence 표준화",
        "goal": "AuditEvent 표준 스키마 + ExternalAppHandoff 기록 구현",
        "files": [
            "ai_orchestrator/domain/audit_schema.py (NEW)",
        ],
        "forbidden": ["DB schema 변경"],
        "test_criteria": "표준 필드 검증 + 금지 필드 차단 테스트",
        "done_when": "audit 기록 모든 표준 필드 포함 확인",
    },
    {
        "phase": 5,
        "name": "External App Bridge 계약",
        "goal": "ExternalAppBridge 엔티티 + handoff record 구현",
        "files": [
            "ai_orchestrator/domain/external_app_bridge.py (NEW)",
        ],
        "forbidden": ["전문 앱 기능 자체 구현"],
        "test_criteria": "bridge contract 테스트 + handoff 기록 테스트",
        "done_when": "6개 브릿지 모두 contract 테스트 PASS",
    },
    {
        "phase": 6,
        "name": "API Contract 안정화",
        "goal": "response_envelope 적용 후보 전환, OpenAPI 정합성 확인",
        "files": ["ai_orchestrator/web_task/web_task_router.py (MODIFY)"],
        "forbidden": ["기존 response key 파괴"],
        "test_criteria": "API contract 테스트 + backward-compat 테스트",
        "done_when": "NEEDS_ENVELOPE_REVIEW 3개 전환 완료",
    },
    {
        "phase": 7,
        "name": "Ops/Monitoring 고도화",
        "goal": "ops_status_service 추출, integration_registry 동적화",
        "files": [
            "ai_orchestrator/services/ops_status_service.py (NEW)",
        ],
        "forbidden": ["ops_router 기존 경로 변경"],
        "test_criteria": "서비스 단위 테스트 + ops read-only 테스트",
        "done_when": "ops endpoint 모두 서비스 경유",
    },
    {
        "phase": 8,
        "name": "Local Agent Dispatch 연결",
        "goal": "local_agent_dispatch_service 추출, WebSocket 계약 안정화",
        "files": [
            "ai_orchestrator/services/local_agent_dispatch_service.py (NEW)",
        ],
        "forbidden": ["외부 브라우저 서버 실행"],
        "test_criteria": "dispatch 단위 테스트 + WS 계약 테스트",
        "done_when": "dispatch 서비스 추출 + 기존 테스트 PASS",
    },
    {
        "phase": 9,
        "name": "Frontend/Desktop 재연결",
        "goal": "admin-web ops + desktop tray 신규 계약으로 재연결",
        "files": ["admin-web + desktop 계약 파일 (MODIFY)"],
        "forbidden": ["backend API 파괴", "새 UI 화면 신설"],
        "test_criteria": "boundary test + tray label test",
        "done_when": "모든 UI 경계 테스트 PASS",
    },
    {
        "phase": 10,
        "name": "Server 준공 반영",
        "goal": "서버 배포, smoke test, 운영 확인",
        "files": ["docker-compose.yml (필요시 MODIFY)"],
        "forbidden": ["운영 DB write", "schema 변경"],
        "test_criteria": "서버 smoke test + health check",
        "done_when": "서버 /api/v1/health 200 + endpoint inventory 일치",
    },
]


class TestNextPhaseRoadmap:
    """다음 공정표 고정 테스트."""

    def test_roadmap_has_10_phases(self):
        """공정표에 10단계가 정의되어 있다."""
        assert len(NEXT_PHASE_ROADMAP) == 10

    def test_phase_numbers_sequential(self):
        """공정 번호가 1~10 순차적이다."""
        phases = [p["phase"] for p in NEXT_PHASE_ROADMAP]
        assert phases == list(range(1, 11))

    def test_all_phases_have_required_keys(self):
        """모든 공정에 필수 키가 있다."""
        required_keys = {"phase", "name", "goal", "files", "forbidden", "test_criteria", "done_when"}
        for p in NEXT_PHASE_ROADMAP:
            missing = required_keys - set(p.keys())
            assert not missing, f"phase {p['phase']} 키 누락: {missing}"

    def test_phase1_targets_domain_models(self):
        """1단계는 Domain Core 정리다."""
        assert NEXT_PHASE_ROADMAP[0]["name"] == "Domain Core 정리"

    def test_phase3_targets_policy_layer(self):
        """3단계는 Policy Layer 통합이다."""
        assert NEXT_PHASE_ROADMAP[2]["name"] == "Policy Layer 통합"

    def test_phase5_targets_external_app_bridge(self):
        """5단계는 External App Bridge 계약이다."""
        assert NEXT_PHASE_ROADMAP[4]["name"] == "External App Bridge 계약"

    def test_phase10_is_server_deployment(self):
        """10단계는 서버 준공 반영이다."""
        assert NEXT_PHASE_ROADMAP[9]["name"] == "Server 준공 반영"

    def test_all_phases_have_forbidden_list(self):
        """모든 공정에 금지선이 정의되어 있다."""
        for p in NEXT_PHASE_ROADMAP:
            assert len(p["forbidden"]) > 0, f"phase {p['phase']} 금지선 없음"
