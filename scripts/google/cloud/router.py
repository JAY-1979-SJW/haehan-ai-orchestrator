"""Router for Google Cloud catalog-only wrappers."""
from __future__ import annotations

from . import (
    api_credentials,
    bigquery,
    billing,
    compute,
    console,
    gke,
    iam,
    logging,
    maps_platform,
    monitoring,
    pubsub,
    run,
    secret_manager,
    sql,
    storage,
)
from .registry import cloud_summary

_RUNNERS = {
    "console": console.run,
    "cloud_console": console.run,
    "maps_platform": maps_platform.run,
    "api_credentials": api_credentials.run,
    "cloud_apis_credentials": api_credentials.run,
    "iam": iam.run,
    "cloud_iam": iam.run,
    "billing": billing.run,
    "cloud_billing": billing.run,
    "run": run.run,
    "cloud_run": run.run,
    "compute": compute.run,
    "compute_engine": compute.run,
    "storage": storage.run,
    "cloud_storage": storage.run,
    "bigquery": bigquery.run,
    "gke": gke.run,
    "sql": sql.run,
    "cloud_sql": sql.run,
    "pubsub": pubsub.run,
    "secret_manager": secret_manager.run,
    "logging": logging.run,
    "cloud_logging": logging.run,
    "monitoring": monitoring.run,
    "cloud_monitoring": monitoring.run,
}


def run_cloud(service: str, task: str = "open", args: list[str] | None = None) -> dict:
    normalized = (service or "").strip().lower()
    if normalized in {"catalog", "summary", "registry"}:
        return cloud_summary()
    runner = _RUNNERS.get(normalized)
    if runner is None:
        return {"ok": False, "reason": "unknown_cloud_service", "service": service}
    return runner(task or "open", args or [])

