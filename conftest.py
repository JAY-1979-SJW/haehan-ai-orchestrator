"""Pytest runtime defaults for local and deployment gates."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.runtime_temp import usable_temp_base


def _pytest_base(kind: str = "pytest_runtime") -> Path:
    return usable_temp_base(kind, "HAEHAN_PYTEST_TEMP")


def pytest_configure(config):
    """Force Python tempfile users under a verified runtime temp base."""
    base = _pytest_base()
    for key in ("TMP", "TEMP", "TMPDIR"):
        os.environ[key] = str(base)
    tempfile.tempdir = str(base)


@pytest.fixture
def tmp_path(request) -> Path:
    """Replacement tmp_path that avoids pytest basetemp cleanup on Windows."""
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in request.node.name)[:80]
    path = _pytest_base("pytest_tmp_path") / f"{safe_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
