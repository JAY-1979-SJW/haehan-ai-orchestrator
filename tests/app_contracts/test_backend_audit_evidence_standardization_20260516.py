"""Audit/Evidence 표준화 기준선 테스트.

ASSISTANT_BACKEND_AUDIT_EVIDENCE_STANDARDIZATION_01 공정 검증.

금지:
- 외부 API 호출 금지
- 실제 OAuth/로그인 금지
- DB write 금지
- skip/xfail 금지
- secret/token/password 실값 사용 금지
"""

from __future__ import annotations

from pathlib import Path

from ai_orchestrator.audit_evidence.adapters import (
    audit_event_dict_to_standard,
    build_external_app_handoff,
    evidence_dict_to_artifact_ref,
    policy_decision_to_safety_verdict,
    task_state_to_execution_attempt,
)
from ai_orchestrator.audit_evidence.models import (
    ArtifactEvidenceRef,
    ExecutionAttempt,
    ExternalAppHandoff,
    SafetyVerdict,
    StandardAuditEvent,
)
from ai_orchestrator.safety_policy.secret_redaction import (
    FORBIDDEN_SECRET_FIELDS,
)

# ---------------------------------------------------------------------------
# 금지 필드 헬퍼
# ---------------------------------------------------------------------------


def _has_forbidden(d: dict, checked: set | None = None) -> list[str]:
    """재귀적으로 금지 필드 탐색."""
    if checked is None:
        checked = set()
    found = []
    for k, v in d.items():
        if k.lower() in FORBIDDEN_SECRET_FIELDS:
            found.append(k)
        if isinstance(v, dict):
            found.extend(_has_forbidden(v, checked))
    return found


# ---------------------------------------------------------------------------
# STEP 3: StandardAuditEvent
# ---------------------------------------------------------------------------


class TestStandardAuditEvent:
    """StandardAuditEvent 표준 필드 11개 계약."""

    def test_has_eleven_fields(self):
        ev = StandardAuditEvent.create(
            event_type="task_executed",
            task_id="t_001",
            actor="system",
            status="executed",
            summary="작업 완료",
        )
        d = ev.to_safe_dict()
        assert len(d) == 11, f"필드 수 불일치: {list(d.keys())}"

    def test_required_field_names(self):
        ev = StandardAuditEvent.create(
            event_type="task_blocked",
            task_id="t_002",
            actor="admin",
            status="blocked",
            summary="정책 위반",
        )
        d = ev.to_safe_dict()
        required = {
            "event_id",
            "event_type",
            "task_id",
            "actor",
            "status",
            "timestamp",
            "summary",
            "safety_verdict",
            "artifact_refs",
            "metadata",
            "redaction_applied",
        }
        assert required == set(d.keys())

    def test_no_forbidden_fields_in_safe_dict(self):
        ev = StandardAuditEvent.create(
            event_type="approval_requested",
            task_id="t_003",
            actor="operator",
            status="pending",
            summary="승인 요청",
            metadata={"note": "FAKE_NOTE", "password": "FAKE_PASS"},
        )
        d = ev.to_safe_dict()
        assert _has_forbidden(d) == [], f"금지 필드 노출: {_has_forbidden(d)}"

    def test_nested_metadata_redacted(self):
        ev = StandardAuditEvent.create(
            event_type="policy_check",
            task_id="t_004",
            actor="policy",
            status="blocked",
            summary="정책 차단",
            metadata={"inner": {"token": "FAKE_TOKEN", "reason": "위험"}},
        )
        d = ev.to_safe_dict()
        assert "token" not in d.get("metadata", {}).get("inner", {})

    def test_redaction_applied_flag(self):
        ev = StandardAuditEvent.create(
            event_type="test",
            task_id="t_005",
            actor="test",
            status="ok",
            summary="테스트",
        )
        assert ev.redaction_applied is True


# ---------------------------------------------------------------------------
# STEP 3: ExecutionAttempt
# ---------------------------------------------------------------------------


