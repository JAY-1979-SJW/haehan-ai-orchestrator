"""네이버 스마트스토어 카테고리 해석기 (로컬 조회 — 브라우저 불필요).

왜 필요한가 (2026-08-15 실제 사고):
    '라인조명' 이라는 그럴듯한 이름으로 상품 등록을 시도했다. 브라우저를 열고,
    로그인을 확인하고, 사이드바로 진입해 자동완성에 입력한 **뒤에야**
    "그런 카테고리 없음" 이 드러났다. 60초를 쓰고 얻은 정보가 실패 사실뿐이었다.

    그런데 답은 이미 `data/smartstore/categories.json` 에 있었다.
    조회하지 않았을 뿐이다.

설계 원칙:
    브라우저에 가기 전에 로컬에서 확인할 수 있는 것은 전부 확인한다.
    그리고 틀렸을 때는 **고칠 수 있는 형태**로 돌려준다(후보 제시).
    이래야 사람도 AI 에이전트도 스스로 교정할 수 있다.

주의:
    이 파일은 1차 거름망이다. 최종 판정은 브라우저 자동완성 검증이 계속 맡는다.
    네이버가 카테고리를 바꾸면 이 파일이 옛 정보가 될 수 있기 때문이다.
    (신선도 점검은 주간 셀렉터 헬스체크에서 함께 본다)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# scripts/naver/smartstore/product/ -> 저장소 루트
_ROOT = Path(__file__).resolve().parents[4]
CATEGORY_FILE = _ROOT / "data" / "smartstore" / "categories.json"

# 경로 구분자 (예: 가구/인테리어>인테리어소품>조명>인테리어조명)
_SEP = ">"
_PATH_RE = re.compile(r'"([^"]*>[^"]*)"')

HOW_EXACT_LEAF = "exact_leaf"
HOW_EXACT_PATH = "exact_path"


@dataclass(frozen=True)
class CategoryMatch:
    """해석 결과. path 가 네이버에 실제 존재하는 정식 경로다."""

    path: str
    leaf: str
    how: str

    def to_dict(self) -> dict:
        return {"path": self.path, "leaf": self.leaf, "how": self.how}


class CategoryResolver:
    """카테고리명 → 정식 경로 해석 + 오입력 시 후보 제시."""

    def __init__(self, paths: list[str]):
        self.paths = paths
        self.by_leaf: dict[str, list[str]] = {}
        for p in paths:
            self.by_leaf.setdefault(p.split(_SEP)[-1], []).append(p)

    # ── 로드 ────────────────────────────────────────────────────
    @classmethod
    def load(cls, path: str | Path | None = None) -> CategoryResolver:
        """categories.json 에서 '>' 를 포함한 모든 경로 문자열을 수집한다.

        파일 구조(키 배치)가 바뀌어도 경로 문자열만 뽑으면 되므로
        스키마 변화에 둔감하다.
        """
        f = Path(path) if path else CATEGORY_FILE
        if not f.exists():
            return cls([])
        try:
            raw = f.read_text(encoding="utf-8")
            json.loads(raw)  # 유효성만 확인 (파싱 실패 시 빈 해석기)
        except (OSError, ValueError):
            return cls([])
        return cls(sorted(set(_PATH_RE.findall(raw))))

    @property
    def loaded(self) -> bool:
        return bool(self.paths)

    # ── 해석 ────────────────────────────────────────────────────
    def resolve(self, name: str) -> CategoryMatch | None:
        """정확히 일치하는 것만 인정한다. 애매하면 None 을 반환한다.

        부분일치를 성공으로 처리하면 엉뚱한 카테고리에 상품이 등록된다.
        (실측: 자동완성 첫 항목이 'LED모듈' 이라 맹목적 선택은 위험하다)
        """
        name = (name or "").strip()
        if not name:
            return None
        if name in self.by_leaf:
            return CategoryMatch(self.by_leaf[name][0], name, HOW_EXACT_LEAF)
        if name in self.paths:
            return CategoryMatch(name, name.split(_SEP)[-1], HOW_EXACT_PATH)
        return None

    def is_ambiguous(self, name: str) -> bool:
        """같은 말단명이 여러 경로에 있는가 (예: '조명' 이 여러 대분류에 존재)."""
        return len(self.by_leaf.get((name or "").strip(), [])) > 1

    def paths_for(self, leaf: str) -> list[str]:
        return list(self.by_leaf.get((leaf or "").strip(), []))

    def candidates(self, name: str, limit: int = 3) -> list[str]:
        """오입력 시 제시할 후보. 글자 겹침 기준(외부 의존 없음).

        '라인조명' → 인테리어조명 / 플래시·라이트·조명 / 조명 처럼
        사람이 바로 알아볼 수 있는 후보를 준다.
        """
        name = (name or "").strip()
        if not name:
            return []
        chars = set(name)
        scored: list[tuple[int, int, str]] = []
        for leaf in self.by_leaf:
            common = len(chars & set(leaf))
            if common >= 2:
                # 겹침 많은 순 → 짧은 순 (짧을수록 일반적인 상위 개념)
                scored.append((-common, len(leaf), leaf))
        scored.sort()
        return [leaf for _, _, leaf in scored[:limit]]


@lru_cache(maxsize=1)
def get_resolver() -> CategoryResolver:
    """기본 해석기(캐시). 파일이 없으면 loaded=False 인 빈 해석기."""
    return CategoryResolver.load()
