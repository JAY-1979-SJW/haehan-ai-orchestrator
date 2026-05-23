"""Read-only audit for the locked common_tool_runtime baseline."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
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
    "python scripts/ops/audit_common_tool_runtime.py",
    "python -m pytest tests/test_common_tool_runtime.py -q",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### common_tool_runtime",
    "docs/baseline/modules/COMMON_TOOL_RUNTIME_BASELINE.md",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not COMMON_BASELINE.exists():
        return False, ["docs/baseline/modules/COMMON_TOOL_RUNTIME_BASELINE.md missing"]
    if not MODULE_BASELINE.exists():
        return False, ["docs/baseline/MODULE_BASELINE.md missing"]

    common_text = COMMON_BASELINE.read_text(encoding="utf-8", errors="replace")
    module_text = MODULE_BASELINE.read_text(encoding="utf-8", errors="replace")

    missing_common = missing_phrases(common_text, REQUIRED_COMMON_PHRASES)
    if missing_common:
        failures.append("common_tool_runtime baseline missing phrase(s): " + ", ".join(missing_common))

    missing_module_refs = missing_phrases(module_text, REQUIRED_MODULE_BASELINE_PHRASES)
    if missing_module_refs:
        failures.append("module baseline missing common_tool_runtime reference(s): " + ", ".join(missing_module_refs))

    return not failures, failures or [
        "COMMON_TOOL_RUNTIME_BASELINE exists and is locked",
        "common task/result/risk/approval/forbidden-field boundaries are documented",
        "module baseline references COMMON_TOOL_RUNTIME_BASELINE",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_COMMON_TOOL_RUNTIME_BASELINE_CONTRACT' if ok else 'FAIL_COMMON_TOOL_RUNTIME_BASELINE_CONTRACT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

