"""Image upload boundary for SmartStore registration."""
from __future__ import annotations

from pathlib import Path

from scripts.smartstore.draft_fill import create_test_image, upload_first_product_image


def prepare_test_image(path: str | Path | None = None, *, label: str = "SMARTSTORE TEST") -> Path:
    return create_test_image(path, label=label)


def upload_representative_image(target_id: str, *, port: int, image_path: str | Path) -> dict:
    """Upload a representative image as a prepare-stage action."""
    return upload_first_product_image(target_id, port=port, image_path=image_path)
