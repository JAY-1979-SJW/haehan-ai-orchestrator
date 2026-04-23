"""
명령 어댑터 — 화이트리스트 패턴 매칭 후 안전한 argv로만 실행
shell=True 금지, high/critical 호출 금지
"""
import subprocess
import shlex
from typing import Optional

DEFAULT_TIMEOUT = 30  # seconds

# (pattern_string, argv_builder) — pattern 매칭 시 안전 argv 반환
_WHITELIST: list[tuple[str, list[str]]] = [
    ("pwd",            ["pwd"]),
    ("ls -la",         ["ls", "-la"]),
    ("ls",             ["ls"]),
    ("whoami",         ["whoami"]),
    ("hostname",       ["hostname"]),
    ("date",           ["date"]),
    ("docker compose logs --tail 50", ["docker", "compose", "logs", "--tail", "50"]),
    ("docker compose ps",             ["docker", "compose", "ps"]),
]

_BLOCKED_PATTERNS = [
    "rm", "mv", "chmod", "chown",
    "systemctl restart", "reboot", "shutdown",
    "docker compose up", "docker compose build", "docker compose restart",
    "git push",
    "curl |", "bash -c", "sh -c",
    "sudo",
    "|", ";", "&&", "||", "`", "$(",
]

_BLOCKED_ACTION_TYPES = {"high", "critical"}


def _match_whitelist(command: str) -> Optional[list[str]]:
    cmd_stripped = command.strip().lower()
    for pattern, argv in _WHITELIST:
        if cmd_stripped == pattern.lower():
            return argv
    return None


def _has_blocked_pattern(command: str) -> Optional[str]:
    cl = command.lower()
    for bp in _BLOCKED_PATTERNS:
        if bp.lower() in cl:
            return bp
    return None


def run_command(
    command: str,
    action_type: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    if action_type in _BLOCKED_ACTION_TYPES:
        return {
            "status": "BLOCKED",
            "reason": f"action_type '{action_type}' is not allowed in command adapter",
        }

    blocked = _has_blocked_pattern(command)
    if blocked:
        return {
            "status": "BLOCKED",
            "reason": f"blocked pattern detected: '{blocked}'",
        }

    argv = _match_whitelist(command)
    if argv is None:
        return {
            "status": "BLOCKED",
            "reason": f"command not in whitelist: '{command}'",
        }

    try:
        result = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "status": "OK",
            "command": command,
            "argv": argv,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"status": "ERROR", "reason": f"command timed out after {timeout}s"}
    except FileNotFoundError as e:
        return {"status": "ERROR", "reason": f"executable not found: {e}"}
    except OSError as e:
        return {"status": "ERROR", "reason": str(e)}
