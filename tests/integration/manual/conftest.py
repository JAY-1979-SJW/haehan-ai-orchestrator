"""Manual/integration tests — excluded from automated pytest collection.

These tests require a live browser session, Gmail login, or external
network access and must be run explicitly by a developer, not by CI.
"""
collect_ignore_glob = ["*.py"]
