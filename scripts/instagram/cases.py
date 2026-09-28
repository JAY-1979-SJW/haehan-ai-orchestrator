"""gonobi_images_v2 폴더에서 시공사례(log_no 접두사)를 그룹핑하고,
이미 발행한 사례는 캐시로 걸러 다음 발행 후보를 고른다.

파일명 규칙: {log_no}_{순번}_{설명}.jpg|png
같은 log_no = 같은 네이버 블로그 글에서 나온 같은 시공사례 이미지 묶음.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from scripts.instagram import CACHE_PATH, IMAGE_ROOT, MAX_CAROUSEL

_FNAME_RE = re.compile(r"^(?P<log_no>\d+)_(?P<seq>\d+)_(?P<desc>.+)\.(jpg|jpeg|png)$", re.IGNORECASE)


@dataclass
class Case:
    log_no: str
    category: str
    desc: str
    images: list[Path] = field(default_factory=list)

    @property
    def case_id(self) -> str:
        return f"{self.category}:{self.log_no}"


def load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {"posted": []}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 인스타그램 게시 캐시 JSON 로드 - 손상/부재 시 빈 posted 목록으로 안전한 기본값 반환
        return {"posted": []}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def posted_case_ids(cache: dict | None = None, kind: str = "photo") -> set[str]:
    cache = cache or load_cache()
    return {p["case_id"] for p in cache.get("posted", []) if p.get("kind", "photo") == kind}


def scan_cases(category: str | None = None) -> list[Case]:
    """카테고리 폴더(들)를 스캔해 log_no 기준으로 이미지를 묶는다."""
    cases: dict[str, Case] = {}
    categories = [category] if category else [d.name for d in IMAGE_ROOT.iterdir() if d.is_dir()]

    for cat in categories:
        cat_dir = IMAGE_ROOT / cat
        if not cat_dir.exists():
            continue
        for f in sorted(cat_dir.iterdir()):
            if not f.is_file():
                continue
            m = _FNAME_RE.match(f.name)
            if not m:
                continue
            key = f"{cat}:{m.group('log_no')}"
            if key not in cases:
                cases[key] = Case(log_no=m.group("log_no"), category=cat, desc=m.group("desc"))
            cases[key].images.append(f)

    return sorted(cases.values(), key=lambda c: (c.category, c.log_no))


def next_case(category: str | None = None, kind: str = "photo") -> Case | None:
    """아직 발행 안 한(해당 kind 기준) 사례 중 이미지가 가장 많은 것을 고른다."""
    cache = load_cache()
    done = posted_case_ids(cache, kind=kind)
    candidates = [c for c in scan_cases(category) if c.case_id not in done and c.images]
    if not candidates:
        return None
    candidates.sort(key=lambda c: len(c.images), reverse=True)
    chosen = candidates[0]
    chosen.images = chosen.images[:MAX_CAROUSEL]
    return chosen


def mark_posted(case: Case, ig_url: str | None = None, kind: str = "photo") -> None:
    cache = load_cache()
    cache.setdefault("posted", []).append(
        {
            "case_id": case.case_id,
            "category": case.category,
            "log_no": case.log_no,
            "desc": case.desc,
            "ig_url": ig_url,
            "kind": kind,
        }
    )
    save_cache(cache)
