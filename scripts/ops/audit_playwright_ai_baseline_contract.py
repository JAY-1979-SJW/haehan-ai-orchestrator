"""Read-only audit for the locked playwright_ai baseline."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PLAYWRIGHT_BASELINE = ROOT / "docs" / "baseline" / "modules" / "PLAYWRIGHT_AI_BASELINE.md"
MODULE_BASELINE = ROOT / "docs" / "baseline" / "MODULE_BASELINE.md"

REQUIRED_PLAYWRIGHT_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-PLAYWRIGHT-AI-BASELINE-01",
    "local-only browser automation",
    "AI-assisted task planning for approved browser tasks",
    "Playwright/CDP dry-run and live-stage separation",
    "screenshot/capture approval boundary",
    "redacted browser observation return",
    "prompt and secret redaction boundaries",
    "approved browser task contract",
    "AI prompt context without raw secrets",
    "server-side browser execution request",
    "credential/session/cookie extraction request",
    "redacted observation",
    "approved screenshot/capture result",
    "raw prompt containing secrets",
    "raw CDP websocket URL with sensitive query material",
    "Server must not run Playwright directly.",
    "Browser execution must be local-agent mediated.",
    "Dry-run checks must remain side-effect free.",
    "Live browser checks require explicit approval.",
    "Unapproved high-risk browser tasks must not execute.",
    "execute server-side Playwright",
    "bypass local-agent dispatch",
    "use AI output as authorization or approval",
    "python scripts/ops/dry_run_local_agent_cdp_attach.py",
    "python scripts/ops/quality/module_quality_gate.py --module repo_guard",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### playwright_ai",
    "docs/baseline/modules/PLAYWRIGHT_AI_BASELINE.md",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not PLAYWRIGHT_BASELINE.exists():
        return False, ["docs/baseline/modules/PLAYWRIGHT_AI_BASELINE.md missing"]
    if not MODULE_BASELINE.exists():
        return False, ["docs/baseline/MODULE_BASELINE.md missing"]

    playwright_text = PLAYWRIGHT_BASELINE.read_text(encoding="utf-8", errors="replace")
    module_text = MODULE_BASELINE.read_text(encoding="utf-8", errors="replace")

    missing_playwright = missing_phrases(playwright_text, REQUIRED_PLAYWRIGHT_PHRASES)
    if missing_playwright:
        failures.append("playwright_ai baseline missing phrase(s): " + ", ".join(missing_playwright))

    missing_module_refs = missing_phrases(module_text, REQUIRED_MODULE_BASELINE_PHRASES)
    if missing_module_refs:
        failures.append("module baseline missing playwright_ai reference(s): " + ", ".join(missing_module_refs))

    return not failures, failures or [
        "PLAYWRIGHT_AI_BASELINE exists and is locked",
        "Playwright/AI local-only, approval, dry-run, and redaction boundaries are documented",
        "module baseline references PLAYWRIGHT_AI_BASELINE",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_PLAYWRIGHT_AI_BASELINE_CONTRACT' if ok else 'FAIL_PLAYWRIGHT_AI_BASELINE_CONTRACT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

