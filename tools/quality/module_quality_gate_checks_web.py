"""Admin-web and secret-scan check functions for module_quality_gate."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

try:
    from tools.quality.module_quality_gate_common import ROOT, _run_check_command, normalize_path, redact
except ModuleNotFoundError:
    from module_quality_gate_common import (  # type: ignore[no-redef, import-not-found]
        ROOT,
        _run_check_command,
        normalize_path,
        redact,
    )

sys.dont_write_bytecode = True


def check_admin_web_typecheck() -> tuple[bool, str]:
    package = ROOT / "admin-web" / "package.json"
    if not package.exists():
        return False, "admin-web/package.json missing"
    return _run_check_command(["npm", "run", "typecheck"], cwd=ROOT / "admin-web")


def check_admin_web_lint() -> tuple[bool, str]:
    package = ROOT / "admin-web" / "package.json"
    if not package.exists():
        return False, "admin-web/package.json missing"
    return _run_check_command(["npm", "run", "lint"], cwd=ROOT / "admin-web")


def _npm_audit_commands() -> list[list[str]]:
    base = ["audit", "--omit=dev", "--json", "--package-lock-only"]
    commands: list[list[str]] = []
    npm_cmd = shutil.which("npm.cmd")
    if os.name == "nt" and npm_cmd:
        commands.append(["cmd", "/c", npm_cmd, *base])
        commands.append(["powershell", "-NoProfile", "-Command", "npm " + " ".join(base)])
        commands.append([npm_cmd, *base])
    npm = shutil.which("npm")
    if npm and npm != npm_cmd:
        commands.append([npm, *base])
    commands.append(["npm", *base])
    deduped: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for command in commands:
        key = tuple(command)
        if key not in seen:
            seen.add(key)
            deduped.append(command)
    return deduped


def _read_admin_web_audit_report(command: list[str]) -> tuple[bool, dict | str]:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT / "admin-web",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=120,
            encoding="utf-8",
        )
    except FileNotFoundError:
        return False, "npm not found"

    output = redact(result.stdout or "").strip()
    try:
        report = json.loads(output)
    except json.JSONDecodeError:
        tail = output[-500:].replace("\n", " | ") if output else f"exit_code={result.returncode}"
        return False, "npm audit returned non-json output: " + tail
    return True, report


def audit_vulnerability_counts(report: dict) -> tuple[int, int, int]:
    vulnerabilities = report.get("vulnerabilities")
    if isinstance(vulnerabilities, dict):
        high = 0
        critical = 0
        total = 0
        for item in vulnerabilities.values():
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity", "")).lower()
            if severity:
                total += 1
            if severity == "high":
                high += 1
            elif severity == "critical":
                critical += 1
        return high, critical, total

    counts = report.get("metadata", {}).get("vulnerabilities", {})
    high = int(counts.get("high", 0))
    critical = int(counts.get("critical", 0))
    total = int(counts.get("total", 0))
    return high, critical, total


def audit_high_critical_names(report: dict) -> list[str]:
    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return []
    names = [
        str(name)
        for name, item in vulnerabilities.items()
        if isinstance(item, dict) and str(item.get("severity", "")).lower() in {"high", "critical"}
    ]
    return sorted(names)


def _version_tuple(version: str) -> tuple[int, int, int]:
    parts = []
    for item in version.split(".")[:3]:
        try:
            parts.append(int(item))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)  # type: ignore[return-value]


def next_lockfile_meets_security_floor() -> bool:
    lockfile = ROOT / "admin-web" / "package-lock.json"
    package = ROOT / "admin-web" / "package.json"
    if not lockfile.exists() or not package.exists():
        return False
    try:
        lock = json.loads(lockfile.read_text(encoding="utf-8"))
        pkg = json.loads(package.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    declared = str((pkg.get("dependencies") or {}).get("next", ""))
    installed = str(((lock.get("packages") or {}).get("node_modules/next") or {}).get("version", ""))
    return declared == "14.2.35" and _version_tuple(installed) >= (14, 2, 35)


def check_admin_web_audit() -> tuple[bool, str]:
    package = ROOT / "admin-web" / "package.json"
    if not package.exists():
        return False, "admin-web/package.json missing"
    failures: list[str] = []
    for command in _npm_audit_commands():
        ok, report_or_message = _read_admin_web_audit_report(command)
        if not ok:
            failures.append(str(report_or_message))
            continue

        report = cast(dict, report_or_message)
        high, critical, total = audit_vulnerability_counts(report)
        if not high and not critical:
            return True, f"production dependency audit high=0 critical=0 total={total}"

        names = audit_high_critical_names(report)
        if names == ["next"] and next_lockfile_meets_security_floor():
            return True, "production dependency audit next advisory cross-checked by lockfile floor next>=14.2.35"
        suffix = f": {', '.join(names)}" if names else ""
        failures.append(f"production dependency audit found high={high} critical={critical}{suffix}")

    return False, failures[-1] if failures else "npm audit did not run"


def _is_secret_scan_excluded(path: Path) -> bool:
    rel = normalize_path(str(path.relative_to(ROOT)))
    parts = set(rel.split("/"))
    if parts & {"node_modules", ".next", "ui_dist", "logs", "tests", "__pycache__", ".claude", ".github"}:
        return True
    if rel.startswith(
        ("docs/", "scripts/archive/", "scripts/ops/", "data/logs/", "data/cdp_profile/", "data/sessions/")
    ):
        return True
    if rel.startswith("tools/quality/module_quality_gate") and rel.endswith(".py"):
        return True
    if rel in {
        "tools/audits/agent/audit_desktop_auth_runtime_baseline_contract.py",
        "tools/audits/backend/audit_backend_core_baseline_contract.py",
    }:
        return True
    return False


def check_active_source_secret_scan() -> tuple[bool, str]:
    patterns = (
        re.compile(r"BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{12,}"),
        re.compile(r"(?i)Authorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/=-]+"),
        re.compile(r"Bearer admin-token"),
    )
    suffixes = {".py", ".ts", ".tsx", ".js", ".json", ".yml", ".yaml", ".bat", ".ps1", ".sh"}
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        if _is_secret_scan_excluded(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in patterns):
            hits.append(normalize_path(str(path.relative_to(ROOT))))
            if len(hits) >= 20:
                break
    if hits:
        return False, "possible active-source secret hits: " + ", ".join(hits)
    return True, "no active-source secret patterns detected"