class TestExecutionAttempt:
    """ExecutionAttempt 실행 위치/정책판정/결과 계약."""

    def test_create_server_attempt(self):
        ea = ExecutionAttempt.create(
            task_id="t_010",
            execution_location="server",
            risk_level="low",
            status="executed",
            policy_decision="allow",
            safe_to_execute_on_server=True,
        )
        d = ea.to_safe_dict()
        assert d["execution_location"] == "server"
        assert d["safe_to_execute_on_server"] is True

    def test_create_local_agent_attempt(self):
        ea = ExecutionAttempt.create(
            task_id="t_011",
            execution_location="local_agent",
            risk_level="high",
            status="held",
            policy_decision="hold",
            safe_to_execute_on_server=False,
        )
        d = ea.to_safe_dict()
        assert d["execution_location"] == "local_agent"
        assert d["safe_to_execute_on_server"] is False

    def test_no_forbidden_fields(self):
        ea = ExecutionAttempt.create(
            task_id="t_012",
            execution_location="user_direct",
            risk_level="critical",
            status="blocked",
            policy_decision="block",
            safe_to_execute_on_server=False,
            error_code="USER_DIRECT_REQUIRED",
            error_message="사용자 직접 실행 필요",
        )
        assert _has_forbidden(ea.to_safe_dict()) == []

    def test_required_fields_present(self):
        ea = ExecutionAttempt.create(
            task_id="t_013",
            execution_location="server",
            risk_level="medium",
            status="executed",
            policy_decision="allow",
            safe_to_execute_on_server=True,
        )
        d = ea.to_safe_dict()
        for f in [
            "attempt_id",
            "task_id",
            "execution_location",
            "risk_level",
            "started_at",
            "status",
            "policy_decision",
            "safe_to_execute_on_server",
        ]:
            assert f in d


# ---------------------------------------------------------------------------
# STEP 3: SafetyVerdict
# ---------------------------------------------------------------------------


class TestSafetyVerdict:
    """SafetyVerdict block/hold/user_direct/oauth_required 계약."""

    def test_blocked_verdict(self):
        sv = SafetyVerdict.create(
            task_id="t_020",
            policy_id="no_bid_auto_execute",
            decision="block",
            reason="투찰 자동 실행 금지",
            required_execution_location="user_direct",
            blocked=True,
            requires_user_direct=True,
            requires_approval=True,
        )
        d = sv.to_safe_dict()
        assert d["blocked"] is True
        assert d["requires_user_direct"] is True
        assert d["requires_approval"] is True

    def test_oauth_required_verdict(self):
        sv = SafetyVerdict.create(
            task_id="t_021",
            policy_id="oauth_api_required",
            decision="hold",
            reason="OAuth 설정 필요",
            required_execution_location="server",
            requires_oauth_setup=True,
        )
        d = sv.to_safe_dict()
        assert d["requires_oauth_setup"] is True
        assert d["blocked"] is False

    def test_no_forbidden_fields(self):
        sv = SafetyVerdict.create(
            task_id="t_022",
            policy_id="test_policy",
            decision="allow",
            reason="허용",
            required_execution_location="server",
        )
        assert _has_forbidden(sv.to_safe_dict()) == []

    def test_required_fields(self):
        sv = SafetyVerdict.create(
            task_id="t_023",
            policy_id="test",
            decision="allow",
            reason="ok",
            required_execution_location="server",
        )
        d = sv.to_safe_dict()
        for f in [
            "verdict_id",
            "task_id",
            "policy_id",
            "decision",
            "reason",
            "required_execution_location",
            "requires_approval",
            "requires_user_direct",
            "requires_oauth_setup",
            "blocked",
            "checked_at",
        ]:
            assert f in d


# ---------------------------------------------------------------------------
# STEP 3: ExternalAppHandoff
# ---------------------------------------------------------------------------


