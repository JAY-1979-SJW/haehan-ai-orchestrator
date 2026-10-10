import json
from pathlib import Path

from tools.runtime import verify_runtime_drift as drift


def _snapshot(*, head="a" * 40, status="", fingerprint="fp") -> dict:
    return {
        "head": head,
        "origin": head,
        "status": status,
        "fingerprint": {"sha256": fingerprint, "missing": [], "file_count": 1},
    }


def _server(*, head="a" * 40, status="", fingerprint="fp", container_fingerprint="fp") -> dict:
    snap = _snapshot(head=head, status=status, fingerprint=fingerprint)
    snap["container"] = {
        "name": "haehan-ai-orchestrator-api",
        "status": "running",
        "health": "healthy",
        "restart_count": 0,
    }
    snap["container_fingerprint"] = {
        "sha256": container_fingerprint,
        "missing": [],
        "file_count": 1,
    }
    return snap


def test_evaluate_passes_when_heads_and_fingerprints_match():
    verdict = drift.evaluate(_snapshot(), _server())

    assert verdict["ok"] is True
    assert verdict["status"] == "ok"
    assert verdict["failed"] == []


def test_evaluate_fails_dirty_local_and_container_fingerprint_drift():
    verdict = drift.evaluate(
        _snapshot(status=" M ai_orchestrator/routers/registry.py", fingerprint="local"),
        _server(fingerprint="server", container_fingerprint="container"),
    )

    failed_ids = {item["id"] for item in verdict["failed"]}
    assert verdict["ok"] is False
    assert "local_worktree_clean" in failed_ids
    assert "server_runtime_matches_container_runtime" in failed_ids
    assert "local_runtime_matches_container_runtime" in failed_ids


def test_fingerprint_tree_changes_when_runtime_file_changes(tmp_path: Path):
    package = tmp_path / "ai_orchestrator"
    package.mkdir()
    target = package / "router.py"
    target.write_text("A", encoding="utf-8")
    first = drift.fingerprint_tree(tmp_path, ("ai_orchestrator",))
    target.write_text("B", encoding="utf-8")
    second = drift.fingerprint_tree(tmp_path, ("ai_orchestrator",))

    assert first["sha256"] != second["sha256"]
    assert first["file_count"] == 1
    assert second["file_count"] == 1


def test_remote_snapshot_template_formats_without_ssh():
    container_code = drift.CONTAINER_FINGERPRINT_CODE % {
        "container_root": "/app",
        "paths_json": json.dumps(["ai_orchestrator"]),
    }
    remote_code = drift.REMOTE_SNAPSHOT_CODE % {
        "remote_path": "/srv/app",
        "remote": "origin",
        "branch": "master",
        "container": "api",
        "container_code": container_code,
        "paths_json": json.dumps(["ai_orchestrator"]),
    }

    assert "REMOTE_PATH = Path('/srv/app')" in remote_code
    assert "docker" in remote_code
    assert "container_fingerprint" in remote_code
