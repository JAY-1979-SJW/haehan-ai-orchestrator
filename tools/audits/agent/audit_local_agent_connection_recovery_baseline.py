"""Read-only audit for the local-agent connection recovery baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE = ROOT / "docs" / "baseline" / "modules" / "LOCAL_AGENT_CONNECTION_RECOVERY_BASELINE.md"
LOCAL_AGENT_E2E = ROOT / "docs" / "baseline" / "modules" / "LOCAL_AGENT_E2E_BASELINE.md"
COMMON_ENGINE = ROOT / "docs" / "baseline" / "modules" / "COMMON_ENGINE_COMMERCIALIZATION_BASELINE.md"
MODULE_BASELINE = ROOT / "docs" / "baseline" / "MODULE_BASELINE.md"
CONNECTION_DIAGNOSTICS = ROOT / "core" / "agent_runtime" / "connection" / "connection_diagnostics.py"
WEBSOCKET_CLIENT = ROOT / "core" / "agent_runtime" / "connection" / "websocket_client.py"
WS_AUTH_PROBE = ROOT / "tools" / "verify" / "verify_agent_ws_auth.py"
LIVE_DISPATCH = ROOT / "tools" / "verify" / "verify_live_task_dispatch.py"

REQUIRED_BASELINE_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-LOCAL-AGENT-CONNECTION-RECOVERY-BASELINE-01",
    "AUTH_FAILED_4401",
    "RE_REGISTER_REQUIRED",
    "AUTO_RECONNECT",
    "CHECK_NETWORK_OR_SERVER",
    "CHECK_PROXY_OR_FIREWALL",
    "initial backoff: 1 second",
    "maximum backoff: 60 seconds",
    "jitter: up to 10 percent",
    "python tools/quality/module_quality_gate.py --module local_agent_connection_recovery",
)

REQUIRED_DIAGNOSTIC_PHRASES = (
    "def build_recovery_plan",
    "AUTH_FAILED_4401",
    "RE_REGISTER_REQUIRED",
    "TOKEN_NOT_STORED",
    "AUTO_RECONNECT",
    "CHECK_NETWORK_OR_SERVER",
    "CHECK_PROXY_OR_FIREWALL",
    "should_delete_token=False",
    "render_recovery_block",
)

REQUIRED_WEBSOCKET_PHRASES = (
    "backoff = 1.0",
    "max_backoff = 60.0",
    "random.uniform(0.0, backoff * 0.1)",
    "backoff = min(max_backoff, backoff * 2)",
)

REQUIRED_PROBE_PHRASES = (
    "_websocket_close_code",
    "AUTH_FAILED_4401",
    "DEVICE_TOKEN_MISSING",
    "AGENT_ID_MISSING",
)

REQUIRED_DISPATCH_PHRASES = (
    "--temp-admin",
    "basic_auth",
    "task create",
    "RESULT=PASS_LIVE_TASK_DISPATCH",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _missing(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    paths = (
        BASELINE,
        LOCAL_AGENT_E2E,
        COMMON_ENGINE,
        MODULE_BASELINE,
        CONNECTION_DIAGNOSTICS,
        WEBSOCKET_CLIENT,
        WS_AUTH_PROBE,
        LIVE_DISPATCH,
    )
    for path in paths:
        if not path.exists():
            failures.append(f"{path.relative_to(ROOT)} missing")
    if failures:
        return False, failures

    checks = (
        ("connection baseline", _read(BASELINE), REQUIRED_BASELINE_PHRASES),
        ("connection diagnostics", _read(CONNECTION_DIAGNOSTICS), REQUIRED_DIAGNOSTIC_PHRASES),
        ("websocket client", _read(WEBSOCKET_CLIENT), REQUIRED_WEBSOCKET_PHRASES),
        ("ws auth probe", _read(WS_AUTH_PROBE), REQUIRED_PROBE_PHRASES),
        ("live dispatch verifier", _read(LIVE_DISPATCH), REQUIRED_DISPATCH_PHRASES),
    )
    for label, text, phrases in checks:
        missing = _missing(text, phrases)
        if missing:
            failures.append(f"{label} missing phrase(s): " + ", ".join(missing))

    if "LOCAL_AGENT_CONNECTION_RECOVERY_BASELINE.md" not in _read(LOCAL_AGENT_E2E):
        failures.append("local_agent_e2e baseline missing connection recovery baseline reference")
    if "local_agent_connection_recovery" not in _read(COMMON_ENGINE):
        failures.append("common engine baseline missing local_agent_connection_recovery reference")
    if "### local_agent_connection_recovery" not in _read(MODULE_BASELINE):
        failures.append("module baseline missing local_agent_connection_recovery section")

    return not failures, failures or [
        "LOCAL_AGENT_CONNECTION_RECOVERY_BASELINE exists and is locked",
        "connection diagnostics define safe recovery plans",
        "WebSocket client defines bounded reconnect backoff",
        "auth and dispatch probes preserve connection failure signals",
    ]


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "LOCAL_AGENT_CONNECTION_RECOVERY_BASELINE")


if __name__ == "__main__":
    raise SystemExit(main())
