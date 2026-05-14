"""Naver service capability catalog for CLI routing and worktree indexing."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


DATA_DIR = Path("data")
LATEST_PATH = DATA_DIR / "naver_service_action_catalog_latest.json"


FEATURE_CATALOG: dict[str, dict[str, Any]] = {
    "session": {
        "commands": ["session-check", "login"],
        "read": ["session-check"],
        "prepare": [],
        "submit": [],
    },
    "mail": {
        "commands": ["mail inbox", "mail compose", "mail send"],
        "read": ["inbox"],
        "prepare": ["compose"],
        "submit": ["send"],
    },
    "content": {
        "commands": ["content explore", "content actions"],
        "read": ["explore", "actions"],
        "prepare": [],
        "submit": [],
    },
    "seo": {
        "commands": [
            "seo entrypoints", "seo plan", "seo assets", "seo ownership",
            "seo exposure", "seo submit-plan", "seo monitor", "seo full",
            "seo diagnose", "seo submit",
        ],
        "read": ["entrypoints", "plan", "assets", "exposure", "monitor", "diagnose", "full"],
        "prepare": ["ownership", "submit-plan", "searchadvisor prepare"],
        "submit": ["searchadvisor submit"],
    },
    "developers": {
        "commands": ["developers entrypoints", "developers plan"],
        "read": ["entrypoints", "plan"],
        "prepare": ["app registration prepare"],
        "submit": ["app register"],
    },
    "shopping": {
        "commands": ["shopping entrypoints", "shopping competitors"],
        "read": ["entrypoints", "competitors"],
        "prepare": [],
        "submit": [],
    },
    "excel": {
        "commands": ["excel report"],
        "read": ["report"],
        "prepare": ["report"],
        "submit": [],
    },
    "cafe": {
        "commands": ["cafe list", "cafe posts", "cafe read", "cafe write", "cafe publish"],
        "read": ["list", "posts", "read"],
        "prepare": ["write"],
        "submit": ["publish"],
    },
    "calendar": {
        "commands": ["calendar list", "calendar add"],
        "read": ["list"],
        "prepare": ["add"],
        "submit": ["add --save"],
    },
    "mybox": {
        "commands": ["mybox list", "mybox search", "mybox upload"],
        "read": ["list", "search"],
        "prepare": ["upload --dry-run"],
        "submit": ["upload --execute"],
    },
    "pay": {
        "commands": ["pay orders", "pay points"],
        "read": ["orders", "points"],
        "prepare": [],
        "submit": [],
    },
    "talk": {
        "commands": ["talk list", "talk send"],
        "read": ["list"],
        "prepare": ["send"],
        "submit": ["send --execute"],
    },
    "place": {
        "commands": ["place list", "place reviews"],
        "read": ["list", "reviews"],
        "prepare": [],
        "submit": [],
    },
    "smartstore": {
        "commands": ["smartstore actions", "smartstore product list", "smartstore submit"],
        "read": ["actions", "product list"],
        "prepare": ["prepare product"],
        "submit": ["submit product"],
    },
}


def build_catalog() -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "site": "naver",
        "approval_policy": {
            "read": "allowed after session and live-safety checks",
            "prepare": "may type or fill only; no external submit without approval",
            "submit": "requires explicit approval flags and confirmation text",
        },
        "features": FEATURE_CATALOG,
    }


def save_catalog(catalog: dict[str, Any] | None = None, output: str | Path | None = None) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(output) if output else LATEST_PATH
    path.write_text(json.dumps(catalog or build_catalog(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_catalog_summary(catalog: dict[str, Any], path: Path) -> None:
    print("Naver service action catalog")
    for name, feature in catalog["features"].items():
        read_count = len(feature.get("read", []))
        prepare_count = len(feature.get("prepare", []))
        submit_count = len(feature.get("submit", []))
        print(f"  {name}: read={read_count} prepare={prepare_count} submit={submit_count}")
    print(f"saved: {path}")
