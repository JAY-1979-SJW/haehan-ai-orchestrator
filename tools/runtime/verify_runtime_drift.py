"""Verify local, Git, server repo, and running container drift.

This check is read-only. It compares:
- local worktree/HEAD/origin
- server worktree/HEAD/origin
- running container source fingerprint

The container normally has no .git directory, so the script fingerprints the
runtime source tree inside the container and compares it with the server repo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
DEFAULT_SERVER = "haehan-app"
DEFAULT_REMOTE_PATH = "/home/ubuntu/apps/haehan-ai-orchestrator"
DEFAULT_CONTAINER = "haehan-ai-orchestrator-api"
DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "master"
DEFAULT_CONTAINER_ROOT = "/app"
DEFAULT_RUNTIME_PATHS = (
    "ai_orchestrator",
    "scripts",
    "requirements.txt",
    "Dockerfile",
    ".dockerignore",
)
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git", "storage"}
EXCLUDE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".md",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
}


def run_command(args: list[str], *, cwd: Path | None = None, timeout: int = 60) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        encoding="utf-8",
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def run_command_stdin(
    args: list[str],
    *,
    stdin: str,
    cwd: Path | None = None,
    timeout: int = 60,
) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        input=stdin,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        encoding="utf-8",
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def git_text(args: list[str], *, cwd: Path) -> str:
    code, out, err = run_command(["git", *args], cwd=cwd)
    if code != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {err or out}")
    return out


def selected_files(root: Path, paths: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = root / raw
        if not path.exists():
            continue
        if path.is_file():
            files.append(path)
            continue
        for child in path.rglob("*"):
            if not child.is_file():
                continue
            rel_parts = child.relative_to(root).parts
            if any(part in EXCLUDE_DIRS for part in rel_parts):
                continue
            if child.suffix in EXCLUDE_SUFFIXES:
                continue
            files.append(child)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def fingerprint_tree(root: Path, paths: tuple[str, ...] = DEFAULT_RUNTIME_PATHS) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    missing = [raw for raw in paths if not (root / raw).exists()]
    for path in selected_files(root, paths):
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).hexdigest().encode("ascii"))
        digest.update(b"\0")
        count += 1
    return {
        "sha256": digest.hexdigest(),
        "file_count": count,
        "paths": list(paths),
        "missing": missing,
    }


def local_snapshot(root: Path, *, remote: str, branch: str, paths: tuple[str, ...]) -> dict[str, Any]:
    return {
        "kind": "local",
        "path": str(root),
        "head": git_text(["rev-parse", "HEAD"], cwd=root),
        "origin": git_text(["rev-parse", f"{remote}/{branch}"], cwd=root),
        "status": git_text(["status", "--short"], cwd=root),
        "fingerprint": fingerprint_tree(root, paths),
    }


def local_container_fingerprint(*, container: str, container_root: str, paths: tuple[str, ...]) -> dict[str, Any]:
    container_code = CONTAINER_FINGERPRINT_CODE % {
        "container_root": container_root,
        "paths_json": json.dumps(list(paths)),
    }
    code, out, err = run_command(["docker", "exec", container, "python", "-c", container_code], timeout=120)
    if code != 0:
        raise RuntimeError(f"container fingerprint failed: {err or out}")
    return json.loads(out)


def local_container_status(container: str) -> dict[str, Any]:
    code, out, err = run_command(["docker", "inspect", container], timeout=30)
    if code != 0:
        raise RuntimeError(f"docker inspect failed: {err or out}")
    data = json.loads(out)[0]
    return {
        "name": data.get("Name", "").lstrip("/"),
        "image_id": data.get("Image", ""),
        "image_name": data.get("Config", {}).get("Image", ""),
        "status": data.get("State", {}).get("Status", ""),
        "health": data.get("State", {}).get("Health", {}).get("Status", ""),
        "restart_count": data.get("RestartCount", 0),
        "compose_project": data.get("Config", {}).get("Labels", {}).get("com.docker.compose.project", ""),
        "compose_service": data.get("Config", {}).get("Labels", {}).get("com.docker.compose.service", ""),
    }


def self_snapshot(
    root: Path,
    *,
    remote: str,
    branch: str,
    container: str,
    container_root: str,
    paths: tuple[str, ...],
) -> dict[str, Any]:
    snapshot = local_snapshot(root, remote=remote, branch=branch, paths=paths)
    snapshot["kind"] = "self"
    snapshot["container"] = local_container_status(container)
    snapshot["container_fingerprint"] = local_container_fingerprint(
        container=container,
        container_root=container_root,
        paths=paths,
    )
    return snapshot


CONTAINER_FINGERPRINT_CODE = r"""
import hashlib, json
from pathlib import Path

ROOT = Path(%(container_root)r)
PATHS = %(paths_json)s
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git", "storage"}
EXCLUDE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".md",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
}

