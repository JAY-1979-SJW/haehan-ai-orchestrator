"""Read-only audit for the locked desktop_auth_runtime baseline."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DESKTOP_BASELINE = ROOT / "docs" / "baseline" / "modules" / "DESKTOP_AUTH_RUNTIME_BASELINE.md"
MODULE_BASELINE = ROOT / "docs" / "baseline" / "MODULE_BASELINE.md"

REQUIRED_DESKTOP_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-DESKTOP-AUTH-RUNTIME-BASELINE-01",
    "desktop server API call auth boundary",
    "configured session/auth context usage",
    "safe failure when token or session is unavailable",
    "task receiver auth header handling",
    "token masking and redaction",
    "desktop runtime state isolation",
    "configured auth/session context",
    "server base URL",
    "task receiver request",
    "hardcoded bearer token",
    "global `SESSION_ID` shortcut",
    "production mock auth",
    "authenticated outbound request",
    "safe failure when token/session unavailable",
    "redacted log message",
    "If token/session is missing, protected requests must not be sent.",
    "Authorization header values must never be printed.",
    "`Bearer admin-token` is forbidden.",
    "hardcoded admin bearer is forbidden.",
    "mix unrelated app UI state with this app",
    "hide auth failure behind mock success",
    "python scripts/ops/quality/module_quality_gate.py --module desktop_auth_runtime",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### desktop_auth_runtime",
    "docs/baseline/modules/DESKTOP_AUTH_RUNTIME_BASELINE.md",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not DESKTOP_BASELINE.exists():
        return False, ["docs/baseline/modules/DESKTOP_AUTH_RUNTIME_BASELINE.md missing"]
    if not MODULE_BASELINE.exists():
        return False, ["docs/baseline/MODULE_BASELINE.md missing"]

    desktop_text = DESKTOP_BASELINE.read_text(encoding="utf-8", errors="replace")
    module_text = MODULE_BASELINE.read_text(encoding="utf-8", errors="replace")

    missing_desktop = missing_phrases(desktop_text, REQUIRED_DESKTOP_PHRASES)
    if missing_desktop:
        failures.append("desktop_auth_runtime baseline missing phrase(s): " + ", ".join(missing_desktop))

    missing_module_refs = missing_phrases(module_text, REQUIRED_MODULE_BASELINE_PHRASES)
    if missing_module_refs:
        failures.append("module baseline missing desktop_auth_runtime reference(s): " + ", ".join(missing_module_refs))

    return not failures, failures or [
        "DESKTOP_AUTH_RUNTIME_BASELINE exists and is locked",
        "desktop auth/session/redaction/runtime-isolation boundaries are documented",
        "module baseline references DESKTOP_AUTH_RUNTIME_BASELINE",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_DESKTOP_AUTH_RUNTIME_BASELINE_CONTRACT' if ok else 'FAIL_DESKTOP_AUTH_RUNTIME_BASELINE_CONTRACT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

