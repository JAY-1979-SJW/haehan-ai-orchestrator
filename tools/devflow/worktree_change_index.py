"""Build a classified index of the current git worktree.

The output is a management index: it groups changed files by git status,
architecture layer, site owner, and broad review category.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
DEFAULT_OUTPUT = ROOT / "data" / "worktree_change_index_latest.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.code_map.layer_rules import classify_path  # noqa: E402

SITE_IDS = {"eum", "hiworks", "naver", "google", "g2b", "kakao", "smartstore"}


@dataclass(frozen=True)
class WorktreeChange:
    path: str
    status: str
    status_label: str
    layer: str
    layer_reason: str
    category: str
    owner: str
    old_path: str = ""


def run_git_status(root: Path = ROOT) -> str:
    result = subprocess.run(  # noqa: UP022 - 이동 전부터 있던 기존 패턴, 이동과 무관
        ["git", "status", "--porcelain=v1"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    return result.stdout


def parse_porcelain(output: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for raw in output.splitlines():
        if not raw:
            continue
        status = raw[:2]
        payload = raw[3:].strip()
        old_path = ""
        path = payload
        if " -> " in payload:
            old_path, path = payload.split(" -> ", 1)
        rows.append((status, path.replace("\\", "/"), old_path.replace("\\", "/")))
    return rows


def status_label(status: str) -> str:
    if status == "??":
        return "untracked"
    if "R" in status:
        return "renamed"
    if "D" in status and "A" not in status:
        return "deleted"
    if "A" in status:
        return "added"
    if "M" in status:
        return "modified"
    return "changed"


def owner_for(path: str) -> str:
    parts = path.split("/")
    name = parts[-1]
    if len(parts) == 1 and name.startswith("test_"):
        return "tests"
    if len(parts) >= 2 and parts[0] == "scripts" and parts[1] in SITE_IDS:
        return parts[1]
    if len(parts) >= 2 and parts[0] == "docs":
        return "docs"
    if len(parts) >= 2 and parts[0] == "tests":
        return "tests"
    if len(parts) >= 2 and parts[0] == "configs":
        return "config"
    if len(parts) >= 2 and parts[0] in {"data", "tmp", "logs", "runs", "storage"}:
        return "runtime"
    if path.startswith("ai_orchestrator/"):
        return "platform"
    if path.startswith(("agent/", "local_agent/")):
        return "local_agent"
    return "repo"


def category_for(path: str, layer: str) -> str:
    if path in {".gitignore", ".gitattributes", ".dockerignore"}:
        return "contract_or_policy"
    if layer == "L0" or path.startswith(("data/", "tmp/", "logs/", "runs/", "storage/")):
        return "runtime_artifact"
    if layer == "L11":
        return "test"
    if layer == "L12":
        return "doc_or_archive"
    if layer in {"L1", "L2"} or path.startswith("configs/"):
        return "contract_or_policy"
    if layer in {"L5", "L6"}:
        return "site_automation"
    if layer == "L7":
        return "audit_or_persistence"
    if layer in {"L8", "L9"}:
        return "app_surface"
    if layer == "L10":
        return "local_pc_automation"
    return "active_code"


def classify_changes(rows: list[tuple[str, str, str]]) -> list[WorktreeChange]:
    changes: list[WorktreeChange] = []
    for status, path, old_path in rows:
        layer, reason = classify_path(path)
        changes.append(
            WorktreeChange(
                path=path,
                old_path=old_path,
                status=status.strip() or status,
                status_label=status_label(status),
                layer=layer,
                layer_reason=reason,
                category=category_for(path, layer),
                owner=owner_for(path),
            )
        )
    return changes


def _count(rows: list[WorktreeChange], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(getattr(row, key))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def build_index(status_output: str | None = None, *, root: Path = ROOT) -> dict[str, Any]:
    rows = parse_porcelain(status_output if status_output is not None else run_git_status(root))
    changes = classify_changes(rows)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "root": str(root),
        "summary": {
            "changed_count": len(changes),
            "by_status": _count(changes, "status_label"),
            "by_layer": _count(changes, "layer"),
            "by_category": _count(changes, "category"),
            "by_owner": _count(changes, "owner"),
        },
        "operating_rules": {
            "before_new_work": [
                "Generate this worktree index before starting a new task.",
                "Record pre-change dry-run evidence for the selected scope before editing code.",
                "Choose one owner/category as the current work scope.",
                "Read existing changes in that scope before editing files.",
                "Do not revert unrelated existing user changes.",
            ],
            "during_error_or_uncertainty": [
                "Regenerate this index when an error may be caused by local changes.",
                "Check whether the failing file is runtime_artifact, active_code, site_automation, contract_or_policy, or test.",
                "Consult the reference documents listed in reference_pack before changing direction.",
                "If deploy-related files are involved, require deploy dry-run evidence before commit or deployment.",
            ],
            "commit_handling": [
                "Review contract_or_policy and active_code before staging.",
                "Keep runtime_artifact out of commits unless explicitly promoted.",
                "Site automation changes require matching docs or tests.",
                "Existing active code changes require intentional approval in the quality gate.",
            ],
        },
        "reference_pack": [
            "docs/worktree_management_index.md",
            "docs/layer_classification.md",
            "docs/site_automation_reference_index.md",
            "docs/site_automation_status_index.md",
            "docs/realtime_audit_logging.md",
            "docs/pre_change_dry_run_policy_20260513.md",
            "tools/quality/quality_gate.py",
            "tools/devflow/pre_change_dry_run.py",
            "tools/deploy/deploy_dry_run.py",
        ],
        "changes": [asdict(row) for row in changes],
    }


def save_index(index: dict[str, Any], output: Path = DEFAULT_OUTPUT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def print_summary(index: dict[str, Any]) -> None:
    summary = index["summary"]
    print("Worktree change index")
    print("=" * 60)
    print(f"changed: {summary['changed_count']}")
    for name in ("by_status", "by_layer", "by_category", "by_owner"):
        print(f"{name}:")
        for key, value in summary[name].items():
            print(f"- {key}: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify and index current git worktree changes.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSON output path.")
    parser.add_argument("--json", action="store_true", help="Print full JSON index.")
    args = parser.parse_args()

    index = build_index()
    save_index(index, Path(args.output))
    if args.json:
        print(json.dumps(index, ensure_ascii=False, indent=2))
    else:
        print_summary(index)
        print(f"saved: {Path(args.output).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
