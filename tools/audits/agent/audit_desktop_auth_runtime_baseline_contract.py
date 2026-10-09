"""Read-only audit for the locked desktop_auth_runtime baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
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
    "python tools/quality/module_quality_gate.py --module desktop_auth_runtime",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### desktop_auth_runtime",
    "docs/baseline/modules/DESKTOP_AUTH_RUNTIME_BASELINE.md",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    from scripts.common.audit_cli import BaselineRefSpec, audit_baseline_with_module_ref

    return audit_baseline_with_module_ref(
        BaselineRefSpec(
            baseline=DESKTOP_BASELINE,
            baseline_missing="docs/baseline/modules/DESKTOP_AUTH_RUNTIME_BASELINE.md missing",
            baseline_phrases=REQUIRED_DESKTOP_PHRASES,
            baseline_fail_prefix="desktop_auth_runtime baseline missing phrase(s): ",
            module_baseline=MODULE_BASELINE,
            module_missing="docs/baseline/MODULE_BASELINE.md missing",
            module_phrases=REQUIRED_MODULE_BASELINE_PHRASES,
            module_fail_prefix="module baseline missing desktop_auth_runtime reference(s): ",
            success=[
                "DESKTOP_AUTH_RUNTIME_BASELINE exists and is locked",
                "desktop auth/session/redaction/runtime-isolation boundaries are documented",
                "module baseline references DESKTOP_AUTH_RUNTIME_BASELINE",
            ],
        ),
        missing_phrases,
    )


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "DESKTOP_AUTH_RUNTIME_BASELINE_CONTRACT")


if __name__ == "__main__":
    raise SystemExit(main())
