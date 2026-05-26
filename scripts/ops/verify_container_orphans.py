"""Verify that a running container has no untracked code artifacts.

This is read-only. It compares files inside the container with files tracked by
Git in the repository. Runtime state, caches, and explicitly ignored operational
paths are excluded from the comparison.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTAINER = "haehan-ai-orchestrator-api"
DEFAULT_CONTAINER_ROOT = "/app"
IGNORE_PREFIXES = (
    ".git/",
    "ai_orchestrator/storage/",
    "data/",
    "logs/",
    "storage/",
)
IGNORE_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".next",
}
MISSING_ALLOWED_PREFIXES = (
    "data/",
    "docs/",
    "local_agent/",
)
MISSING_ALLOWED_NAMES = {
    ".env.example",
    ".gitignore",
}
MISSING_ALLOWED_SUFFIXES = (
    ".md",
    ".txt",
)


def run(args: list[str], *, cwd: Path | None = None, timeout: int = 60) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def git_tracked_files(root: Path) -> set[str]:
    code, out, err = run(["git", "ls-files"], cwd=root)
    if code != 0:
        raise RuntimeError(f"git ls-files failed: {err or out}")
    return set(out.splitlines())


CONTAINER_LIST_CODE = r"""
import json
from pathlib import Path

root = Path(%(container_root)r)
files = []
for path in root.rglob("*"):
    if path.is_file():
        files.append(path.relative_to(root).as_posix())
print(json.dumps(files))
"""


def container_files(container: str, *, container_root: str) -> set[str]:
    code = CONTAINER_LIST_CODE % {"container_root": container_root}
    rc, out, err = run(["docker", "exec", container, "python", "-c", code], timeout=180)
    if rc != 0:
        raise RuntimeError(f"docker exec file listing failed: {err or out}")
    return set(json.loads(out))


def ignored_container_file(rel: str) -> bool:
    if rel.startswith(IGNORE_PREFIXES):
        return True
    return bool(set(rel.split("/")) & IGNORE_PARTS)


def allowed_missing_tracked_file(rel: str) -> bool:
    if rel in MISSING_ALLOWED_NAMES:
        return True
    if rel.startswith(MISSING_ALLOWED_PREFIXES):
        return True
    return rel.endswith(MISSING_ALLOWED_SUFFIXES)


def evaluate(
    *,
    tracked: set[str],
    container: set[str],
) -> dict[str, Any]:
    considered = {rel for rel in container if not ignored_container_file(rel)}
    untracked = sorted(rel for rel in considered if rel not in tracked)
    missing = sorted(rel for rel in tracked if not allowed_missing_tracked_file(rel) and rel not in container)
    failed = []
    if untracked:
        failed.append("untracked_files_in_container")
    return {
        "ok": not failed,
        "status": "ok" if not failed else "container_orphans_detected",
        "failed_check_ids": failed,
        "tracked_count": len(tracked),
        "container_file_count": len(container),
        "container_files_considered": len(considered),
        "untracked_in_container_count": len(untracked),
        "tracked_missing_from_container_count": len(missing),
        "untracked_in_container": untracked,
        "tracked_missing_from_container": missing,
        "secret_values_output": False,
    }


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        "Container orphan verification",
        f"status: {payload['status']}",
        f"tracked_count: {payload['tracked_count']}",
        f"container_file_count: {payload['container_file_count']}",
        f"container_files_considered: {payload['container_files_considered']}",
        f"untracked_in_container_count: {payload['untracked_in_container_count']}",
        f"tracked_missing_from_container_count: {payload['tracked_missing_from_container_count']}",
    ]
    if payload["untracked_in_container"]:
        lines.append("")
        lines.append("untracked_in_container:")
        lines.extend(f"- {item}" for item in payload["untracked_in_container"][:100])
    if payload["tracked_missing_from_container"]:
        lines.append("")
        lines.append("tracked_missing_from_container:")
        lines.extend(f"- {item}" for item in payload["tracked_missing_from_container"][:100])
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify no untracked code artifacts exist in a container.")
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--container-root", default=DEFAULT_CONTAINER_ROOT)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = evaluate(
        tracked=git_tracked_files(ROOT),
        container=container_files(args.container, container_root=args.container_root),
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(payload))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
