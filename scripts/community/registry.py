"""커뮤니티 사이트 레지스트리 — 모니터링할 사이트(URL) 목록 저장.

data/community/sites.json 에 보관. 쓰기 작업은 라우터(owner/admin)에서만 호출.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from ai_orchestrator.paths.runtime import atomic_write_text, data_dir

ROOT = Path(__file__).resolve().parents[2]
_SITES_FILE = data_dir() / "community" / "sites.json"


def _load() -> list[dict]:
    if not _SITES_FILE.exists():
        return []
    try:
        return json.loads(_SITES_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 커뮤니티 사이트 레지스트리 JSON 로드 실패 시 빈 목록 반환 - 읽기전용 설정 조회 폴백, 쓰기 없음
        return []


def _save(sites: list[dict]) -> None:
    _SITES_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(_SITES_FILE, json.dumps(sites, ensure_ascii=False, indent=2))


def list_sites() -> list[dict]:
    return _load()


def add_site(url: str, name: str = "", note: str = "") -> dict:
    url = (url or "").strip()
    if not url.startswith("http"):
        raise ValueError("http(s) URL 이어야 합니다")
    sites = _load()
    # 중복 URL 방지
    for s in sites:
        if s.get("url") == url:
            return s
    sid = re.sub(r"[^a-z0-9]+", "", url.lower())[:24] + str(len(sites) + 1)
    site = {
        "id": sid,
        "name": (name or "").strip() or _guess_name(url),
        "url": url,
        "note": (note or "").strip(),
        "added_at": datetime.now().isoformat(timespec="seconds"),
    }
    sites.append(site)
    _save(sites)
    return site


def remove_site(site_id: str) -> bool:
    sites = _load()
    new = [s for s in sites if s.get("id") != site_id]
    if len(new) == len(sites):
        return False
    _save(new)
    return True


def _guess_name(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else url[:30]
