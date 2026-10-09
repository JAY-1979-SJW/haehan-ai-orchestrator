"""Read-only audit for the locked playwright_ai baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
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
    "python tools/verify/dry_run_local_agent_cdp_attach.py",
    "python tools/quality/module_quality_gate.py --module repo_guard",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### playwright_ai",
    "docs/baseline/modules/PLAYWRIGHT_AI_BASELINE.md",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    from scripts.common.audit_cli import BaselineRefSpec, audit_baseline_with_module_ref

    return audit_baseline_with_module_ref(
        BaselineRefSpec(
            baseline=PLAYWRIGHT_BASELINE,
            baseline_missing="docs/baseline/modules/PLAYWRIGHT_AI_BASELINE.md missing",
            baseline_phrases=REQUIRED_PLAYWRIGHT_PHRASES,
            baseline_fail_prefix="playwright_ai baseline missing phrase(s): ",
            module_baseline=MODULE_BASELINE,
            module_missing="docs/baseline/MODULE_BASELINE.md missing",
            module_phrases=REQUIRED_MODULE_BASELINE_PHRASES,
            module_fail_prefix="module baseline missing playwright_ai reference(s): ",
            success=[
                "PLAYWRIGHT_AI_BASELINE exists and is locked",
                "Playwright/AI local-only, approval, dry-run, and redaction boundaries are documented",
                "module baseline references PLAYWRIGHT_AI_BASELINE",
            ],
        ),
        missing_phrases,
    )


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "PLAYWRIGHT_AI_BASELINE_CONTRACT")


if __name__ == "__main__":
    raise SystemExit(main())
