"""Read-only audit for the locked portable_install baseline."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PORTABLE_BASELINE = ROOT / "docs" / "baseline" / "modules" / "PORTABLE_INSTALL_BASELINE.md"
MODULE_BASELINE = ROOT / "docs" / "baseline" / "MODULE_BASELINE.md"

REQUIRED_PORTABLE_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-PORTABLE-INSTALL-BASELINE-01",
    "`install.bat`",
    "`start.bat`",
    "`diagnostics.bat`",
    "`uninstall.bat`",
    "`README_실행방법.txt`",
    "no-admin install flow",
    "logs/config folder creation",
    "desktop shortcut creation",
    "desktop shortcut removal",
    "secret-masked diagnostics",
    "extracted portable folder",
    "installer exe build request",
    "Program Files install request",
    "registry modification request",
    "PATH modification request",
    "desktop shortcut",
    "diagnostics log",
    "shortcut removal only on uninstall",
    "`install.bat` must run without administrator rights.",
    "Installation must not copy files into Program Files.",
    "Installation must not edit registry.",
    "Installation must not edit PATH.",
    "Failure must guide the user to `diagnostics.bat`.",
    "Diagnostics must mask secrets.",
    "`uninstall.bat` removes shortcuts only.",
    "`uninstall.bat` must not delete logs.",
    "python scripts/module_quality_gate.py --module portable_install",
)

REQUIRED_MODULE_BASELINE_PHRASES = (
    "### portable_install",
    "docs/baseline/modules/PORTABLE_INSTALL_BASELINE.md",
)


def missing_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not PORTABLE_BASELINE.exists():
        return False, ["docs/baseline/modules/PORTABLE_INSTALL_BASELINE.md missing"]
    if not MODULE_BASELINE.exists():
        return False, ["docs/baseline/MODULE_BASELINE.md missing"]

    portable_text = PORTABLE_BASELINE.read_text(encoding="utf-8", errors="replace")
    module_text = MODULE_BASELINE.read_text(encoding="utf-8", errors="replace")

    missing_portable = missing_phrases(portable_text, REQUIRED_PORTABLE_PHRASES)
    if missing_portable:
        failures.append("portable_install baseline missing phrase(s): " + ", ".join(missing_portable))

    missing_module_refs = missing_phrases(module_text, REQUIRED_MODULE_BASELINE_PHRASES)
    if missing_module_refs:
        failures.append("module baseline missing portable_install reference(s): " + ", ".join(missing_module_refs))

    return not failures, failures or [
        "PORTABLE_INSTALL_BASELINE exists and is locked",
        "portable install/start/diagnostics/uninstall boundaries are documented",
        "module baseline references PORTABLE_INSTALL_BASELINE",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_PORTABLE_INSTALL_BASELINE_CONTRACT' if ok else 'FAIL_PORTABLE_INSTALL_BASELINE_CONTRACT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

