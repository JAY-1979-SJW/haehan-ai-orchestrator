from scripts.ops import verify_docker_context_policy as policy


def test_docker_context_policy_passes_with_required_patterns():
    payload = policy.evaluate(list(policy.REQUIRED_PATTERNS))

    assert payload["ok"] is True
    assert payload["status"] == "ok"
    assert payload["missing_required_patterns"] == []
    assert payload["forbidden_unignore_patterns"] == []


def test_docker_context_policy_fails_when_required_pattern_missing():
    lines = sorted(policy.REQUIRED_PATTERNS - {"docker-compose.override.yml"})

    payload = policy.evaluate(lines)

    assert payload["ok"] is False
    assert payload["status"] == "docker_context_policy_failed"
    assert "dockerignore_required_patterns_missing" in payload["failed_check_ids"]
    assert payload["missing_required_patterns"] == ["docker-compose.override.yml"]


def test_docker_context_policy_fails_for_forbidden_unignore():
    payload = policy.evaluate(list(policy.REQUIRED_PATTERNS) + ["!secrets/"])

    assert payload["ok"] is False
    assert "dockerignore_forbidden_unignore_present" in payload["failed_check_ids"]
    assert payload["forbidden_unignore_patterns"] == ["!secrets/"]
