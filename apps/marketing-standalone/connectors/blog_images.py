"""Unsplash 이미지 수집 - 건설 실무 블로그용 사진 검색/다운로드/배분.

원본: scripts/naver/blog/marketing/images.py (원본도 이미 ai_orchestrator
무의존이었음). 유일한 차이: topics.py::topic_key(해시 한 줄)를 import하지
않고 인라인으로 이식해 topics.py(리서치/중복방지 로직, Phase 2 대상) 의존을
없앴다.
"""

from __future__ import annotations

import hashlib
import os
import sys as _sys
import time
from pathlib import Path
from pathlib import Path as _Path

import requests
from dotenv import load_dotenv

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from _bootstrap import get_logger

_log = get_logger(__name__)

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
# 격리 원칙: 이 앱은 반드시 자기 자신의 .env만 읽는다 — python-dotenv 기본
# 동작(load_dotenv())은 상위 디렉터리로 자동 검색하는데, 이 앱이 본사 저장소
# 하위에 있어서 본사 진짜 .env(회사 OpenAI 키)를 잘못 로드하는 사고가 실제로
# 발생했다(2026-09-12). dotenv_path를 이 앱 폴더로 명시 고정해 재발 방지.
_APP_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def get_local_data_dir() -> Path:
    load_dotenv(dotenv_path=_APP_ENV_PATH, override=True, encoding="utf-8")
    v = os.environ.get("LOCAL_DATA_DIR", "").strip()
    return Path(v) if v else _DEFAULT_DATA_DIR


def _topic_key(title: str) -> str:
    return hashlib.md5(title.strip().lower().encode(), usedforsecurity=False).hexdigest()[:12]


# 건설 실무 관련 Unsplash 검색 쿼리 — 신규 앱 설치 시 고객 업종에 맞게
# 이 리스트를 교체하는 것을 전제로 한다(이 회사 전용 값이 아니라 예시).
UNSPLASH_QUERIES = [
    ("construction site workers", "건설현장 근로자"),
    ("construction blueprint plan", "건설 도면"),
    ("office paperwork documents desk", "서류 작업"),
    ("construction site safety helmet", "건설현장 안전모"),
    ("architect engineer meeting", "건축·엔지니어 미팅"),
    ("crane building construction", "건설 크레인"),
    ("contract signing business", "계약 서명"),
    ("laptop office work desk", "사무실 업무"),
    ("construction site manager clipboard", "현장소장 점검"),
    ("building site equipment", "건설 장비"),
    ("calculator finance accounting", "회계·정산"),
    ("construction worker tools", "건설 도구"),
]


def queries_for(query_set: list[tuple[str, str]] | None = None) -> list[tuple[str, str]]:
    """계정별 검색어 세트. 원본은 blog_id -> 세트 매핑(회사 전용 계정명)이었으나,
    신규 앱은 설치 시 고객이 자기 업종 쿼리 세트를 config로 넘기는 구조로 바꿨다."""
    return query_set or UNSPLASH_QUERIES


def _img_dir():
    return get_local_data_dir() / "images" / "blog_ai_batch"


def _unsplash_key() -> str:
    load_dotenv(dotenv_path=_APP_ENV_PATH, override=True, encoding="utf-8")
    return os.environ.get("UNSPLASH_ACCESS_KEY", "")


def fetch_unsplash_images(count_per_query: int = 5, query_set: list[tuple[str, str]] | None = None) -> list[dict]:
    images = []
    for q_en, q_ko in queries_for(query_set):
        try:
            r = requests.get(
                "https://api.unsplash.com/search/photos",
                params={"query": q_en, "per_page": count_per_query, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {_unsplash_key()}"},
                timeout=10,
            )
            if r.status_code == 200:
                for ph in r.json().get("results", []):
                    images.append(
                        {
                            "query": q_ko,
                            "url": ph["urls"]["regular"],
                            "small": ph["urls"]["small"],
                            "desc": (ph.get("description") or ph.get("alt_description") or "AI")[:60],
                            "author": ph["user"]["name"],
                            "download_location": ph["links"]["download_location"],
                        }
                    )
            else:
                _log.warning("Unsplash %s: %s", q_en, r.status_code)
        except Exception as e:
            _log.warning("Unsplash fetch error: %s", e)
        time.sleep(0.3)
    return images


def download_image(url: str, filename: str) -> str | None:
    img_dir = _img_dir()
    img_dir.mkdir(parents=True, exist_ok=True)
    path = img_dir / filename
    if path.exists():
        return str(path)
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "HaehanAI/1.0"})
        r.raise_for_status()
        path.write_bytes(r.content)
        return str(path)
    except Exception as e:
        _log.warning("이미지 다운로드 실패 %s: %s", url, e)
        return None


def pick_3_images(all_images: list[dict], idx: int) -> list[str]:
    """포스트 인덱스 기준으로 이미지 3장 선택. 이미지가 부족하면 순환 할당."""
    n = len(all_images)
    if n == 0:
        return []
    start = (idx * 3) % n
    selected = [all_images[(start + j) % n] for j in range(3)]
    paths = []
    for i, img in enumerate(selected):
        fn = f"post{idx:02d}_img{i + 1}_{_topic_key(img['url'])}.jpg"
        path = download_image(img["url"], fn)
        if path:
            paths.append(path)
        try:
            requests.get(
                img["download_location"],
                headers={"Authorization": f"Client-ID {_unsplash_key()}"},
                timeout=5,
            )
        except Exception as e:
            _log.debug("Unsplash download_location 트리거 실패(무시): %s", e)
        time.sleep(0.2)
    return paths
