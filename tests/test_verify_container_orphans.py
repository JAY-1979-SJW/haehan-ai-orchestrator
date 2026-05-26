from scripts.ops import verify_container_orphans as orphans


def test_container_orphan_evaluate_passes_for_tracked_files_only():
    payload = orphans.evaluate(
        tracked={"ai_orchestrator/router.py", "scripts/youtube/oauth.py"},
        container={"ai_orchestrator/router.py", "scripts/youtube/oauth.py"},
    )

    assert payload["ok"] is True
    assert payload["untracked_in_container_count"] == 0


def test_container_orphan_evaluate_fails_for_untracked_code_file():
    payload = orphans.evaluate(
        tracked={"ai_orchestrator/router.py"},
        container={"ai_orchestrator/router.py", "docker-compose.override.yml"},
    )

    assert payload["ok"] is False
    assert payload["status"] == "container_orphans_detected"
    assert payload["untracked_in_container"] == ["docker-compose.override.yml"]


def test_container_orphan_evaluate_ignores_runtime_and_cache_files():
    payload = orphans.evaluate(
        tracked={"ai_orchestrator/router.py"},
        container={
            "ai_orchestrator/router.py",
            "ai_orchestrator/storage/secrets/token.json",
            "admin-web/node_modules/lib/index.js",
            "data/runtime/latest.json",
        },
    )

    assert payload["ok"] is True
    assert payload["untracked_in_container_count"] == 0
