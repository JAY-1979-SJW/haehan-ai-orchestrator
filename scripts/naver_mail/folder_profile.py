"""folder_profile_snapshot — 사용자별 폴더 구조 스냅샷.

저장 위치: data/inspection/naver_mail_folder_discovery/
민감정보: 계정 이메일 원문 저장 금지. account_hint_masked 만.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import folder_discovery as fd
from . import folder_policy as fp

KST = timezone(timedelta(hours=9))
SCHEMA_VERSION = "1.0"


def _mask_account_hint(raw: str) -> str:
    if not raw:
        return ""
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"acct:{h}"


@dataclass
class FolderProfileSnapshot:
    schema_version: str
    run_id: str
    account_hint_masked: str
    discovered_at_iso: str
    lnb_total_unread: int
    folders: list[dict]
    groups: dict   # {group_name: [folder_name, ...]}
    unknown_folders: list[str]
    policy_excluded_folders: list[dict]   # [{name, reason}]
    collectable_folders: list[str]
    warnings: list[str] = field(default_factory=list)
    verdict: str = ""


def build_snapshot(folders: list[fd.FolderInfo],
                   *, account_raw: str = "",
                   lnb_total_unread: int = -1,
                   warnings: list[str] | None = None
                   ) -> FolderProfileSnapshot:
    groups: dict[str, list[str]] = {}
    unknown: list[str] = []
    excluded: list[dict] = []
    collectable: list[str] = []

    for f in folders:
        groups.setdefault(f.parent_group or "lnb_top", []).append(f.name)
        if f.kind == fp.KIND_UNKNOWN:
            unknown.append(f.name)
        if f.is_collectable:
            collectable.append(f.name)
        else:
            excluded.append({
                "name": f.name, "kind": f.kind,
                "reason": f.default_policy_state or "unspecified",
                "unread_count": f.unread_count,
                "adapter_selected": f.adapter_selected,
            })

    return FolderProfileSnapshot(
        schema_version=SCHEMA_VERSION,
        run_id=uuid.uuid4().hex[:12],
        account_hint_masked=_mask_account_hint(account_raw),
        discovered_at_iso=datetime.now(KST).replace(microsecond=0).isoformat(),
        lnb_total_unread=lnb_total_unread,
        folders=[asdict(f) for f in folders],
        groups=groups,
        unknown_folders=unknown,
        policy_excluded_folders=excluded,
        collectable_folders=collectable,
        warnings=warnings or [],
    )


def write_snapshot(snap: FolderProfileSnapshot, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "folder_profile_snapshot.json"
    path.write_text(json.dumps(asdict(snap), ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


# JSON 필수 필드 검증
REQUIRED_TOP_FIELDS = (
    "schema_version", "run_id", "account_hint_masked", "discovered_at_iso",
    "lnb_total_unread", "folders", "groups", "unknown_folders",
    "policy_excluded_folders", "collectable_folders", "warnings", "verdict",
)


def validate_schema(d: dict) -> list[str]:
    return [k for k in REQUIRED_TOP_FIELDS if k not in d]
