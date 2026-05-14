from scripts.eum import router
from scripts.eum import run_log
from scripts.eum import work_plan


def test_cmd_work_executes_read_only_history(monkeypatch, tmp_path):
    calls = []

    def fake_history(sub, args):
        calls.append((sub, args))

    monkeypatch.setattr(run_log, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(router, "_cmd_history", fake_history)

    router._cmd_work("history", ["DEVICE-001"])

    assert calls == [("DEVICE-001", [])]
    assert list((tmp_path / "device_history").glob("*.json"))


def test_cmd_work_does_not_execute_approval_workflow(monkeypatch):
    calls = []

    def fake_registration(sub, args, *, submit=False):
        calls.append((sub, args, submit))

    monkeypatch.setattr(router, "_cmd_registration", fake_registration)

    router._cmd_work("WEBMAN381M00", ["PROJECT-001", "DEVICE-001"])

    assert calls == []


def test_cmd_work_dry_run_does_not_execute(monkeypatch, tmp_path):
    calls = []

    def fake_extract(sub, args):
        calls.append((sub, args))

    monkeypatch.setattr(run_log, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(router, "_cmd_extract", fake_extract)

    router._cmd_work("extract", ["--dry-run"])

    assert calls == []
    assert not tmp_path.exists() or not list(tmp_path.rglob("*.json"))


def test_cmd_work_approval_dry_run_writes_plan(monkeypatch, tmp_path):
    monkeypatch.setattr(work_plan, "PLANS_DIR", tmp_path)

    router._cmd_work("registration", ["P-001", "D-001", "Seoul", "--dry-run"])

    files = list((tmp_path / "device_registration").glob("*.json"))
    assert len(files) == 1


def test_cmd_work_approval_submit_executes_after_valid_plan(monkeypatch, tmp_path):
    calls = []

    def fake_registration(sub, args, *, submit=False):
        calls.append((sub, args, submit))

    monkeypatch.setattr(work_plan, "PLANS_DIR", tmp_path / "plans")
    monkeypatch.setattr(run_log, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(router, "_cmd_registration", fake_registration)

    router._cmd_work("registration", ["P-001", "D-001", "Seoul", "--submit"])

    assert calls == [("P-001", ["D-001", "Seoul"], True)]
    assert list((tmp_path / "plans" / "device_registration").glob("*.json"))
    assert list((tmp_path / "runs" / "device_registration").glob("*.json"))


def test_cmd_work_approval_submit_blocks_invalid_plan(monkeypatch, tmp_path):
    calls = []

    def fake_registration(sub, args, *, submit=False):
        calls.append((sub, args, submit))

    monkeypatch.setattr(work_plan, "PLANS_DIR", tmp_path / "plans")
    monkeypatch.setattr(run_log, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(router, "_cmd_registration", fake_registration)

    try:
        router._cmd_work("registration", ["P-001", "--submit"])
    except SystemExit as exc:
        assert exc.code == 2

    assert calls == []
    assert not (tmp_path / "runs").exists()


def test_cmd_work_approval_prepare_executes_without_submit(monkeypatch, tmp_path):
    calls = []

    def fake_registration(sub, args, *, submit=False):
        calls.append((sub, args, submit))

    monkeypatch.setattr(work_plan, "PLANS_DIR", tmp_path / "plans")
    monkeypatch.setattr(run_log, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(router, "_cmd_registration", fake_registration)

    router._cmd_work("registration", ["P-001", "D-001", "Seoul", "--prepare"])

    assert calls == [("P-001", ["D-001", "Seoul"], False)]
    assert list((tmp_path / "plans" / "device_registration").glob("*.json"))
    assert list((tmp_path / "runs" / "device_registration").glob("*.json"))


def test_cmd_work_approval_prepare_blocks_invalid_plan(monkeypatch, tmp_path):
    calls = []

    def fake_registration(sub, args, *, submit=False):
        calls.append((sub, args, submit))

    monkeypatch.setattr(work_plan, "PLANS_DIR", tmp_path / "plans")
    monkeypatch.setattr(run_log, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(router, "_cmd_registration", fake_registration)

    try:
        router._cmd_work("registration", ["P-001", "--prepare"])
    except SystemExit as exc:
        assert exc.code == 2

    assert calls == []
    assert not (tmp_path / "runs").exists()
