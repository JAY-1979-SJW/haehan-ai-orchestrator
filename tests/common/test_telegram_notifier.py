import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".."))

import orchestrator_v1.monitoring.telegram_notifier as telegram_notifier  # noqa: E402
from orchestrator_v1.core.models import ExecutionPlan, RiskAssessment, TaskRequest  # noqa: E402


@pytest.fixture(autouse=True)
def _mock_mode_env(monkeypatch):
    """TELEGRAM_BOT_TOKEN/CHAT_ID 를 지우고 모듈을 재로드해 mock 모드를 강제.

    예전엔 이 파일의 최상단에서 `os.environ.pop(...)` 로 직접 지웠는데, monkeypatch 가
    아니라 수집시 한 번만 실행되고 복원도 없어서 이 파일이 수집되는 순간 그 env 가
    세션 끝까지(다른 시험에까지) 사라진 채로 남았다 — 재발방지 전수조사(run38015451820)
    중 발견. monkeypatch.delenv 로 시험마다(autouse) 지우고 시험이 끝나면 자동 복원한다.
    """
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    importlib.reload(telegram_notifier)
    yield


def _make_fixtures():
    task = TaskRequest(
        task_id="tg-test-001",
        source="pc",
        action_type="edit_config",
        target="/tmp/config.yaml",
        description="텔레그램 테스트",
    )
    risk = RiskAssessment(risk_level="medium", requires_approval=True)
    plan = ExecutionPlan(task_id=task.task_id, allowed=True, requires_approval=True)
    return task, risk, plan


def test_mock_mode_returns_ok_when_no_env():
    task, risk, plan = _make_fixtures()
    result = telegram_notifier.send_approval_request(task, risk, plan, token="tok-abc-123")
    assert result["sent"] is True
    assert result["mock"] is True


def test_required_fields_present():
    task, risk, plan = _make_fixtures()
    result = telegram_notifier.send_approval_request(task, risk, plan, token="tok-abc-123")
    assert result["task_id"] == "tg-test-001"
    assert result["action_type"] == "edit_config"
    assert result["target"] == "/tmp/config.yaml"
    assert result["risk_level"] == "medium"
    assert result["requires_approval"] is True
    assert result["token_id"] == "tok-abc-123"


def test_send_status_message_mock():
    result = telegram_notifier.send_status_message("테스트 상태 메시지")
    assert result["sent"] is True
    assert result["mock"] is True
    assert "timestamp" in result


def test_no_token_still_returns_result():
    task, risk, plan = _make_fixtures()
    result = telegram_notifier.send_approval_request(task, risk, plan, token=None)
    assert result["token_id"] is None
    assert result["sent"] is True
