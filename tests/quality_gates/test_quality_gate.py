from tools.quality import quality_gate


def _cfg():
    return {
        "active_code_prefixes": ["scripts/", "ai_orchestrator/"],
        "runtime_prefixes": ["data/", "tmp/"],
        "doc_prefixes": ["docs/", "README", "CLAUDE.md"],
        "test_prefixes": ["tests/"],
        "schema_prefixes": ["ai_orchestrator/"],
        "schema_name_tokens": ["schema", "model"],
        "destructive_sql_tokens": ["drop table", "drop column"],
        "deploy_paths": ["docker/", "Dockerfile", "docker-compose.yml"],
        "deploy_name_tokens": ["deploy", "docker", "compose", "Dockerfile"],
        "deploy_dry_run_evidence_path": "data/logs/deploy_dry_run_latest.json",
        "deploy_dry_run_required": True,
        "existing_code_change_requires_flag": True,
        "existing_code_change_severity": "error",
        "code_change_requires_test_or_doc": True,
        "schema_change_requires_doc_and_test": True,
    }


def test_code_change_without_doc_or_test_warns():
    files = [quality_gate.ChangedFile("scripts/eum/router.py", "M")]

    issues = quality_gate.evaluate_changes(files, _cfg(), allow_existing_code_change=True)

    assert any(issue.code == "CODE_WITHOUT_TEST_OR_DOC" for issue in issues)


def test_existing_code_change_errors_without_flag():
    files = [quality_gate.ChangedFile("scripts/eum/router.py", "M")]

    issues = quality_gate.evaluate_changes(files, _cfg())

    issue = next(issue for issue in issues if issue.code == "EXISTING_CODE_MODIFIED")
    assert issue.severity == "error"


def test_code_change_with_test_passes_doc_test_rule():
    files = [
        quality_gate.ChangedFile("scripts/eum/router.py", "M"),
        quality_gate.ChangedFile("tests/eum/test_eum_router_work.py", "M"),
    ]

    issues = quality_gate.evaluate_changes(files, _cfg(), allow_existing_code_change=True)

    assert not any(issue.code == "CODE_WITHOUT_TEST_OR_DOC" for issue in issues)


def test_schema_change_requires_doc_and_test():
    files = [quality_gate.ChangedFile("ai_orchestrator/server/task_queue_schema.py", "M")]

    issues = quality_gate.evaluate_changes(files, _cfg(), allow_existing_code_change=True)

    assert any(issue.code == "SCHEMA_CHANGE_NEEDS_DOC_AND_TEST" for issue in issues)


def test_schema_change_with_doc_and_test_passes():
    files = [
        quality_gate.ChangedFile("ai_orchestrator/server/task_queue_schema.py", "M"),
        quality_gate.ChangedFile("docs/design/schema_change.md", "A"),
        quality_gate.ChangedFile("tests/test_schema_change.py", "A"),
    ]

    issues = quality_gate.evaluate_changes(files, _cfg(), allow_existing_code_change=True)

    assert not any(issue.code == "SCHEMA_CHANGE_NEEDS_DOC_AND_TEST" for issue in issues)


def test_deploy_change_requires_dry_run(monkeypatch):
    files = [quality_gate.ChangedFile("docker/docker-compose.dev.yml", "M")]
    monkeypatch.setattr(quality_gate, "_deploy_dry_run_ok", lambda config, deploy_paths: False)

    issues = quality_gate.evaluate_changes(files, _cfg(), allow_existing_code_change=True)

    issue = next(issue for issue in issues if issue.code == "DEPLOY_CHANGE_REQUIRES_DRY_RUN")
    assert issue.severity == "error"


def test_deploy_change_passes_with_dry_run(monkeypatch):
    files = [quality_gate.ChangedFile("docker/docker-compose.dev.yml", "M")]
    monkeypatch.setattr(quality_gate, "_deploy_dry_run_ok", lambda config, deploy_paths: True)

    issues = quality_gate.evaluate_changes(files, _cfg(), allow_existing_code_change=True)

    assert not any(issue.code == "DEPLOY_CHANGE_REQUIRES_DRY_RUN" for issue in issues)
