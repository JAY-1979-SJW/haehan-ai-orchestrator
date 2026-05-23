"""Security and validation utilities for file-map-executor."""

from pathlib import Path
from typing import Tuple

TMP_ROOT = Path("/tmp").resolve()


def validate_target_path(base_target_dir: str) -> Tuple[bool, str]:
    """Validate that target directory is in /tmp (smoke mode).

    Args:
        base_target_dir: Target directory path to validate

    Returns:
        (is_valid, error_message)
    """
    if not base_target_dir:
        return False, "base_target_dir is required"

    try:
        path = Path(base_target_dir).resolve()
        if path != TMP_ROOT and TMP_ROOT not in path.parents:
            return False, f"base_target_dir must be inside /tmp (smoke mode only): {base_target_dir}"
        if path.exists() and not path.is_dir():
            return False, f"base_target_dir must be a directory: {base_target_dir}"
    except Exception as e:
        return False, f"Invalid path: {str(e)}"

    return True, ""


def validate_dry_run(dry_run: bool) -> Tuple[bool, str]:
    """Validate dry_run mode (true only in skeleton).

    Args:
        dry_run: dry_run flag from request

    Returns:
        (is_valid, error_message)
    """
    if not dry_run:
        return False, "dry_run=false is not supported in this skeleton. dry_run must be true."

    return True, ""
