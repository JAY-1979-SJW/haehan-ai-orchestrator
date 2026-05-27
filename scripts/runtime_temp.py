"""Runtime temporary directory selection with create/delete verification."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


def _candidate_paths(kind: str, env_var: str | None = None) -> list[Path]:
    candidates: list[Path] = []
    if env_var and os.environ.get(env_var):
        candidates.append(Path(os.environ[env_var]))
    if os.environ.get("HAEHAN_RUNTIME_TEMP"):
        candidates.append(Path(os.environ["HAEHAN_RUNTIME_TEMP"]) / kind)
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"]) / "HaehanAI" / "runtime" / kind)
    candidates.append(Path.home() / ".haehan-ai" / "runtime" / kind)
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    candidates.append(codex_home / "memories" / "haehan-ai-runtime" / kind)
    candidates.append(ROOT / ".pytest-tmp" / kind)
    return candidates


def _can_create_list_remove(base: Path) -> bool:
    probe = base / f".probe_{uuid4().hex}"
    try:
        probe.mkdir(parents=True, exist_ok=False)
        list(probe.iterdir())
        probe.rmdir()
        return True
    except Exception:
        return False


def usable_temp_base(kind: str, env_var: str | None = None) -> Path:
    """Return the first temp base that supports create, list, and remove."""
    for candidate in _candidate_paths(kind, env_var):
        if _can_create_list_remove(candidate):
            return candidate
    raise RuntimeError(f"no usable runtime temp directory for {kind}")
