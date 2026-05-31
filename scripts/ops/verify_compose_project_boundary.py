"""Verify Docker Compose project isolation boundaries.

This gate is intentionally project-scoped. The host may run many unrelated
Docker applications, but this project must only own the expected services,
containers, networks, volumes, and published ports.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROJECT = "haehan-ai-orchestrator"

EXPECTED_SERVICES = {
    "ai-orchestrator-api",
    "admin-web",
    "browser-worker",
    "file-map-executor",
}
EXPECTED_CONTAINERS = {
    "ai-orchestrator-api": "haehan-ai-orchestrator-api",
    "admin-web": "haehan-ai-orchestrator-admin-web",
    "browser-worker": "haehan-ai-orchestrator-browser-worker",
    "file-map-executor": "haehan-ai-orchestrator-file-map-executor",
}
EXPECTED_IMAGES = {
    "ai-orchestrator-api": "haehan-ai-orchestrator-api:local",
    "admin-web": "haehan-ai-orchestrator-admin-web:local",
    "browser-worker": "haehan-ai-orchestrator-browser-worker:local",
    "file-map-executor": "haehan-ai-orchestrator-file-map-executor:local",
}
EXPECTED_NETWORKS = {
    "default": {"name": "haehan-ai-orchestrator_default", "external": False},
    "app_web": {"name": "app_web", "external": True},
}
PRIVATE_NETWORK = "haehan-ai-orchestrator_default"
EXPECTED_VOLUMES = {
    "api_storage": "haehan-ai-orchestrator-api-storage",
}
EXPECTED_PUBLISHED_PORTS = {
    "ai-orchestrator-api": {("127.0.0.1", "8400", 8400, "tcp")},
    "admin-web": set(),
    "browser-worker": set(),
    "file-map-executor": set(),
}
ALLOWED_SERVICE_NETWORKS = {
    "ai-orchestrator-api": {"default", "app_web"},
    "admin-web": {"default", "app_web"},
    "browser-worker": {"default"},
    "file-map-executor": {"default", "app_web"},
}
ALLOWED_BIND_TARGETS = {
    "ai-orchestrator-api": {"/app/logs", "/run/secrets/api"},
    "browser-worker": {"/dev/shm"},
}
REQUIRED_READ_ONLY_BINDS = {
    "ai-orchestrator-api": {"/run/secrets/api"},
}


def run(args: list[str], *, timeout: int = 120, cwd: str | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=cwd or str(ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def compose_config(cwd: str | None = None) -> dict[str, Any]:
    code, out, err = run(["docker", "compose", "config", "--format", "json"], cwd=cwd)
    if code != 0:
        raise RuntimeError(f"docker compose config failed: {err[-500:]}")
    return json.loads(out)


def project_container_names(project: str = PROJECT) -> list[str]:
    code, out, err = run([
        "docker",
        "ps",
        "--filter",
        f"label=com.docker.compose.project={project}",
        "--format",
        "{{.Names}}",
    ])
    if code != 0:
        raise RuntimeError(f"docker ps failed: {err[-500:]}")
    return sorted(line.strip() for line in out.splitlines() if line.strip())


def network_container_names(network: str = PRIVATE_NETWORK) -> list[str]:
    code, out, err = run([
        "docker",
        "network",
        "inspect",
        network,
        "--format",
        "{{json .Containers}}",
    ])
    if code != 0:
        raise RuntimeError(f"docker network inspect failed: {err[-500:]}")
    containers = json.loads(out or "{}") or {}
    return sorted(item.get("Name", "") for item in containers.values() if item.get("Name"))


def published_ports(service: dict[str, Any]) -> set[tuple[str, str, int, str]]:
    ports = set()
    for port in service.get("ports", []) or []:
        ports.add((
            str(port.get("host_ip", "")),
            str(port.get("published", "")),
            int(port.get("target", 0)),
            str(port.get("protocol", "")),
        ))
    return ports


def service_networks(service: dict[str, Any]) -> set[str]:
    networks = service.get("networks", {}) or {}
    if isinstance(networks, dict):
        return set(networks)
    return set(networks)


def evaluate(
    config: dict[str, Any],
    running_containers: list[str],
    private_network_containers: list[str] | None = None,
) -> dict[str, Any]:
    failed: list[str] = []
    details: dict[str, Any] = {}

    if config.get("name") != PROJECT:
        failed.append("compose_project_name_mismatch")
        details["project_name"] = config.get("name")

    services = config.get("services", {}) or {}
    service_names = set(services)
    if service_names != EXPECTED_SERVICES:
        failed.append("compose_services_mismatch")
        details["expected_services"] = sorted(EXPECTED_SERVICES)
        details["actual_services"] = sorted(service_names)

    for name in sorted(EXPECTED_SERVICES & service_names):
        service = services[name]
        if service.get("container_name") != EXPECTED_CONTAINERS[name]:
            failed.append(f"{name}:container_name_mismatch")
        if service.get("image") != EXPECTED_IMAGES[name]:
            failed.append(f"{name}:image_mismatch")
        actual_networks = service_networks(service)
        if actual_networks != ALLOWED_SERVICE_NETWORKS[name]:
            failed.append(f"{name}:networks_mismatch")
            details[f"{name}_networks"] = sorted(actual_networks)
        actual_ports = published_ports(service)
        if actual_ports != EXPECTED_PUBLISHED_PORTS[name]:
            failed.append(f"{name}:published_ports_mismatch")
            details[f"{name}_published_ports"] = sorted(actual_ports)

        bind_targets = {
            item.get("target")
            for item in service.get("volumes", []) or []
            if item.get("type") == "bind"
        }
        unexpected_binds = sorted(bind_targets - ALLOWED_BIND_TARGETS.get(name, set()))
        if unexpected_binds:
            failed.append(f"{name}:unexpected_bind_mounts")
            details[f"{name}_unexpected_bind_targets"] = unexpected_binds
        readonly_targets = {
            item.get("target")
            for item in service.get("volumes", []) or []
            if item.get("type") == "bind" and item.get("read_only") is True
        }
        missing_ro = sorted(REQUIRED_READ_ONLY_BINDS.get(name, set()) - readonly_targets)
        if missing_ro:
            failed.append(f"{name}:required_bind_not_readonly")
            details[f"{name}_required_readonly_missing"] = missing_ro

    networks = config.get("networks", {}) or {}
    actual_networks = {
        name: {"name": value.get("name"), "external": value.get("external", False) is True}
        for name, value in networks.items()
    }
    if actual_networks != EXPECTED_NETWORKS:
        failed.append("compose_networks_mismatch")
        details["actual_networks"] = actual_networks

    volumes = config.get("volumes", {}) or {}
    actual_volumes = {name: value.get("name") for name, value in volumes.items()}
    if actual_volumes != EXPECTED_VOLUMES:
        failed.append("compose_volumes_mismatch")
        details["actual_volumes"] = actual_volumes

    expected_running = sorted(EXPECTED_CONTAINERS.values())
    if sorted(running_containers) != expected_running:
        failed.append("project_running_containers_mismatch")
        details["expected_running_containers"] = expected_running
        details["actual_running_containers"] = sorted(running_containers)

    if private_network_containers is not None and sorted(private_network_containers) != expected_running:
        failed.append("private_network_containers_mismatch")
        details["private_network"] = PRIVATE_NETWORK
        details["expected_private_network_containers"] = expected_running
        details["actual_private_network_containers"] = sorted(private_network_containers)

    return {
        "schema_version": 1,
        "ok": not failed,
        "status": "ok" if not failed else "compose_project_boundary_failed",
        "project": PROJECT,
        "failed_check_ids": failed,
        "details": details,
        "secret_values_output": False,
    }


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        "Compose project boundary verification",
        f"status: {payload['status']}",
        f"project: {payload['project']}",
        f"failed_count: {len(payload['failed_check_ids'])}",
    ]
    for check_id in payload["failed_check_ids"]:
        lines.append(f"- {check_id}")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify compose project isolation boundaries.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--compose-dir", default=None, help="Directory containing docker-compose.yml (defaults to repo root).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    compose_dir = str(Path(args.compose_dir).resolve()) if args.compose_dir else None
    payload = evaluate(compose_config(cwd=compose_dir), project_container_names(), network_container_names())
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(payload))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