def selected_files(root, paths):
    files = []
    for raw in paths:
        path = root / raw
        if not path.exists():
            continue
        if path.is_file():
            files.append(path)
            continue
        for child in path.rglob("*"):
            if not child.is_file():
                continue
            rel_parts = child.relative_to(root).parts
            if any(part in EXCLUDE_DIRS for part in rel_parts):
                continue
            if child.suffix in EXCLUDE_SUFFIXES:
                continue
            files.append(child)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())

digest = hashlib.sha256()
count = 0
missing = [raw for raw in PATHS if not (ROOT / raw).exists()]
for path in selected_files(ROOT, PATHS):
    rel = path.relative_to(ROOT).as_posix()
    data = path.read_bytes()
    digest.update(rel.encode("utf-8"))
    digest.update(b"\0")
    digest.update(hashlib.sha256(data).hexdigest().encode("ascii"))
    digest.update(b"\0")
    count += 1
print(json.dumps({
    "sha256": digest.hexdigest(),
    "file_count": count,
    "paths": PATHS,
    "missing": missing,
}, sort_keys=True))
"""


REMOTE_SNAPSHOT_CODE = r"""
import hashlib, json, subprocess
from pathlib import Path

REMOTE_PATH = Path(%(remote_path)r)
REMOTE = %(remote)r
BRANCH = %(branch)r
CONTAINER = %(container)r
CONTAINER_CODE = %(container_code)r
PATHS = %(paths_json)s
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git", "storage"}
EXCLUDE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".md",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
}

def run(args, cwd=None, timeout=60):
    p = subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=timeout)
    return {"code": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}

def must(args, cwd=None, timeout=60):
    result = run(args, cwd=cwd, timeout=timeout)
    if result["code"] != 0:
        raise RuntimeError("%%s failed: %%s" %% (" ".join(args), result["stderr"] or result["stdout"]))
    return result["stdout"]

def selected_files(root, paths):
    files = []
    for raw in paths:
        path = root / raw
        if not path.exists():
            continue
        if path.is_file():
            files.append(path)
            continue
        for child in path.rglob("*"):
            if not child.is_file():
                continue
            rel_parts = child.relative_to(root).parts
            if any(part in EXCLUDE_DIRS for part in rel_parts):
                continue
            if child.suffix in EXCLUDE_SUFFIXES:
                continue
            files.append(child)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())

def fingerprint_tree(root, paths):
    digest = hashlib.sha256()
    count = 0
    missing = [raw for raw in paths if not (root / raw).exists()]
    for path in selected_files(root, paths):
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).hexdigest().encode("ascii"))
        digest.update(b"\0")
        count += 1
    return {"sha256": digest.hexdigest(), "file_count": count, "paths": PATHS, "missing": missing}

inspect_raw = must(["docker", "inspect", CONTAINER], timeout=30)
inspect_data = json.loads(inspect_raw)[0]
container_status = {
    "name": inspect_data.get("Name", "").lstrip("/"),
    "image_id": inspect_data.get("Image", ""),
    "image_name": inspect_data.get("Config", {}).get("Image", ""),
    "status": inspect_data.get("State", {}).get("Status", ""),
    "health": inspect_data.get("State", {}).get("Health", {}).get("Status", ""),
    "restart_count": inspect_data.get("RestartCount", 0),
    "compose_project": inspect_data.get("Config", {}).get("Labels", {}).get("com.docker.compose.project", ""),
    "compose_service": inspect_data.get("Config", {}).get("Labels", {}).get("com.docker.compose.service", ""),
}
container_fp_raw = must(["docker", "exec", CONTAINER, "python", "-c", CONTAINER_CODE], timeout=120)

