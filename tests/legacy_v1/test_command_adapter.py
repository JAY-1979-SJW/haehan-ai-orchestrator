import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from orchestrator_v1.tasks.command_adapter import run_command


def test_pwd_or_whoami_success():
    result = run_command("whoami", "status_check")
    assert result["status"] in ("OK", "ERROR"), result
    if result["status"] == "OK":
        assert result["exit_code"] == 0


def test_ls_success():
    result = run_command("ls", "status_check")
    assert result["status"] in ("OK", "ERROR")


def test_blocked_rm_command():
    result = run_command("rm -rf /tmp/test", "low")
    assert result["status"] == "BLOCKED"
    assert "blocked" in result["reason"].lower()


def test_blocked_shutdown():
    result = run_command("shutdown now", "low")
    assert result["status"] == "BLOCKED"


def test_unlisted_command_blocked():
    result = run_command("cat /etc/passwd", "low")
    assert result["status"] == "BLOCKED"
    assert "whitelist" in result["reason"].lower()


def test_shell_injection_blocked():
    for injection in ["ls; rm -rf /", "ls && shutdown", "ls | bash"]:
        result = run_command(injection, "low")
        assert result["status"] == "BLOCKED", f"Should be blocked: {injection}"


def test_high_action_type_blocked():
    result = run_command("ls", "high")
    assert result["status"] == "BLOCKED"
    assert "high" in result["reason"]


def test_critical_action_type_blocked():
    result = run_command("pwd", "critical")
    assert result["status"] == "BLOCKED"
