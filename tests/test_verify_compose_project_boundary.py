from scripts.ops import verify_compose_project_boundary as boundary


def base_config():
    return {
        "name": boundary.PROJECT,
        "services": {
            name: {
                "container_name": boundary.EXPECTED_CONTAINERS[name],
                "image": boundary.EXPECTED_IMAGES[name],
                "networks": {network: None for network in boundary.ALLOWED_SERVICE_NETWORKS[name]},
                "ports": [],
                "volumes": [],
            }
            for name in boundary.EXPECTED_SERVICES
        },
        "networks": {
            "default": {"name": "haehan-ai-orchestrator_default"},
            "app_web": {"name": "app_web", "external": True},
        },
        "volumes": {
            "api_storage": {"name": "haehan-ai-orchestrator-api-storage"},
        },
    }


def test_compose_project_boundary_passes_for_expected_project():
    config = base_config()
    config["services"]["ai-orchestrator-api"]["ports"] = [
        {"host_ip": "127.0.0.1", "published": "8400", "target": 8400, "protocol": "tcp"}
    ]
    config["services"]["ai-orchestrator-api"]["volumes"] = [
        {"type": "bind", "target": "/app/logs"},
        {"type": "bind", "target": "/run/secrets/api", "read_only": True},
        {"type": "volume", "target": "/app/ai_orchestrator/storage"},
    ]
    config["services"]["browser-worker"]["volumes"] = [
        {"type": "bind", "target": "/dev/shm"},
    ]

    payload = boundary.evaluate(config, sorted(boundary.EXPECTED_CONTAINERS.values()))

    assert payload["ok"] is True
    assert payload["status"] == "ok"


def test_compose_project_boundary_fails_for_unexpected_service():
    config = base_config()
    config["services"]["debug-shell"] = {"container_name": "debug-shell"}

    payload = boundary.evaluate(config, sorted(boundary.EXPECTED_CONTAINERS.values()))

    assert payload["ok"] is False
    assert "compose_services_mismatch" in payload["failed_check_ids"]


def test_compose_project_boundary_fails_for_public_api_port():
    config = base_config()
    config["services"]["ai-orchestrator-api"]["ports"] = [
        {"host_ip": "0.0.0.0", "published": "8400", "target": 8400, "protocol": "tcp"}
    ]

    payload = boundary.evaluate(config, sorted(boundary.EXPECTED_CONTAINERS.values()))

    assert payload["ok"] is False
    assert "ai-orchestrator-api:published_ports_mismatch" in payload["failed_check_ids"]


def test_compose_project_boundary_fails_for_unexpected_running_project_container():
    payload = boundary.evaluate(base_config(), ["haehan-ai-orchestrator-api", "debug-shell"])

    assert payload["ok"] is False
    assert "project_running_containers_mismatch" in payload["failed_check_ids"]
