from __future__ import annotations

import verify_release_runtime_gate as gate


def test_command_matrix_blocks_build_deploy_push_commands():
    commands = [check.command for check in gate.make_checks(gate.DEFAULT_SERVER_URL)]

    assert commands
    assert all(not gate.command_is_forbidden(command) for command in commands)
    assert gate.command_is_forbidden(("python", "build.py", "docker"))
    assert gate.command_is_forbidden(("npm", "run", "build"))


def test_local_runtime_allows_only_packaging_warns():
    output = "\n".join([
        "[PASS] server http health - status=200",
        "[WARN] desktop exe - not found; portable start requires exe",
        "RESULT=WARN_LOCAL_RUNTIME_DRY_RUN",
    ])

    status, detail = gate.classify_local_runtime_live(output, 0)

    assert status == "WARN"
    assert detail == "WARN_LOCAL_RUNTIME_DRY_RUN"


def test_local_runtime_blocks_server_warns():
    output = "\n".join([
        "[WARN] server http health - ConnectionRefusedError",
        "RESULT=WARN_LOCAL_RUNTIME_DRY_RUN",
    ])

    status, detail = gate.classify_local_runtime_live(output, 0)

    assert status == "FAIL"
    assert "server http health" in detail


def test_live_agent_smoke_allows_task_dispatch_skip_only():
    output = "\n".join([
        "[PASS] server health - status=200",
        "[PASS] websocket heartbeat - heartbeat_ack",
        "[WARN] task dispatch - skipped; admin/owner credentials not present",
        "RESULT=WARN_LIVE_AGENT_SMOKE",
    ])

    status, detail = gate.classify_live_agent_smoke(output, 0)

    assert status == "WARN"
    assert "dedicated check" in detail


def test_live_agent_smoke_blocks_health_failures():
    output = "\n".join([
        "[FAIL] server health - ConnectionRefusedError",
        "RESULT=FAIL_LIVE_AGENT_SMOKE",
    ])

    status, detail = gate.classify_live_agent_smoke(output, 1)

    assert status == "FAIL"
    assert detail == "FAIL_LIVE_AGENT_SMOKE"


def test_pytest_classifier_requires_passed_tests():
    assert gate.classify_pytest_requires_pass("19 passed in 1.2s", 0) == ("PASS", "passed=19")
    assert gate.classify_pytest_requires_pass("19 skipped in 1.2s", 0) == ("FAIL", "no passed tests observed")
    assert gate.classify_pytest_requires_pass("1 failed, 18 passed", 1)[0] == "FAIL"


def test_transient_marker_detection():
    assert gate.has_transient_marker("ws_auth_status=ConnectionRefusedError")
    assert gate.has_transient_marker("task create - URLError")
    assert gate.has_transient_marker("PLAYWRIGHT_LAUNCH_ERROR:PermissionError")
    assert not gate.has_transient_marker("RESULT=PASS_AGENT_WS_AUTH")
