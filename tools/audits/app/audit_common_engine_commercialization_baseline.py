"""Read-only audit for the common engine commercialization baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE = ROOT / "docs" / "baseline" / "modules" / "COMMON_ENGINE_COMMERCIALIZATION_BASELINE.md"
APP_BASELINE = ROOT / "docs" / "baseline" / "APP_BASELINE.md"
MODULE_BASELINE = ROOT / "docs" / "baseline" / "MODULE_BASELINE.md"
REVIEW = ROOT / "docs" / "reports" / "commercialization_common_engine_review_20260525.md"

REQUIRED_BASELINE_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-COMMON-ENGINE-COMMERCIALIZATION-BASELINE-01",
    "The app is the control surface.",
    "commercial product",
    "common engine contract",
    "connection and recovery hardening",
    "local_agent_connection_recovery",
    "site/tool-specific module baseline",
    "app control surface",
    "app UI first",
    "stale token detection",
    "WebSocket reconnect and backoff policy",
    "task dispatch health check",
    "normalized task/result contract",
    "no-final-submit mode",
    "Approval API failure",
    "Evidence must not contain raw secrets",
    "python tools/quality/module_quality_gate.py --module common_engine_commercialization",
)

REQUIRED_APP_BASELINE_PHRASES = (
    "common_engine_commercialization",
    "docs/baseline/modules/COMMON_ENGINE_COMMERCIALIZATION_BASELINE.md",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### common_engine_commercialization",
    "COMMON_ENGINE_COMMERCIALIZATION_BASELINE.md",
    "app control surface",
)

REQUIRED_REVIEW_PHRASES = (
    "COMMON_ENGINE_COMMERCIALIZATION_BASELINE_01",
    "The app should be treated as the control surface",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    for path in (BASELINE, APP_BASELINE, MODULE_BASELINE, REVIEW):
        if not path.exists():
            failures.append(f"{path.relative_to(ROOT)} missing")
    if failures:
        return False, failures

    baseline_text = _read(BASELINE)
    app_text = _read(APP_BASELINE)
    module_text = _read(MODULE_BASELINE)
    review_text = _read(REVIEW)

    missing = [phrase for phrase in REQUIRED_BASELINE_PHRASES if phrase not in baseline_text]
    if missing:
        failures.append("commercialization baseline missing phrase(s): " + ", ".join(missing))

    missing = [phrase for phrase in REQUIRED_APP_BASELINE_PHRASES if phrase not in app_text]
    if missing:
        failures.append("app baseline missing phrase(s): " + ", ".join(missing))

    missing = [phrase for phrase in REQUIRED_MODULE_BASELINE_PHRASES if phrase not in module_text]
    if missing:
        failures.append("module baseline missing phrase(s): " + ", ".join(missing))

    missing = [phrase for phrase in REQUIRED_REVIEW_PHRASES if phrase not in review_text]
    if missing:
        failures.append("review note missing phrase(s): " + ", ".join(missing))

    return not failures, failures or [
        "COMMON_ENGINE_COMMERCIALIZATION_BASELINE exists and is locked",
        "APP_BASELINE references common_engine_commercialization",
        "MODULE_BASELINE defines common_engine_commercialization",
        "commercialization review points to the locked baseline work item",
    ]


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "COMMON_ENGINE_COMMERCIALIZATION_BASELINE")


if __name__ == "__main__":
    raise SystemExit(main())
