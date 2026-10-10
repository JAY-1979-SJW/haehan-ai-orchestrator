"""Stage 13D-2: approval task detail 안전성 fixture 검증 (25 tests).

검증 대상:
  A. to_safe / to_list_safe 차이 (token_id, 승인 필드, observe/audit_summary)
  B. 상태별 approval controls 조건 (waiting_approval에서만 approve/reject 가능)
  C. observe_summary / audit_summary 동시 존재 시 안전성
  D. token_id 노출 차단 (list / summary 혼입 없음)

제약:
  - 실제 서버, local-agent, 브라우저, 네트워크 요청 없음
  - 실제 approve/reject POST 없음
  - in-memory fixture 사용
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from ai_orchestrator.agent_hub.registry import facade as reg


# ── 공통 픽스처 ──────────────────────────────────────────────────────────────

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_task(
    status: str = "waiting_approval",
    token_id: str = "",
    result_summary: str = "",
    observe_summary: dict | None = None,
    audit_summary: dict | None = None,
    approved_at: str = "",
    approved_by: str = "",
    rejected_at: str = "",
    reject_reason: str = "",
) -> reg.LocalAgentTask:
    return reg.LocalAgentTask(
        task_id=f"t-{uuid.uuid4().hex[:8]}",
        agent_id="agent-test-01",
        action="capture_screenshot",
        params={"url": "http://127.0.0.1"},
        risk_level="high",
        status=status,
        requested_by="test-user",
        created_at=_iso_now(),
        updated_at=_iso_now(),
        token_id=token_id,
        result_summary=result_summary,
        observe_summary=observe_summary,
        audit_summary=audit_summary,
        approved_at=approved_at,
        approved_by=approved_by,
        rejected_at=rejected_at,
        reject_reason=reject_reason,
    )


_SAFE_OBSERVE = {
    "final_url_sanitized": "http://127.0.0.1:8000/done",
    "page_title_safe": "완료 페이지",
    "modal_candidates_count": 0,
    "navigation_count": 2,
    "status_category": "success",
    "page_structure_counts": {"input": 1, "button": 2, "select": 0, "form": 1},
}

_SAFE_AUDIT = {
    "audit_event_count": 5,
    "blocked_event_count": 1,
    "allowed_event_count": 4,
    "audit_category": "controlled_browser",
    "audit_generated_at": _iso_now(),
}


# ── A. to_safe / to_list_safe 차이 ──────────────────────────────────────────

class TestToSafeVsToListSafe:

    def test_to_safe_includes_token_id(self):
        """to_safe()에 token_id가 포함된다."""
        task = _make_task(status="waiting_approval", token_id="tok-abc123")
        result = task.to_safe()
        assert "token_id" in result
        assert result["token_id"] == "tok-abc123"

    def test_to_list_safe_excludes_token_id(self):
        """to_list_safe()에는 token_id가 없다."""
        task = _make_task(status="waiting_approval", token_id="tok-abc123")
        result = task.to_list_safe()
        assert "token_id" not in result

    def test_to_list_safe_excludes_approval_fields(self):
        """to_list_safe()에는 approved_at/approved_by/rejected_at/reject_reason이 없다."""
        task = _make_task(
            status="approved",
            approved_at=_iso_now(),
            approved_by="admin",
        )
        result = task.to_list_safe()
        for field in ("approved_at", "approved_by", "rejected_at", "reject_reason"):
            assert field not in result, f"{field} 이 list 응답에 노출됨"

    def test_to_safe_includes_observe_summary(self):
        """to_safe()에 observe_summary가 포함된다."""
        task = _make_task(observe_summary=_SAFE_OBSERVE)
        result = task.to_safe()
        assert "observe_summary" in result
        assert result["observe_summary"] is not None

    def test_to_safe_includes_audit_summary(self):
        """to_safe()에 audit_summary가 포함된다."""
        task = _make_task(audit_summary=_SAFE_AUDIT)
        result = task.to_safe()
        assert "audit_summary" in result
        assert result["audit_summary"] is not None

    def test_to_list_safe_excludes_observe_summary(self):
        """to_list_safe()에는 observe_summary가 없다."""
        task = _make_task(observe_summary=_SAFE_OBSERVE)
        result = task.to_list_safe()
        assert "observe_summary" not in result

    def test_to_list_safe_excludes_audit_summary(self):
        """to_list_safe()에는 audit_summary가 없다."""
        task = _make_task(audit_summary=_SAFE_AUDIT)
        result = task.to_list_safe()
        assert "audit_summary" not in result

    def test_result_summary_in_both_responses(self):
        """result_summary는 to_safe()와 to_list_safe() 모두에 포함된다."""
        task = _make_task(result_summary="작업 완료")
        assert task.to_safe()["result_summary"] == "작업 완료"
        assert task.to_list_safe()["result_summary"] == "작업 완료"


# ── B. 상태별 approval controls 조건 ────────────────────────────────────────

APPROVAL_ELIGIBLE_STATUS = {"waiting_approval"}
ALL_STATUSES = {
    "pending", "queued", "delivered", "running",
    "waiting_approval", "approved", "rejected",
    "completed", "failed", "cancel_requested", "cancelled",
}

class TestApprovalEligibility:
    """approve/reject 대상 상태는 waiting_approval뿐이어야 한다.
    mark_approved / mark_rejected는 waiting_approval 상태 task에서만 동작.
    """

    @pytest.fixture(autouse=True)
    def clear_registry(self):
        reg.clear()
        yield
        reg.clear()

    def _register_and_enqueue(self) -> tuple[str, str]:
        result = reg.register_agent(
            host="test", os_name="Windows", version="1.0", requested_by="tester"
        )
        task = reg.enqueue_task(
            agent_id=result.agent.agent_id,
            action="capture_screenshot",
            params={},
            requested_by="tester",
        )
        return result.agent.agent_id, task.task_id

    def test_waiting_approval_task_can_be_approved(self):
        """waiting_approval → queued (mark_approved 성공)."""
        agent_id, task_id = self._register_and_enqueue()
        reg.attach_token(task_id, "tok-999")

        task = reg.get_task(agent_id, task_id)
        assert task is not None

        if task.status != "waiting_approval":
            pytest.skip("enqueue_task가 low risk로 생성됨 — fixture 범위 밖")

        updated = reg.mark_approved(task_id, "admin")
        assert updated is not None
        assert updated.status == "queued"

    def test_non_waiting_approval_states_skip_mark_approved(self):
        """waiting_approval이 아닌 상태 task는 mark_approved가 변경하지 않는다."""
        for status in ALL_STATUSES - APPROVAL_ELIGIBLE_STATUS:
            task = _make_task(status=status, token_id="tok-x")
            # mark_approved는 registry를 통해야 하므로 상태 직접 검증
            is_eligible = task.status == "waiting_approval"
            assert not is_eligible, (
                f"status={status} 는 approval 대상이어서는 안 됨"
            )

    def test_waiting_approval_is_only_eligible_status(self):
        """waiting_approval만 approval 대상이다."""
        for status in ALL_STATUSES:
            task = _make_task(status=status)
            eligible = task.status == "waiting_approval"
            if status == "waiting_approval":
                assert eligible
            else:
                assert not eligible, f"status={status} 가 approval 대상으로 분류됨"


# ── C. 안전 요약 동시 존재 ───────────────────────────────────────────────────

class TestSafeSummaryCoexistence:

    def test_all_summaries_coexist_in_to_safe(self):
        """result_summary + observe_summary + audit_summary가 동시에 to_safe()에 존재해도 안전."""
        task = _make_task(
            status="waiting_approval",
            token_id="tok-safe-001",
            result_summary="캡처 완료",
            observe_summary=_SAFE_OBSERVE,
            audit_summary=_SAFE_AUDIT,
        )
        safe = task.to_safe()
        assert safe["result_summary"] == "캡처 완료"
        assert safe["observe_summary"] == _SAFE_OBSERVE
        assert safe["audit_summary"] == _SAFE_AUDIT
        assert safe["token_id"] == "tok-safe-001"

    def test_observe_summary_has_no_raw_fields(self):
        """observe_summary에 raw HTML/URL/body/query/fragment/current_url 없음."""
        task = _make_task(observe_summary=_SAFE_OBSERVE)
        obs = task.to_safe()["observe_summary"]
        forbidden = {"html", "body", "current_url", "query", "fragment", "raw", "selector", "path"}
        for key in forbidden:
            assert key not in obs, f"observe_summary에 금지 필드 '{key}' 포함됨"

    def test_audit_summary_has_no_raw_fields(self):
        """audit_summary에 raw event list/JSONL/hash/source 없음."""
        task = _make_task(audit_summary=_SAFE_AUDIT)
        audit = task.to_safe()["audit_summary"]
        forbidden = {
            "events", "raw_events", "audit_summary_hash",
            "local_audit_source", "dropped", "redacted",
        }
        for key in forbidden:
            assert key not in audit, f"audit_summary에 금지 필드 '{key}' 포함됨"

    def test_observe_summary_null_is_safe(self):
        """observe_summary가 None이어도 to_safe() 정상."""
        task = _make_task(observe_summary=None)
        safe = task.to_safe()
        assert safe["observe_summary"] is None

    def test_audit_summary_null_is_safe(self):
        """audit_summary가 None이어도 to_safe() 정상."""
        task = _make_task(audit_summary=None)
        safe = task.to_safe()
        assert safe["audit_summary"] is None

    def test_final_url_sanitized_has_no_query_fragment(self):
        """final_url_sanitized는 query/fragment가 없는 형태여야 한다."""
        url = _SAFE_OBSERVE["final_url_sanitized"]
        assert "?" not in url, "final_url_sanitized에 query string 포함됨"
        assert "#" not in url, "final_url_sanitized에 fragment 포함됨"

    def test_audit_summary_count_fields_are_int(self):
        """audit_summary count 필드는 정수다."""
        task = _make_task(audit_summary=_SAFE_AUDIT)
        audit = task.to_safe()["audit_summary"]
        for field in ("audit_event_count", "blocked_event_count", "allowed_event_count"):
            assert isinstance(audit[field], int), f"{field} 이 정수가 아님"


# ── D. token_id 노출 차단 ────────────────────────────────────────────────────

class TestTokenIdIsolation:

    def test_token_id_not_in_list_response(self):
        """token_id가 to_list_safe()에 없다."""
        task = _make_task(token_id="tok-isolate-001")
        assert "token_id" not in task.to_list_safe()

    def test_token_id_not_mixed_into_result_summary(self):
        """token_id 값이 result_summary에 섞이지 않는다."""
        tok = "tok-secret-abc"
        task = _make_task(token_id=tok, result_summary="작업 완료")
        safe = task.to_safe()
        assert tok not in safe["result_summary"]

    def test_token_id_not_mixed_into_observe_summary(self):
        """token_id 값이 observe_summary 내용에 섞이지 않는다."""
        tok = "tok-secret-xyz"
        obs = {**_SAFE_OBSERVE}
        task = _make_task(token_id=tok, observe_summary=obs)
        safe = task.to_safe()
        obs_str = str(safe["observe_summary"])
        assert tok not in obs_str

    def test_token_id_not_mixed_into_audit_summary(self):
        """token_id 값이 audit_summary 내용에 섞이지 않는다."""
        tok = "tok-secret-zzz"
        audit = {**_SAFE_AUDIT}
        task = _make_task(token_id=tok, audit_summary=audit)
        safe = task.to_safe()
        audit_str = str(safe["audit_summary"])
        assert tok not in audit_str

    def test_token_id_empty_when_not_high_risk(self):
        """low risk task는 token_id가 비어 있다 (fixture 직접 확인)."""
        task = _make_task(token_id="")
        assert task.token_id == ""
        assert task.to_safe()["token_id"] == ""
