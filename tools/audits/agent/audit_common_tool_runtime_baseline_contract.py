"""Read-only audit for the locked common_tool_runtime baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

COMMON_BASELINE = ROOT / "docs" / "baseline" / "modules" / "COMMON_TOOL_RUNTIME_BASELINE.md"
MODULE_BASELINE = ROOT / "docs" / "baseline" / "MODULE_BASELINE.md"

REQUIRED_COMMON_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-COMMON-TOOL-RUNTIME-BASELINE-01",
    "task contract",
    "result contract",
    "risk level",
    "approval requirement",
    "forbidden field rejection",
    "safe execution metadata",
    "redacted result metadata",
    "normalized tool task request",
    "execution context",
    "tool name",
    "action",
    "parameters",
    "risk classification",
    "accepted task contract",
    "rejected task contract",
    "approval required flag",
    "raw Authorization header",
    "raw secret, token, cookie, session, password, or OTP",
    "approval-required task without approval",
    "Approval-required risk must not be bypassed by callers.",
    "Forbidden field rejection must occur before execution is delegated",
    "execute browser work directly",
    "call Playwright directly",
    "duplicate site-specific workflow logic",
    "python tools/audits/agent/audit_common_tool_runtime.py",
    "python -m pytest tests/test_common_tool_runtime.py -q",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### common_tool_runtime",
    "docs/baseline/modules/COMMON_TOOL_RUNTIME_BASELINE.md",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    from scripts.common.audit_cli import BaselineRefSpec, audit_baseline_with_module_ref

    return audit_baseline_with_module_ref(
        BaselineRefSpec(
            baseline=COMMON_BASELINE,
            baseline_missing="docs/baseline/modules/COMMON_TOOL_RUNTIME_BASELINE.md missing",
            baseline_phrases=REQUIRED_COMMON_PHRASES,
            baseline_fail_prefix="common_tool_runtime baseline missing phrase(s): ",
            module_baseline=MODULE_BASELINE,
            module_missing="docs/baseline/MODULE_BASELINE.md missing",
            module_phrases=REQUIRED_MODULE_BASELINE_PHRASES,
            module_fail_prefix="module baseline missing common_tool_runtime reference(s): ",
            success=[
                "COMMON_TOOL_RUNTIME_BASELINE exists and is locked",
                "common task/result/risk/approval/forbidden-field boundaries are documented",
                "module baseline references COMMON_TOOL_RUNTIME_BASELINE",
            ],
        ),
        missing_phrases,
    )


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "COMMON_TOOL_RUNTIME_BASELINE_CONTRACT")


if __name__ == "__main__":
    raise SystemExit(main())
