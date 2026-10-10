"""ASSISTANT_BACKEND_API_CONTRACT_AUDIT_AND_SAFE_ADOPTION_01 — 계약 감사 테스트.

API 출입구 전수조사 결과를 기준선으로 고정한다.
DB, 서버, 외부 URL, 브라우저 실행 없음.
"""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# 1. Enum 공종 — 기존 중복 정의와 충돌 없음 확인
# ---------------------------------------------------------------------------


def test_domain_enum_import_clean():
    from ai_orchestrator.domain.enums import (
        ApprovalStatus,
        ExecutionLocation,
        RiskLevel,
        TaskStatus,
        Verdict,
    )

    # 기존 소문자 문자열과 값 호환
    assert RiskLevel.HIGH == "high"
    assert ExecutionLocation.BLOCKED == "BLOCKED"
    assert TaskStatus.PENDING == "pending"
    assert ApprovalStatus.ISSUED == "issued"
    assert Verdict.PASS == "PASS"


def test_domain_enum_no_conflict_with_scripts_schemas():
    """scripts/common/schemas.py RiskLevel(AUTO/NOTIFY)과 다른 네임스페이스."""
    from ai_orchestrator.domain.enums import RiskLevel as OrchestratorRiskLevel
    from scripts.common.schemas import RiskLevel as ScriptsRiskLevel

    # 서로 다른 클래스여야 한다 (충돌 없음)
    assert OrchestratorRiskLevel is not ScriptsRiskLevel
    # 값이 겹치지 않음 — 도메인이 다름
    orch_values = {m.value for m in OrchestratorRiskLevel}
    scripts_values = {m.value for m in ScriptsRiskLevel}
    assert orch_values.isdisjoint(scripts_values)


def test_domain_enum_no_conflict_with_site_engine_execution_location():
    """scripts/site_engine/site_types.py ExecutionLocation과 별개 공존."""
    from ai_orchestrator.domain.enums import ExecutionLocation as OrchestratorEL
    from scripts.site_engine.site_types import ExecutionLocation as SiteEngineEL

    assert OrchestratorEL is not SiteEngineEL
    # ai_orchestrator 5값, site_engine 3값 — 별개 도메인
    assert len(list(OrchestratorEL)) == 5
    assert len(list(SiteEngineEL)) == 3


# ---------------------------------------------------------------------------
# 2. Response Envelope 공종
# ---------------------------------------------------------------------------


def test_api_success_json_serializable():
    from ai_orchestrator.domain.response_envelope import api_success

    resp = api_success(data={"task_id": "abc", "status": "pending"})
    j = resp.model_dump()
    assert j["success"] is True
    assert j["data"]["task_id"] == "abc"
    # JSON 직렬화 가능
    raw = json.dumps(j)
    loaded = json.loads(raw)
    assert loaded["success"] is True


def test_api_error_json_serializable():
    from ai_orchestrator.domain.response_envelope import api_error

    resp = api_error(code="AGENT_NOT_FOUND", message="에이전트 없음", details={"agent_id": "x"})
    j = resp.model_dump()
    assert j["success"] is False
    assert j["error"]["code"] == "AGENT_NOT_FOUND"
    raw = json.dumps(j)
    loaded = json.loads(raw)
    assert loaded["error"]["message"] == "에이전트 없음"


def test_api_meta_optional():
    from ai_orchestrator.domain.response_envelope import ApiMeta, api_success

    # meta 없음
    r1 = api_success(data=[1, 2, 3])
    assert r1.meta is None
    # meta 있음
    r2 = api_success(data=[1, 2, 3], meta=ApiMeta(total=3, page=1, page_size=20))
    assert r2.meta.total == 3


# ---------------------------------------------------------------------------
# 3. response_adapter thin wrapper 공종
# ---------------------------------------------------------------------------


def test_wrap_legacy_dict():
    from ai_orchestrator.domain.response_adapter import wrap_legacy_dict

    data = {"task_id": "t1", "status": "ok", "risk_level": "low"}
    resp = wrap_legacy_dict(data)
    j = resp.model_dump()
    assert j["success"] is True
    assert j["data"]["task_id"] == "t1"
    assert j["data"]["risk_level"] == "low"