payload = {
    "kind": "server",
    "path": str(REMOTE_PATH),
    "head": must(["git", "rev-parse", "HEAD"], cwd=REMOTE_PATH),
    "origin": must(["git", "rev-parse", "%%s/%%s" %% (REMOTE, BRANCH)], cwd=REMOTE_PATH),
    "status": must(["git", "status", "--short"], cwd=REMOTE_PATH),
    "fingerprint": fingerprint_tree(REMOTE_PATH, PATHS),
    "container": container_status,
    "container_fingerprint": json.loads(container_fp_raw),
}
print(json.dumps(payload, sort_keys=True))
"""


def remote_snapshot(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수/CLI 인자 보존)
    *,
    server: str,
    remote_path: str,
    container: str,
    remote: str,
    branch: str,
    container_root: str,
    paths: tuple[str, ...],
) -> dict[str, Any]:
    container_code = CONTAINER_FINGERPRINT_CODE % {
        "container_root": container_root,
        "paths_json": json.dumps(list(paths)),
    }
    remote_code = REMOTE_SNAPSHOT_CODE % {
        "remote_path": remote_path,
        "remote": remote,
        "branch": branch,
        "container": container,
        "container_code": container_code,
        "paths_json": json.dumps(list(paths)),
    }
    code, out, err = run_command_stdin(["ssh", server, "python3", "-"], stdin=remote_code, timeout=180)
    if code != 0:
        raise RuntimeError(f"remote snapshot failed: {err or out}")
    return json.loads(out)


def evaluate(local: dict[str, Any], server: dict[str, Any]) -> dict[str, Any]:
    checks = [
        {
            "id": "local_worktree_clean",
            "ok": local.get("status", "") == "",
            "detail": "local git status --short must be empty",
        },
        {
            "id": "server_worktree_clean",
            "ok": server.get("status", "") == "",
            "detail": "server git status --short must be empty",
        },
        {
            "id": "local_head_matches_origin",
            "ok": local.get("head") == local.get("origin"),
            "detail": "local HEAD must equal origin branch",
        },
        {
            "id": "server_head_matches_origin",
            "ok": server.get("head") == server.get("origin"),
            "detail": "server HEAD must equal origin branch",
        },
        {
            "id": "local_head_matches_server_head",
            "ok": local.get("head") == server.get("head"),
            "detail": "local HEAD must equal server HEAD",
        },
        {
            "id": "container_running_healthy",
            "ok": server.get("container", {}).get("status") == "running"
            and server.get("container", {}).get("health") in {"", "healthy"},
            "detail": "container must be running and healthy when a healthcheck exists",
        },
        {
            "id": "server_runtime_matches_container_runtime",
            "ok": server.get("fingerprint", {}).get("sha256") == server.get("container_fingerprint", {}).get("sha256"),
            "detail": "server runtime source fingerprint must equal container source fingerprint",
        },
        {
            "id": "local_runtime_matches_container_runtime",
            "ok": local.get("fingerprint", {}).get("sha256") == server.get("container_fingerprint", {}).get("sha256"),
            "detail": "local runtime source fingerprint must equal container source fingerprint",
        },
        {
            "id": "container_runtime_paths_present",
            "ok": server.get("container_fingerprint", {}).get("missing") == [],
            "detail": "all required runtime paths must exist inside the container",
        },
    ]
    failed = [check for check in checks if not check["ok"]]
    return {
        "status": "ok" if not failed else "drift_detected",
        "ok": not failed,
        "checks": checks,
        "failed": failed,
    }


def render_text(local: dict[str, Any], server: dict[str, Any], verdict: dict[str, Any]) -> str:
    lines = [
        "Runtime drift verification",
        f"status: {verdict['status']}",
        f"local_head: {local.get('head', '')[:12]}",
        f"local_origin: {local.get('origin', '')[:12]}",
        f"server_head: {server.get('head', '')[:12]}",
        f"server_origin: {server.get('origin', '')[:12]}",
        f"container: {server.get('container', {}).get('name', '')}",
        f"container_status: {server.get('container', {}).get('status', '')}",
        f"container_health: {server.get('container', {}).get('health', '') or 'none'}",
        f"runtime_fingerprint_local: {local.get('fingerprint', {}).get('sha256', '')[:16]}",
        f"runtime_fingerprint_server: {server.get('fingerprint', {}).get('sha256', '')[:16]}",
        f"runtime_fingerprint_container: {server.get('container_fingerprint', {}).get('sha256', '')[:16]}",
        f"runtime_file_count_local: {local.get('fingerprint', {}).get('file_count', 0)}",
        f"runtime_file_count_server: {server.get('fingerprint', {}).get('file_count', 0)}",
        f"runtime_file_count_container: {server.get('container_fingerprint', {}).get('file_count', 0)}",
        "",
        "checks:",
    ]
    for check in verdict["checks"]:
        marker = "PASS" if check["ok"] else "FAIL"
        lines.append(f"- {marker} {check['id']}: {check['detail']}")
    if local.get("status"):
        lines.extend(["", "local_dirty_files:", local["status"]])
    if server.get("status"):
        lines.extend(["", "server_dirty_files:", server["status"]])
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify local/server/container runtime drift.")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--remote-path", default=DEFAULT_REMOTE_PATH)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--container-root", default=DEFAULT_CONTAINER_ROOT)
    parser.add_argument("--path", action="append", dest="paths", default=[])
    parser.add_argument("--self", action="store_true", help="Check the current host repo against its local container.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    paths = tuple(args.paths) if args.paths else DEFAULT_RUNTIME_PATHS
    local = local_snapshot(ROOT, remote=args.remote, branch=args.branch, paths=paths)
    if args.self:
        server = self_snapshot(
            ROOT,
            remote=args.remote,
            branch=args.branch,
            container=args.container,
            container_root=args.container_root,
            paths=paths,
        )
    else:
        server = remote_snapshot(
            server=args.server,
            remote_path=args.remote_path,
            container=args.container,
            remote=args.remote,
            branch=args.branch,
            container_root=args.container_root,
            paths=paths,
        )
    verdict = evaluate(local, server)
    payload = {"local": local, "server": server, "verdict": verdict}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(local, server, verdict))
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
