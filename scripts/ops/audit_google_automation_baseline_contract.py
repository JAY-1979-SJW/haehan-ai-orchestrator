"""Read-only audit for the locked Google automation baseline."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE = ROOT / "docs" / "baseline" / "GOOGLE_AUTOMATION_BASELINE.md"

REQUIRED_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: GOOGLE-AUTOMATION-BASELINE-01",
    "Google tabs: 9",
    "Google surfaces: 50",
    "Google actions: 96",
    "Read actions: 50",
    "Approval actions: 46",
    "Host normalization warnings: 0",
    "user_present_session",
    "host_warnings == []",
    "scripts/google/tab_registry.py",
    "tests/test_google_tab_registry.py",
    "Do not split all Google modules in one change.",
)

REQUIRED_TABS = (
    "search",
    "identity",
    "workspace",
    "cloud",
    "ai",
    "youtube",
    "marketing",
    "developer",
    "media",
)


def _missing(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not BASELINE.exists():
        return False, ["docs/baseline/GOOGLE_AUTOMATION_BASELINE.md missing"]

    text = BASELINE.read_text(encoding="utf-8", errors="replace")
    missing = _missing(text, REQUIRED_PHRASES)
    if missing:
        failures.append("Google baseline missing phrase(s): " + ", ".join(missing))

    from scripts.google.tab_registry import GOOGLE_TABS, build_google_tab_summary

    tab_keys = tuple(tab.key for tab in GOOGLE_TABS)
    if tab_keys != REQUIRED_TABS:
        failures.append("Google tab order or keys changed: " + ", ".join(tab_keys))

    summary = build_google_tab_summary()
    counts = summary["counts"]
    expected_counts = {
        "tabs": 9,
        "surfaces": 50,
        "actions": 96,
        "read_actions": 50,
        "approval_actions": 46,
    }
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            failures.append(f"Google count mismatch {key}: expected {expected}, got {counts.get(key)}")

    if summary["host_warnings"]:
        failures.append(f"Google host warnings must be zero, got {len(summary['host_warnings'])}")

    return not failures, failures or [
        "GOOGLE_AUTOMATION_BASELINE exists and is locked",
        "9 Google tabs, 50 surfaces, and 96 actions are registered",
        "Google host warnings are zero",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_GOOGLE_AUTOMATION_BASELINE_CONTRACT' if ok else 'FAIL_GOOGLE_AUTOMATION_BASELINE_CONTRACT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

