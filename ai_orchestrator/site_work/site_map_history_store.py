"""L7 Persistence — 사이트 지도 이력 저장소 (호스트·버전별 구조 요약 파일).

기준서: docs/specs/2026-10-05_new_site_onboarding_pipeline.md (M11)

- 위치: `<지도 폴더>/_history/<host>/<map_rev>.json` — 지도 폴더는 호출자가 넘긴다(시험이 저장 위치를 바꿔도 실제 데이터를 건드리지 않게).
- 구조 요약만 저장한다(값·시각 외 정보 없음). 최근 `RETENTION` 개만 보존하고 오래된 것은 지운다.
- 쓰기는 임시 파일 → 교체(원자적). 형식이 틀린 파일은 읽을 때 오류를 낸다.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from . import site_map_history as hist

_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")
_REV_FILE = re.compile(r"^(\d+)\.json$")


def _host_dir(root: Path, host: str) -> Path:
    host = str(host or "").strip().lower()
    if not _HOST_RE.match(host) or ".." in host:
        raise ValueError("호스트 이름이 올바르지 않습니다")
    return root / "_history" / host


def _revs(folder: Path) -> list[int]:
    if not folder.exists():
        return []
    return sorted(int(m.group(1)) for p in folder.iterdir() if (m := _REV_FILE.match(p.name)))


def save(root: Path, host: str, rev: int, struct: dict[str, Any], *, at: str, fingerprint: str) -> Path:
    """한 버전의 구조 요약을 저장하고 보존 개수를 넘는 옛 버전을 지운다."""
    folder = _host_dir(root, host)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{int(rev)}.json"
    payload = {"map_rev": int(rev), "fingerprint": fingerprint, "at": at, "structure": struct}
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{rev}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    for old in _revs(folder)[: -hist.RETENTION]:
        (folder / f"{old}.json").unlink(missing_ok=True)
    return path


def list_revs(root: Path, host: str) -> list[dict[str, Any]]:
    """보존 중인 버전 목록(최신 순) — 버전·지문·저장 시각만."""
    folder = _host_dir(root, host)
    out = []
    for rev in reversed(_revs(folder)):
        item = load(root, host, rev)
        out.append({"map_rev": item["map_rev"], "fingerprint": item["fingerprint"], "at": item["at"]})
    return out


def load(root: Path, host: str, rev: int) -> dict[str, Any]:
    path = _host_dir(root, host) / f"{int(rev)}.json"
    if not path.exists():
        raise ValueError(f"보존된 지도 버전을 찾을 수 없습니다: {int(rev)}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"지도 이력 파일을 읽을 수 없습니다: {path.name}") from e
    if not isinstance(data, dict) or not isinstance(data.get("structure"), dict):
        raise ValueError(f"지도 이력 파일 형식이 올바르지 않습니다: {path.name}")
    return data