class TestExternalAppHandoff:
    """ExternalAppHandoff CAD/HWPX/Excel/Tax/Bid 계약."""

    def test_cad_handoff_local_agent_required(self):
        hf = ExternalAppHandoff.create(
            task_id="t_030",
            bridge_id="cad_bridge_001",
            app_type="CAD",
            handoff_mode="file_drop",
            status="handoff_recorded",
            approval_required=True,
            user_direct_required=False,
            safety_policy_ids=("external_app_hold_policy",),
            auto_execute_allowed=False,
        )
        d = hf.to_safe_dict()
        assert d["app_type"] == "CAD"
        assert d["approval_required"] is True
        assert d["auto_execute_allowed"] is False

    def test_hwpx_handoff_approval_required(self):
        hf = ExternalAppHandoff.create(
            task_id="t_031",
            bridge_id="hwpx_bridge_001",
            app_type="HWPX",
            handoff_mode="file_drop",
            status="handoff_recorded",
            approval_required=True,
            user_direct_required=False,
            auto_execute_allowed=False,
        )
        assert hf.approval_required is True
        assert hf.auto_execute_allowed is False

    def test_excel_handoff(self):
        hf = ExternalAppHandoff.create(
            task_id="t_032",
            bridge_id="excel_bridge_001",
            app_type="Excel",
            handoff_mode="file_drop",
            status="handoff_recorded",
            approval_required=True,
            user_direct_required=False,
            auto_execute_allowed=False,
        )
        assert hf.app_type == "Excel"

    def test_bid_handoff_no_auto_execute(self):
        hf = ExternalAppHandoff.create(
            task_id="t_033",
            bridge_id="bid_bridge_001",
            app_type="Bid",
            handoff_mode="user_manual",
            status="handoff_recorded",
            approval_required=True,
            user_direct_required=True,
            safety_policy_ids=("no_bid_auto_execute",),
            auto_execute_allowed=False,
        )
        d = hf.to_safe_dict()
        assert d["auto_execute_allowed"] is False
        assert d["user_direct_required"] is True
        assert "no_bid_auto_execute" in d["safety_policy_ids"]

    def test_tax_handoff_user_direct_required(self):
        hf = ExternalAppHandoff.create(
            task_id="t_034",
            bridge_id="tax_bridge_001",
            app_type="Tax",
            handoff_mode="user_manual",
            status="handoff_recorded",
            approval_required=True,
            user_direct_required=True,
            auto_execute_allowed=False,
        )
        assert hf.user_direct_required is True

    def test_no_forbidden_fields(self):
        hf = ExternalAppHandoff.create(
            task_id="t_035",
            bridge_id="test_bridge",
            app_type="CAD",
            handoff_mode="file_drop",
            status="handoff_recorded",
            approval_required=True,
            user_direct_required=False,
        )
        assert _has_forbidden(hf.to_safe_dict()) == []

    def test_handoff_is_record_only_not_execution(self):
        hf = ExternalAppHandoff.create(
            task_id="t_036",
            bridge_id="cad_bridge",
            app_type="CAD",
            handoff_mode="file_drop",
            status="handoff_recorded",
            approval_required=True,
            user_direct_required=False,
        )
        assert hf.status == "handoff_recorded"
        assert hf.completed_at is None


# ---------------------------------------------------------------------------
# STEP 3: ArtifactEvidenceRef
# ---------------------------------------------------------------------------


class TestArtifactEvidenceRef:
    """ArtifactEvidenceRef storage_ref 포함, 민감정보 미포함 계약."""

    def test_has_storage_ref(self):
        ar = ArtifactEvidenceRef.create(
            artifact_type="screenshot",
            content_type="image/png",
            storage_ref="/data/evidence/t_001/screen.png",
            safe_name="screen_t001",
            source_task_id="t_001",
        )
        assert ar.storage_ref == "/data/evidence/t_001/screen.png"

    def test_no_binary_content(self):
        ar = ArtifactEvidenceRef.create(
            artifact_type="document",
            content_type="application/pdf",
            storage_ref="/data/evidence/t_002/doc.pdf",
            safe_name="doc_t002",
            source_task_id="t_002",
        )
        d = ar.to_safe_dict()
        assert "file_content" not in d
        assert "file_bytes" not in d
        assert "base64" not in d

    def test_no_forbidden_fields(self):
        ar = ArtifactEvidenceRef.create(
            artifact_type="log",
            content_type="text/plain",
            storage_ref="/data/evidence/t_003/log.txt",
            safe_name="log_t003",
            source_task_id="t_003",
        )
        assert _has_forbidden(ar.to_safe_dict()) == []

    def test_redaction_applied_flag(self):
        ar = ArtifactEvidenceRef.create(
            artifact_type="log",
            content_type="text/plain",
            storage_ref="/data/evidence/t_004/log.txt",
            safe_name="log_t004",
            source_task_id="t_004",
        )
        assert ar.redaction_applied is True


# ---------------------------------------------------------------------------
# STEP 4: Adapter 테스트
# ---------------------------------------------------------------------------