def test_wrap_legacy_list_with_meta():
    from ai_orchestrator.domain.response_adapter import wrap_legacy_list

    items = [{"id": 1}, {"id": 2}]
    resp = wrap_legacy_list(items, total=2, page=1, page_size=20)
    j = resp.model_dump()
    assert j["success"] is True
    assert len(j["data"]) == 2
    assert j["meta"]["total"] == 2


def test_wrap_legacy_list_no_meta():
    from ai_orchestrator.domain.response_adapter import wrap_legacy_list

    resp = wrap_legacy_list([{"x": 1}])
    assert resp.meta is None


def test_wrap_http_exception():
    from ai_orchestrator.domain.response_adapter import wrap_http_exception

    resp = wrap_http_exception("TASK_MISMATCH", "태스크 불일치", details={"task_id": "t1"})
    j = resp.model_dump()
    assert j["success"] is False
    assert j["error"]["code"] == "TASK_MISMATCH"
    assert j["error"]["details"]["task_id"] == "t1"


# ---------------------------------------------------------------------------
# 4. API 출입구 공종 — 핵심 router import 검증
# ---------------------------------------------------------------------------


def test_router_imports_clean():
    """핵심 sub-router들이 import error 없이 로드된다.

    router.py 자체는 server.py와 순환 의존이 있으므로 직접 import하지 않는다.
    TestClient(app) 경로로 서버 전체 기동이 검증된다 (test_health_endpoint_unchanged).
    """
    import ai_orchestrator.agent_hub.router.root as lar
    import ai_orchestrator.auth.auth_router as auth
    import ai_orchestrator.routers.admin_ui_router as aur
    import ai_orchestrator.web_task.web_task_router as wtr

    assert lar.local_agent_router is not None
    assert aur.admin_ui_router is not None
    assert auth.auth_router is not None
    assert wtr.web_task_router is not None


def test_approval_record_router_imports_clean():
    from ai_orchestrator.browser_tool.approval.approval_record_router import (
        approval_record_router,
    )

    assert approval_record_router is not None


def test_sites_router_imports_clean():
    from ai_orchestrator.sites.router import sites_router

    assert sites_router is not None


def test_naver_search_router_imports_clean():
    from ai_orchestrator.connectors.naver_search.naver_search_router import naver_search_router

    assert naver_search_router is not None


# ---------------------------------------------------------------------------
# 5. HEALTH_OR_STATUS endpoint — 기존 응답 구조 고정
# ---------------------------------------------------------------------------


def test_health_endpoint_unchanged():
    """GET /health 응답이 기존 {"status":"ok","service":...} 구조를 유지한다."""
    from fastapi.testclient import TestClient

    from ai_orchestrator.asgi import app

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert "service" in data
    # ApiResponse 봉투가 아님 — success 키 없어야 함
    assert "success" not in data


# ---------------------------------------------------------------------------
# 6. 기존 테스트 기대값 보존 확인 — approval key 구조
# ---------------------------------------------------------------------------


def test_approval_response_keys_unchanged():
    """approval_record_router가 ApprovalRecordResponse 모델을 그대로 반환한다."""
    from ai_orchestrator.browser_tool.approval.approval_record_router import (
        ApprovalRecordResponse,
    )

    assert hasattr(ApprovalRecordResponse, "model_fields")
    # 응답 모델에 success 봉투가 없음 — 기존 구조 보존
    fields = set(ApprovalRecordResponse.model_fields.keys())
    assert "success" not in fields


# ---------------------------------------------------------------------------
# 7. domain 패키지 전체 import — 순환 의존 없음 확인
# ---------------------------------------------------------------------------


def test_domain_package_no_circular_import():
    from ai_orchestrator.domain import enums, response_adapter, response_envelope

    # 모두 import 가능해야 한다
    assert enums.RiskLevel is not None
    assert response_envelope.ApiResponse is not None
    assert response_adapter.wrap_legacy_dict is not None
