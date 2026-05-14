"""Repository quality gate for change audit and pre-commit checks.

The gate is conservative by design: it audits all changes and only blocks in
`--enforce` mode. Pre-commit installation uses staged changes only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "quality_gate.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str


@dataclass(frozen=True)
class GateIssue:
    severity: str
    code: str
    path: str
    message: str


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def parse_porcelain(output: str) -> list[ChangedFile]:
    rows: list[ChangedFile] = []
    for raw in output.splitlines():
        if not raw:
            continue
        status = raw[:2].strip() or raw[:2]
        path = raw[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        rows.append(ChangedFile(path=path.replace("\\", "/"), status=status))
    return rows


def changed_files(*, staged: bool = False) -> list[ChangedFile]:
    args = ["diff", "--cached", "--name-status"] if staged else ["status", "--short"]
    output = _run_git(args)
    if staged:
        rows: list[ChangedFile] = []
        for raw in output.splitlines():
            if not raw:
                continue
            parts = raw.split("\t")
            status = parts[0]
            path = parts[-1]
            rows.append(ChangedFile(path=path.replace("\\", "/"), status=status))
        return rows
    return parse_porcelain(output)


def _starts(path: str, prefixes: Iterable[str]) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)


def _is_doc(path: str, config: dict[str, Any]) -> bool:
    return _starts(path, config["doc_prefixes"]) or path.endswith(".md")


def _is_test(path: str, config: dict[str, Any]) -> bool:
    return _starts(path, config["test_prefixes"]) or "/test_" in path or Path(path).name.startswith("test_")


def _is_runtime(path: str, config: dict[str, Any]) -> bool:
    return _starts(path, config["runtime_prefixes"])


def _is_active_code(path: str, config: dict[str, Any]) -> bool:
    if _is_runtime(path, config) or _is_doc(path, config) or _is_test(path, config):
        return False
    return _starts(path, config["active_code_prefixes"]) and Path(path).suffix.lower() in {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".sql",
        ".json",
        ".yml",
        ".yaml",
    }


def _is_schema_related(path: str, config: dict[str, Any]) -> bool:
    name = Path(path).name.lower()
    if path.startswith("migrations/") or path.endswith(".sql"):
        return True
    if not _starts(path, config["schema_prefixes"]):
        return False
    return any(token in name for token in config["schema_name_tokens"])


def _is_deploy_related(path: str, config: dict[str, Any]) -> bool:
    if _is_runtime(path, config) or _is_doc(path, config) or _is_test(path, config):
        return False
    if path.startswith("scripts/archive/"):
        return False
    name = Path(path).name
    if _starts(path, config.get("deploy_paths", [])):
        return True
    if "/" in path:
        return False
    return any(token.lower() in name.lower() for token in config.get("deploy_name_tokens", []))


def _diff_for(path: str, *, staged: bool) -> str:
    args = ["diff", "--cached", "--", path] if staged else ["diff", "--", path]
    try:
        return _run_git(args)
    except RuntimeError:
        return ""


def _has_destructive_sql(path: str, config: dict[str, Any], *, staged: bool) -> bool:
    if not (path.startswith("migrations/") or path.endswith(".sql")):
        return False
    diff = _diff_for(path, staged=staged).lower()
    added_lines = "\n".join(line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    return any(token in added_lines for token in config["destructive_sql_tokens"])


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _deploy_dry_run_evidence(config: dict[str, Any]) -> dict[str, Any] | None:
    path = ROOT / str(config.get("deploy_dry_run_evidence_path") or "")
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _deploy_dry_run_ok(config: dict[str, Any], deploy_paths: list[str]) -> bool:
    evidence = _deploy_dry_run_evidence(config)
    if not evidence or evidence.get("status") != "ok":
        return False
    generated = _parse_time(str(evidence.get("generated_at") or ""))
    if generated is None:
        return False

    latest_mtime = 0.0
    for path in deploy_paths:
        full = ROOT / path
        if full.exists():
            latest_mtime = max(latest_mtime, full.stat().st_mtime)
    if not latest_mtime:
        return True
    return generated.timestamp() >= latest_mtime


def record_deploy_dry_run(command: list[str], *, exit_code: int, output: str = "") -> Path:
    config = load_config()
    path = ROOT / str(config.get("deploy_dry_run_evidence_path"))
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "ok" if exit_code == 0 else "failed",
        "command": command,
        "exit_code": exit_code,
        "output_tail": output[-2000:],
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from scripts.realtime_audit import emit_event

        emit_event(
            "DEPLOY_DRY_RUN_RECORDED",
            site="repo",
            workflow="deploy_dry_run",
            status=record["status"],
            risk="deploy",
            message="deploy dry-run evidence recorded",
            artifact_path=str(path),
            metadata={"command": command, "exit_code": exit_code},
        )
    except Exception:
        pass
    return path


def evaluate_changes(
    files: list[ChangedFile],
    config: dict[str, Any],
    *,
    staged: bool = False,
    allow_existing_code_change: bool = False,
) -> list[GateIssue]:
    issues: list[GateIssue] = []
    paths = [row.path for row in files]
    code_paths = [p for p in paths if _is_active_code(p, config)]
    doc_paths = [p for p in paths if _is_doc(p, config)]
    test_paths = [p for p in paths if _is_test(p, config)]
    schema_paths = [p for p in paths if _is_schema_related(p, config)]
    deploy_paths = [p for p in paths if _is_deploy_related(p, config)]

    if code_paths and config.get("code_change_requires_test_or_doc") and not (doc_paths or test_paths):
        issues.append(
            GateIssue(
                "warn",
                "CODE_WITHOUT_TEST_OR_DOC",
                ",".join(code_paths[:5]),
                "Active code changed without accompanying test or design doc change.",
            )
        )

    if config.get("existing_code_change_requires_flag") and not allow_existing_code_change:
        for row in files:
            if row.status.startswith("M") and _is_active_code(row.path, config):
                issues.append(
                    GateIssue(
                        str(config.get("existing_code_change_severity") or "warn"),
                        "EXISTING_CODE_MODIFIED",
                        row.path,
                        "Existing active code was modified. Confirm this is intentional or pass --allow-existing-code-change.",
                    )
                )

    if schema_paths and config.get("schema_change_requires_doc_and_test") and not (doc_paths and test_paths):
        issues.append(
            GateIssue(
                "error",
                "SCHEMA_CHANGE_NEEDS_DOC_AND_TEST",
                ",".join(schema_paths[:5]),
                "Schema/DB-related changes require both documentation and tests.",
            )
        )

    for path in schema_paths:
        if _has_destructive_sql(path, config, staged=staged):
            issues.append(
                GateIssue(
                    "error",
                    "DESTRUCTIVE_SQL_REQUIRES_MANUAL_REVIEW",
                    path,
                    "Destructive SQL token detected in added lines.",
                )
            )

    if deploy_paths and config.get("deploy_dry_run_required") and not _deploy_dry_run_ok(config, deploy_paths):
        issues.append(
            GateIssue(
                "error",
                "DEPLOY_CHANGE_REQUIRES_DRY_RUN",
                ",".join(deploy_paths[:5]),
                "Deploy-related changes require successful deploy dry-run evidence before commit/deploy.",
            )
        )

    return issues


def summarize(files: list[ChangedFile], issues: list[GateIssue]) -> dict[str, Any]:
    return {
        "changed_count": len(files),
        "issue_count": len(issues),
        "errors": sum(1 for issue in issues if issue.severity == "error"),
        "warnings": sum(1 for issue in issues if issue.severity == "warn"),
        "files": [row.__dict__ for row in files],
        "issues": [issue.__dict__ for issue in issues],
    }


def emit_audit(summary: dict[str, Any]) -> None:
    try:
        from scripts.realtime_audit import emit_event

        status = "failed" if summary["errors"] else ("warn" if summary["warnings"] else "ok")
        emit_event(
            "QUALITY_GATE_CHECK",
            site="repo",
            workflow="quality_gate",
            status=status,
            risk="policy",
            message=f"quality gate: {summary['errors']} errors, {summary['warnings']} warnings",
            metadata=summary,
        )
    except Exception:
        pass


def print_summary(summary: dict[str, Any]) -> None:
    print("Quality gate")
    print("=" * 60)
    print(f"changed: {summary['changed_count']}")
    print(f"errors: {summary['errors']}")
    print(f"warnings: {summary['warnings']}")
    for issue in summary["issues"]:
        print(f"[{issue['severity']}] {issue['code']} {issue['path']} - {issue['message']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repository quality gate")
    parser.add_argument("--staged", action="store_true", help="check staged changes only")
    parser.add_argument("--enforce", action="store_true", help="return non-zero on errors")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--allow-existing-code-change", action="store_true")
    parser.add_argument(
        "--record-deploy-dry-run",
        nargs=argparse.REMAINDER,
        help="run a deploy dry-run command and record evidence; pass command after --",
    )
    args = parser.parse_args()

    if args.record_deploy_dry_run is not None:
        command = [part for part in args.record_deploy_dry_run if part != "--"]
        if not command:
            print("missing dry-run command", file=sys.stderr)
            return 2
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        path = record_deploy_dry_run(command, exit_code=result.returncode, output=result.stdout)
        print(result.stdout, end="")
        print(f"deploy dry-run evidence: {path}")
        return result.returncode

    config = load_config(args.config)
    files = changed_files(staged=args.staged)
    issues = evaluate_changes(
        files,
        config,
        staged=args.staged,
        allow_existing_code_change=args.allow_existing_code_change,
    )
    summary = summarize(files, issues)
    emit_audit(summary)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_summary(summary)

    if args.enforce and summary["errors"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