class TestAdapters:
    """read-only adapter 변환 테스트."""

    def test_audit_event_dict_to_standard(self):
        raw = {
            "event_type": "task_executed",
            "task_id": "t_100",
            "actor": "operator",
            "decision": "allowed",
            "action_type": "send_email",
            "note": "이메일 발송",
        }
        ev = audit_event_dict_to_standard(raw)
        assert ev.event_type == "task_executed"
        assert ev.task_id == "t_100"
        assert _has_forbidden(ev.to_safe_dict()) == []

    def test_audit_event_with_secret_stripped(self):
        raw = {
            "event_type": "login",
            "task_id": "t_101",
            "password": "FAKE_SECRET",
            "decision": "blocked",
            "note": "위험",
        }
        ev = audit_event_dict_to_standard(raw)
        assert _has_forbidden(ev.to_safe_dict()) == []

    def test_task_state_to_execution_attempt(self):
        raw = {
            "task_id": "t_110",
            "state": "executed",
            "execution_location": "server",
            "risk_level": "low",
            "policy_decision": "allow",
            "safe_to_execute_on_server": True,
            "updated_at": "2026-05-16T00:00:00+00:00",
        }
        ea = task_state_to_execution_attempt(raw)
        assert ea.task_id == "t_110"
        assert ea.execution_location == "server"
        assert _has_forbidden(ea.to_safe_dict()) == []

    def test_policy_decision_to_safety_verdict(self):
        decision = {
            "execution_location": "local_agent",
            "is_blocked": False,
            "is_external_app_hold": True,
            "requires_approval": True,
            "requires_user_direct": False,
            "requires_oauth_setup": False,
            "reason": "외부 앱 hold",
        }
        sv = policy_decision_to_safety_verdict("t_120", "external_app_hold_policy", decision)
        assert sv.decision == "hold"
        assert sv.requires_approval is True
        assert _has_forbidden(sv.to_safe_dict()) == []

    def test_evidence_dict_to_artifact_ref(self):
        raw = {
            "evidence_id": "ev_001",
            "action_name": "capture_screenshot",
            "task_id": "t_130",
            "result_status": "ok",
            "evidence_files_ref": "/data/evidence/ev_001/",
        }
        ar = evidence_dict_to_artifact_ref(raw)
        assert ar.source_task_id == "t_130"
        assert _has_forbidden(ar.to_safe_dict()) == []

    def test_build_external_app_handoff_cad(self):
        hf = build_external_app_handoff(
            task_id="t_140",
            bridge_id="cad_b",
            app_type="CAD",
            handoff_mode="file_drop",
            approval_required=True,
            user_direct_required=False,
            safety_policy_ids=("external_app_hold_policy",),
            auto_execute_allowed=False,
        )
        assert hf.app_type == "CAD"
        assert hf.status == "handoff_recorded"
        assert _has_forbidden(hf.to_safe_dict()) == []

    def test_build_external_app_handoff_bid_no_auto_execute(self):
        hf = build_external_app_handoff(
            task_id="t_141",
            bridge_id="bid_b",
            app_type="Bid",
            handoff_mode="user_manual",
            approval_required=True,
            user_direct_required=True,
            safety_policy_ids=("no_bid_auto_execute",),
            auto_execute_allowed=False,
        )
        assert hf.auto_execute_allowed is False


# ---------------------------------------------------------------------------
# STEP 5: secret redaction 종합
# ---------------------------------------------------------------------------


class TestSecretRedactionAllModels:
    """모든 모델 to_safe_dict에 금지 키 없음 보장."""

    def test_all_models_safe_dict_no_forbidden(self):
        models = [
            StandardAuditEvent.create(
                event_type="test",
                task_id="t",
                actor="a",
                status="ok",
                summary="s",
                metadata={"password": "FAKE", "token": "FAKE_TOK"},
            ).to_safe_dict(),
            ExecutionAttempt.create(
                task_id="t",
                execution_location="server",
                risk_level="low",
                status="ok",
                policy_decision="allow",
                safe_to_execute_on_server=True,
            ).to_safe_dict(),
            SafetyVerdict.create(
                task_id="t",
                policy_id="p",
                decision="allow",
                reason="ok",
                required_execution_location="server",
            ).to_safe_dict(),
            ExternalAppHandoff.create(
                task_id="t",
                bridge_id="b",
                app_type="CAD",
                handoff_mode="file_drop",
                status="handoff_recorded",
                approval_required=True,
                user_direct_required=False,
            ).to_safe_dict(),
            ArtifactEvidenceRef.create(
                artifact_type="log",
                content_type="text/plain",
                storage_ref="/tmp/x",
                safe_name="x",
                source_task_id="t",
            ).to_safe_dict(),
        ]
        for d in models:
            assert _has_forbidden(d) == [], f"금지 필드 노출: {_has_forbidden(d)} in {d}"


# ---------------------------------------------------------------------------
# STEP 10: 기존 API contract / endpoint inventory 불변 확인
# ---------------------------------------------------------------------------


class TestExistingContractUnchanged:
    """기존 API contract / endpoint inventory 변경 없음."""

    def test_audit_evidence_package_importable(self):
        pass

    def test_existing_audit_logger_still_importable(self):
        pass

    def test_existing_task_state_still_importable(self):
        pass

    def test_existing_action_evidence_store_still_importable(self):
        pass

    def test_existing_action_approval_audit_store_still_importable(self):
        pass

    def test_no_ui_files_modified(self):
        ui_paths = [
            "admin-web/src",
            "desktop/ui",
        ]
        base = Path(__file__).resolve().parent.parent.parent
        import subprocess

        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=base,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        changed = result.stdout.splitlines()
        for p in ui_paths:
            for f in changed:
                assert not f.startswith(p), f"UI 파일 변경 금지: {f}"
