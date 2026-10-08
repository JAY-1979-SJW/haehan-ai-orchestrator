"""기존 저장소 내부 데이터를 윈도우 표준 저장소로 복사 이전하는 엔진 (결함 #17, 기준서 §5).

설계: docs/specs/2026-10-01_windows_standard_storage.md

원칙
- **복사만 한다. 원본은 지우지 않는다.** (롤백 = 해석기 전환을 되돌리면 옛 위치로 돌아간다)
- 기본은 드라이런(`plan()`): 무엇을 얼마나 복사할지만 보고하고 아무것도 쓰지 않는다. 실제 복사(`execute()`)는 사용자 승인 뒤에만.
- 파일마다 크기·SHA-256 을 검증하고, 이미 같은 파일이 있으면 건너뛴다(중간에 끊겨도 이어서 — 멱등).
- sqlite DB 는 실행 중인 서버가 쓰고 있을 수 있어 파일 복사 대신 `Connection.backup()` 으로 일관된 스냅샷을 만든다.
- 브라우저 프로필·로그인 세션은 브라우저가 파일을 잡고 있으면 깨지므로, CDP 브라우저가 켜져 있으면 해당 항목을 건너뛰고 알린다.
- 이전 기록(`migration/migration.json`)에는 비밀 값과 사용자명이 든 절대경로를 남기지 않는다(상대 경로만).

표준 라이브러리만 사용한다(다른 프로젝트 모듈을 import 하지 않는다).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import shutil
import sqlite3
import time
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

REQUIRED = "required"  # 필수: 항상 복사
OPTIONAL = "optional"  # 선택: 용량이 크거나 재생성 가능 — 사용자가 선택
EXCLUDED = "excluded"  # 제외: 임시·재생성 가능 — 복사하지 않음

# 분류 규칙(위에서부터 처음 일치하는 것). 경로는 원본 루트 기준 상대 경로(/ 구분).
_EXCLUDE_PATTERNS = (
    "*/__pycache__/*",
    "__pycache__/*",
    "*.pyc",
    "*.lock",
    "*.tmp",
    "*_tmp/*",
    "cdp_chrome_tmp/*",
    "video_test/*",
    "*/Cache/*",
    "*/Code Cache/*",
    "*/GPUCache/*",
    "*/Crashpad/*",
    "*/ShaderCache/*",
    "*/Singleton*",
)
_REQUIRED_PATTERNS = (
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "sessions/*",
    "browser_sessions/*",
    "secrets/*",
    "*.jsonl",
    "*.json",
    ".env",
    ".fernet_key",
)
_OPTIONAL_TOP_DIRS = ("cdp_profile",)  # 로그인 유지용 브라우저 프로필(대용량)
_SQLITE_SUFFIXES = (".db", ".sqlite", ".sqlite3")
_SQLITE_SIDE_SUFFIXES = ("-wal", "-shm", "-journal")


@dataclass
class PlanItem:
    rel: str  # 원본 루트 기준 상대 경로
    dest_rel: str  # 대상 루트 기준 상대 경로
    size: int
    category: str
    kind: str = "file"  # file | sqlite


@dataclass
class MigrationSource:
    """이전 원본 한 곳. `dest_subdir` 은 데이터 루트 아래 대상 폴더(예: 'data', 'db')."""

    name: str
    root: Path
    dest_subdir: str
    # 최상위 항목 이름 → 대상 폴더를 바꾸고 싶을 때(예: cdp_profile → browser_profile/ai_chrome)
    remap: dict[str, str] = field(default_factory=dict)


@dataclass
class Plan:
    items: list[PlanItem] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def totals(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for item in self.items:
            bucket = out.setdefault(item.category, {"files": 0, "bytes": 0})
            bucket["files"] += 1
            bucket["bytes"] += item.size
        return out


def classify(rel: str) -> str:
    """상대 경로 → 필수/선택/제외."""
    rel = rel.replace("\\", "/")
    for pattern in _EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(rel, pattern):
            return EXCLUDED
    top = rel.split("/", 1)[0]
    if top in _OPTIONAL_TOP_DIRS:
        return OPTIONAL
    name = rel.rsplit("/", 1)[-1]
    for pattern in _REQUIRED_PATTERNS:
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern):
            return REQUIRED
    return OPTIONAL


def _walk_files(root: Path) -> Iterator[tuple[str, int]]:
    for path in root.rglob("*"):
        try:
            if path.is_file():
                yield path.relative_to(root).as_posix(), path.stat().st_size
        except OSError:
            continue


def _dest_rel(source: MigrationSource, rel: str) -> str:
    top, _, rest = rel.partition("/")
    if top in source.remap:
        return f"{source.remap[top]}/{rest}" if rest else source.remap[top]
    return f"{source.dest_subdir}/{rel}"


def _is_sqlite_side_file(rel: str) -> bool:
    return rel.endswith(_SQLITE_SIDE_SUFFIXES)


def plan(sources: Iterable[MigrationSource]) -> Plan:
    """드라이런: 파일을 읽지 않고(크기만) 무엇을 어디로 복사할지 계획만 만든다. 아무것도 쓰지 않는다."""
    result = Plan()
    for source in sources:
        if not source.root.exists():
            result.missing_sources.append(source.name)
            continue
        for rel, size in _walk_files(source.root):
            if _is_sqlite_side_file(rel):
                continue  # -wal/-shm 은 backup() 스냅샷에 반영되므로 별도 복사하지 않는다
            category = classify(rel)
            kind = "sqlite" if rel.endswith(_SQLITE_SUFFIXES) else "file"
            result.items.append(
                PlanItem(
                    rel=f"{source.name}:{rel}", dest_rel=_dest_rel(source, rel), size=size, category=category, kind=kind
                )
            )
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_sqlite(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_con = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    try:
        dst_con = sqlite3.connect(str(dst))
        try:
            src_con.backup(dst_con)
        finally:
            dst_con.close()
    finally:
        src_con.close()


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _sources_by_name(sources: Iterable[MigrationSource]) -> dict[str, MigrationSource]:
    return {s.name: s for s in sources}


def execute(
    sources: Iterable[MigrationSource],
    dest_root: Path,
    *,
    categories: tuple[str, ...] = (REQUIRED,),
    browser_running: bool = False,
) -> dict:
    """실제 복사. **사용자 승인 후에만 호출한다.** 원본은 건드리지 않는다. 결과 요약을 반환하고 이전 기록을 남긴다."""
    sources = list(sources)
    by_name = _sources_by_name(sources)
    migration_plan = plan(sources)
    copied = skipped_same = skipped_browser = failed = 0
    problems: list[str] = []
    record: list[dict] = []
    for item in migration_plan.items:
        if item.category not in categories:
            continue
        source_name, _, rel = item.rel.partition(":")
        src = by_name[source_name].root / rel
        dst = dest_root / item.dest_rel
        if browser_running and (
            rel.startswith(("cdp_profile/", "browser_sessions/", "sessions/")) or "browser_profile" in item.dest_rel
        ):
            skipped_browser += 1
            continue
        try:
            if (
                dst.exists()
                and item.kind == "file"
                and dst.stat().st_size == item.size
                and _sha256(dst) == _sha256(src)
            ):
                skipped_same += 1
                continue
            if item.kind == "sqlite":
                _copy_sqlite(src, dst)
            else:
                _copy_file(src, dst)
            if item.kind == "file" and _sha256(dst) != _sha256(src):
                raise OSError("복사 후 해시가 일치하지 않음")
            copied += 1
            record.append({"from": item.rel, "to": item.dest_rel, "size": item.size, "category": item.category})
        except (OSError, sqlite3.Error) as exc:
            failed += 1
            problems.append(f"{item.rel}: {type(exc).__name__}")
    summary = {
        "copied": copied,
        "skipped_same": skipped_same,
        "skipped_browser_running": skipped_browser,
        "failed": failed,
        "problems": problems[:50],
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    migration_dir = dest_root / "migration"
    migration_dir.mkdir(parents=True, exist_ok=True)
    (migration_dir / "migration.json").write_text(
        json.dumps({"summary": summary, "items": record}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def plan_to_report(migration_plan: Plan) -> dict:
    """사람이 읽는 드라이런 요약(비밀 값 없음)."""
    totals = migration_plan.totals()
    top_dirs: dict[str, int] = {}
    for item in migration_plan.items:
        if item.category == EXCLUDED:
            continue
        key = item.rel.split(":", 1)[0] + ":" + item.rel.split(":", 1)[1].split("/", 1)[0]
        top_dirs[key] = top_dirs.get(key, 0) + item.size
    return {
        "totals": totals,
        "missing_sources": migration_plan.missing_sources,
        "largest_included": sorted(top_dirs.items(), key=lambda kv: kv[1], reverse=True)[:12],
        "plan_items": [asdict(i) for i in migration_plan.items[:0]],  # 목록 본문은 보고서에 넣지 않는다(양이 많음)
    }
