"""번들 안 예전 위치 → 새 데이터 위치로 1회 복사 이행 (DESKTOP_RUNTIME_AUDIT D1).

이전 버전은 DB·감사 기록·업무 데이터를 코드 옆(`ai_orchestrator/storage`, `<저장소>/data`)에 썼다. 데스크톱이
HAEHAN_DATA_ROOT 를 사용자 프로필로 지정하면, 예전 위치에 데이터가 남아 있을 때 첫 실행에서 새 위치로 **복사**한다.

원칙:
- 이동이 아니라 복사 — 원본은 그대로 둔다(롤백 가능, 이행 중 중단돼도 데이터가 사라지지 않는다).
- 새 위치에 이미 있는 파일은 덮어쓰지 않는다(새 위치가 항상 우선).
- 완료 표시(`<root>/.bundle-migration.json`)를 남겨 다시 하지 않는다. 일부 실패하면 `complete: false` 로 남기고
  다음 실행에서 남은 것만 다시 시도한다(최대 3회, 같은 방식이라 안전).
- 어떤 실패도 서버 시작을 막지 않는다 — 로그와 경고만 남긴다.
- 서버가 DB 를 처음 열기 **전**에 불러야 한다(asgi 맨 위). 그래야 옛 users.db 가 이행돼 '계정이 비어 있지 않은' 상태가 된다.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from .runtime import (
    data_dir,
    data_root_override,
    default_data_dir,
    default_storage_dir,
    storage_dir,
)

logger = logging.getLogger(__name__)

MARKER_NAME = ".bundle-migration.json"
MAX_ATTEMPTS = 3
_SKIP_DIRS = {"__pycache__"}
_SKIP_SUFFIXES = {".pyc", ".tmp"}
_SKIP_NAMES = {".gitkeep", ".gitignore"}


def _copy_tree(src: Path, dst: Path, errors: list[str], defer: frozenset[str] = frozenset()) -> tuple[int, int]:
    """src → dst 로 없는 파일만 복사. (복사 수, 이미 있어 건너뛴 수).

    defer: 이번 호출에서 건너뛸 최상위 파일 이름(예: users.db) — 호출자가 나중에 따로 복사한다."""
    copied = skipped = 0
    if not src.is_dir():
        return 0, 0
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        rel = Path(root).relative_to(src)
        for name in files:
            if name in _SKIP_NAMES or Path(name).suffix in _SKIP_SUFFIXES:
                continue
            if rel == Path(".") and name in defer:
                continue
            target = dst / rel / name
            if target.exists():
                skipped += 1
                continue
            if _copy_file(Path(root) / name, target, errors):
                copied += 1
    return copied, skipped


def _copy_file(source: Path, target: Path, errors: list[str]) -> bool:
    """파일 하나를 복사(이미 있으면 호출자가 걸러야 한다). 실패하면 errors 에 쌓고 False."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".migrating")
        shutil.copy2(source, tmp)
        tmp.replace(target)  # 반쯤 복사된 파일이 정식 이름으로 남지 않게 원자적 교체
        return True
    except OSError as exc:
        errors.append(f"{source}: {type(exc).__name__}: {exc}")
        return False


def _same(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return a == b


def migrate_legacy_data() -> dict:
    """필요하면 이행하고 결과 요약을 돌려준다. 절대 예외를 밖으로 던지지 않는다."""
    try:
        return _migrate()
    except Exception as exc:  # noqa: BLE001 - 이행 실패가 서버 시작을 막으면 안 된다(로그·경고만)
        logger.warning("[migrate] 데이터 이행 중 예기치 못한 오류 — 건너뜀: %s: %s", type(exc).__name__, exc)
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def _migrate() -> dict:  # noqa: C901 - 이행 전제 조건(환경·번들 여부·표시 파일)을 순서대로 점검하는 절차
    root = data_root_override()
    if root is None:
        return {"status": "skipped", "reason": "HAEHAN_DATA_ROOT 없음(저장소 실행 — 기존 위치 그대로)"}
    if not (getattr(sys, "frozen", False) or os.environ.get("HAEHAN_MIGRATE_LEGACY") == "1"):
        # 소스 체크아웃의 data/ 는 수 GB 일 수 있어 번들(frozen) 실행에서만 자동 이행한다(시험·수동은 환경변수로 켬).
        return {"status": "skipped", "reason": "번들 실행이 아님(HAEHAN_MIGRATE_LEGACY=1 로 강제 가능)"}
    pairs = [
        ("storage", default_storage_dir(), storage_dir()),
        ("data", default_data_dir(), data_dir()),
    ]
    pairs = [(label, old, new) for label, old, new in pairs if not _same(old, new)]
    if not pairs:
        return {"status": "skipped", "reason": "예전 위치와 새 위치가 같음"}

    marker = root / MARKER_NAME
    prior: dict = {}
    if marker.is_file():
        try:
            prior = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prior = {}
        if prior.get("complete") is True:
            return {"status": "already_done", "migrated_at": prior.get("migrated_at")}
        if int(prior.get("attempts", 0)) >= MAX_ATTEMPTS:
            return {"status": "gave_up", "attempts": prior.get("attempts")}

    errors: list[str] = []
    summary: dict[str, dict[str, int]] = {}
    for label, old, new in pairs:
        copied, skipped = _copy_tree(old, new, errors)
        summary[label] = {"copied": copied, "skipped_existing": skipped}
    complete = not errors
    payload = {
        "complete": complete,
        "attempts": int(prior.get("attempts", 0)) + 1,
        "migrated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "from": {label: str(old) for label, old, _ in pairs},
        "to": {label: str(new) for label, _, new in pairs},
        "summary": summary,
        "errors": errors[:20],
    }
    try:
        root.mkdir(parents=True, exist_ok=True)
        tmp = marker.with_name(marker.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(marker)
    except OSError as exc:
        logger.warning("[migrate] 완료 표시 기록 실패(다음 실행에서 다시 시도): %s", exc)
    total = sum(v["copied"] for v in summary.values())
    if errors:
        logger.warning("[migrate] 예전 위치 → 새 위치 복사 일부 실패 %d건(시작은 계속) — %s", len(errors), errors[0])
    else:
        logger.info("[migrate] 예전 위치 → 새 위치 복사 완료: %d개 파일 %s", total, summary)
    return {"status": "complete" if complete else "partial", **payload}
