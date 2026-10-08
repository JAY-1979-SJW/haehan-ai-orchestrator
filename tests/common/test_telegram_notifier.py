import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / ".."))

# 환경변수 제거하여 mock 모드 강제
os.environ.pop("TELEGRAM_BOT_TOKEN", None)
os.environ.pop("TELEGRAM_CHAT_ID", None)

import importlib

import telegram_notifier

importlib.reload(telegram_notifier)

from models import ExecutionPlan, RiskAssessment, TaskRequest  # noqa: E402
from telegram_notifier import send_approval_request, send_status_message  # noqa: E402


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
    result = send_approval_request(task, risk, plan, token="tok-abc-123")
    assert result["sent"] is True
    assert result["mock"] is True


def test_required_fields_present():
    task, risk, plan = _make_fixtures()
    result = send_approval_request(task, risk, plan, token="tok-abc-123")
    assert result["task_id"] == "tg-test-001"
    assert result["action_type"] == "edit_config"
    assert result["target"] == "/tmp/config.yaml"
    assert result["risk_level"] == "medium"
    assert result["requires_approval"] is True
    assert result["token_id"] == "tok-abc-123"


def test_send_status_message_mock():
    result = send_status_message("테스트 상태 메시지")
    assert result["sent"] is True
    assert result["mock"] is True
    assert "timestamp" in result


def test_no_token_still_returns_result():
    task, risk, plan = _make_fixtures()
    result = send_approval_request(task, risk, plan, token=None)
    assert result["token_id"] is None
    assert result["sent"] is True
