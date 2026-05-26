import json

from scripts.ops import ai_work_record
from scripts.ops import work_approval_watch


def test_start_record_is_resumable(tmp_path):
    latest = tmp_path / "latest.json"
    history = tmp_path / "history.jsonl"

    code = ai_work_record.main([
        "start",
        "--latest",
        str(latest),
        "--history",
        str(history),
        "--task-id",
        "TASK-1",
        "--summary",
        "prepare youtube oauth operational handoff",
        "--lane",
        "ops",
        "--scope",
        "scripts/ops/",
        "--forbidden-scope",
        "scripts/naver_mail/",
        "--next-step",
        "run work approval gate",
    ])

    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["task_id"] == "TASK-1"
    assert payload["lane"] == "ops"
    assert payload["forbidden_scopes"] == ["scripts/naver_mail/"]
    assert payload["secret_values_output"] is False
    assert json.loads(history.read_text(encoding="utf-8").strip())["status"] == "in_progress"


def test_append_and_complete_preserve_resume_next_step(tmp_path):
    latest = tmp_path / "latest.json"
    history = tmp_path / "history.jsonl"
    ai_work_record.main([
        "start",
        "--latest",
        str(latest),
        "--history",
        str(history),
        "--task-id",
        "TASK-2",
        "--summary",
        "build work record gate",
        "--scope",
        "scripts/ops/",
    ])

    code = ai_work_record.main([
        "complete",
        "--latest",
        str(latest),
        "--history",
        str(history),
        "--verification",
        "pytest passed",
        "--next-step",
        "commit after user approval",
    ])

    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["status"] == "completed"
    assert payload["resume_next_step"] == "commit after user approval"
    assert payload["verification"] == ["pytest passed"]


def test_secret_shaped_text_is_rejected(tmp_path):
    latest = tmp_path / "latest.json"
    history = tmp_path / "history.jsonl"

    code = ai_work_record.main([
        "start",
        "--latest",
        str(latest),
        "--history",
        str(history),
        "--task-id",
        "TASK-3",
        "--summary",
        "access_token=raw",
        "--scope",
        "scripts/ops/",
    ])

    assert code == 1


def test_work_approval_watch_can_require_work_record(tmp_path):
    latest = tmp_path / "latest.json"
    history = tmp_path / "history.jsonl"
    ai_work_record.main([
        "start",
        "--latest",
        str(latest),
        "--history",
        str(history),
        "--task-id",
        "TASK-4",
        "--summary",
        "resume safe operational work",
        "--scope",
        "scripts/ops/",
    ])

    payload = work_approval_watch.work_record_status(latest)

    assert payload["ok"] is True
    assert payload["task_id"] == "TASK-4"
