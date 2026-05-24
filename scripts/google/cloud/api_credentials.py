"""Google Cloud API credentials catalog-only wrapper."""
from __future__ import annotations

from ._catalog_only import catalog_only_result


def run(task: str = "open", args: list[str] | None = None) -> dict:
    return catalog_only_result("api_credentials", "cloud_apis_credentials", task)

