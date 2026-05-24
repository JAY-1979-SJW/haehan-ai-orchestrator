"""Read-only audit for the locked release_preflight baseline."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RELEASE_PREFLIGHT_BASELINE = ROOT / "docs" / "baseline" / "modules" / "RELEASE_PREFLIGHT_BASELINE.md"
MODULE_BASELINE = ROOT / "docs" / "baseline" / "MODULE_BASELINE.md"

REQUIRED_RELEASE_PREFLIGHT_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-RELEASE-PREFLIGHT-BASELINE-01",
    "no-build release readiness check",
    "admin-web static checks",
    "UI residue audit",
    "secret scan classification",
    "module gate verification",
    "OUT_OF_SCOPE preservation",
    "dirty tree classification",
    "PASS/WARN/FAIL release readiness summary",
    "source tree",
    "package/build script metadata",
    "git status",
    "secret finding classification",
    "UI residue WARN/FAIL classification",
    "release readiness decision",
    "Preflight must not run `npm run build`.",
    "Preflight must not run `electron-builder`.",
    "Preflight must not run `pyinstaller`.",
    "Preflight must not run Docker build, pull, up, restart, or deploy.",
    "Secret scan findings must be classified.",
    "Active-source raw secrets are FAIL.",
    "UI residue cleanup must not run during preflight unless explicitly approved.",
    "Environment WARN must be reported separately from security FAIL.",
    "python scripts/module_quality_gate.py --module release_preflight --dry-run",
    "python scripts/required_quality_gate.py",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### release_preflight",
    "docs/baseline/modules/RELEASE_PREFLIGHT_BASELINE.md",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not RELEASE_PREFLIGHT_BASELINE.exists():
        return False, ["docs/baseline/modules/RELEASE_PREFLIGHT_BASELINE.md missing"]
    if not MODULE_BASELINE.exists():
        return False, ["docs/baseline/MODULE_BASELINE.md missing"]

    release_text = RELEASE_PREFLIGHT_BASELINE.read_text(encoding="utf-8", errors="replace")
    module_text = MODULE_BASELINE.read_text(encoding="utf-8", errors="replace")

    missing_release = missing_phrases(release_text, REQUIRED_RELEASE_PREFLIGHT_PHRASES)
    if missing_release:
        failures.append("release_preflight baseline missing phrase(s): " + ", ".join(missing_release))

    missing_module_refs = missing_phrases(module_text, REQUIRED_MODULE_BASELINE_PHRASES)
    if missing_module_refs:
        failures.append("module baseline missing release_preflight reference(s): " + ", ".join(missing_module_refs))

    return not failures, failures or [
        "RELEASE_PREFLIGHT_BASELINE exists and is locked",
        "release preflight static/no-build/secret/UI residue boundaries are documented",
        "module baseline references RELEASE_PREFLIGHT_BASELINE",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_RELEASE_PREFLIGHT_BASELINE_CONTRACT' if ok else 'FAIL_RELEASE_PREFLIGHT_BASELINE_CONTRACT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

