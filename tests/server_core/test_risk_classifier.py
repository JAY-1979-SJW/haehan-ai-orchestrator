import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ai_orchestrator.core.models import TaskRequest
from tools.gates.risk_classifier import classify_risk


def make_req(action, target="/tmp/test.txt", payload=None):  # noqa: S108 — 테스트 헬퍼 기본값, 실제 파일 생성 없음
    return TaskRequest(
        task_id="TEST",
        source="manual",
        action_type=action,
        target=target,
        description="테스트",
        payload=payload or {},
        requested_by="test",
    )


def test_read_file_is_low():
    risk = classify_risk(make_req("read_file"))
    assert risk.risk_level == "low", f"expected low, got {risk.risk_level}"
    assert not risk.requires_approval
    print("PASS: read_file → low, 승인 불필요")


def test_restart_service_is_high():
    risk = classify_risk(make_req("restart_service", target="haehan-api"))
    assert risk.risk_level == "high", f"expected high, got {risk.risk_level}"
    assert risk.requires_approval
    print("PASS: restart_service → high, 승인 필요")


def test_delete_file_is_critical():
    risk = classify_risk(make_req("delete_file", target="/var/www/haehan/file.txt"))
    assert risk.risk_level == "critical", f"expected critical, got {risk.risk_level}"
    assert risk.requires_approval
    print("PASS: delete_file → critical, 승인 필요")


def test_sensitive_path_escalates():
    risk = classify_risk(make_req("read_file", target="/etc/passwd"))
    assert risk.risk_level in ("high", "critical"), f"expected high+, got {risk.risk_level}"
    print(f"PASS: /etc/ 경로 → {risk.risk_level}, 상향됨")


def test_destructive_payload_escalates():
    risk = classify_risk(make_req("run_shell", payload={"cmd": "rm -rf /var/www"}))
    assert risk.risk_level == "critical", f"expected critical, got {risk.risk_level}"
    print("PASS: rm -rf payload → critical")


if __name__ == "__main__":
    test_read_file_is_low()
    test_restart_service_is_high()
    test_delete_file_is_critical()
    test_sensitive_path_escalates()
    test_destructive_payload_escalates()
    print("\n모든 risk_classifier 테스트 통과")
