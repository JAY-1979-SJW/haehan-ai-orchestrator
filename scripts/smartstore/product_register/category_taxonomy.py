"""SmartStore category taxonomy cache.

This module is intentionally offline-first. Live category discovery can fill the
same schema later, while registration code can already resolve products against
a stable cache.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
LATEST_CATEGORY_TAXONOMY_PATH = ROOT / "data" / "smartstore_category_taxonomy_latest.json"


@dataclass(frozen=True)
class CategoryNode:
    category_id: str
    name: str
    whole_category_name: str
    whole_category_id: str = ""
    parent_id: str = ""
    level: int = 0
    last_level: bool = True
    keywords: list[str] = field(default_factory=list)
    catalog_followup_required: bool = False
    kc_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_CATEGORY_NODES = [
    CategoryNode(
        category_id="50003340",
        parent_id="50001119",
        name="인테리어조명",
        whole_category_id="50000004>50000108>50001119>50003340",
        whole_category_name="가구/인테리어>인테리어소품>조명>인테리어조명",
        level=4,
        keywords=["조명", "인테리어조명", "라인조명", "간접조명", "무드등", "LED", "T3"],
        catalog_followup_required=True,
        kc_required=True,
    ),
    CategoryNode(
        category_id="50003645",
        name="LED모듈",
        whole_category_name="가구/인테리어>인테리어소품>조명>LED모듈",
        level=4,
        keywords=["LED모듈", "LED", "T5", "T3", "라인조명", "간접조명", "슬림조명"],
        catalog_followup_required=True,
        kc_required=True,
    ),
    CategoryNode(
        category_id="50001119",
        name="조명",
        whole_category_name="가구/인테리어>인테리어소품>조명",
        level=3,
        last_level=False,
        keywords=["조명", "lamp", "lighting"],
        catalog_followup_required=True,
        kc_required=True,
    ),
]


def build_default_taxonomy() -> dict[str, Any]:
    return {
        "schema": "smartstore_category_taxonomy.v1",
        "source": "offline_seed",
        "nodes": [node.to_dict() for node in DEFAULT_CATEGORY_NODES],
        "notes": [
            "Live discovery may replace or extend this cache.",
            "Only last_level categories should be auto-selected.",
            "Lighting categories require KC/catalog follow-up gates.",
        ],
    }


def save_taxonomy(payload: dict[str, Any] | None = None, output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_CATEGORY_TAXONOMY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload or build_default_taxonomy(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_taxonomy(path: str | Path | None = None) -> dict[str, Any]:
    source = Path(path) if path else LATEST_CATEGORY_TAXONOMY_PATH
    if not source.exists():
        payload = build_default_taxonomy()
        save_taxonomy(payload, source)
        return payload
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("SmartStore category taxonomy must be a JSON object")
    return data
