"""Unsplash 이미지 수집 - 건설 실무 블로그용 사진 검색/다운로드/배분.

발행 정책: 이미지는 A4 1장(본문 구간 1개)당 1장 매칭 - body_segments 3구간에
맞춰 포스트당 3장을 인터리브 삽입한다(publish.py에서 처리).
"""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.logger import get_logger
from scripts.naver.blog.accounts import DEFAULT_ACCOUNT
from scripts.naver.blog.marketing.topics import topic_key

_log = get_logger(__name__)

# 데이터 저장 위치 — 앱 본체(ai_orchestrator)에 의존하지 않는다.
#
# 원래는 `from ai_orchestrator.core.config import get_local_data_dir` 였는데,
# 이게 블로그 모듈이 앱 패키지에 걸린 **유일한 의존**이었다(2026-08-24 실측).
# 기준서 0절이 "언제든 들어낼 수 있는 경계 유지"를 요구하므로 직접 구현으로
# 대체했다. 동작은 동일하다 — `LOCAL_DATA_DIR` 환경변수, 없으면 repo/data.
_DEFAULT_DATA_DIR = data_dir()


def get_local_data_dir() -> Path:
    load_dotenv(override=True, encoding="utf-8")
    v = os.environ.get("LOCAL_DATA_DIR", "").strip()
    return Path(v) if v else _DEFAULT_DATA_DIR


# 건설 실무 관련 Unsplash 검색 쿼리 — 20포스트 × 3장 = 60장 필요
# 12개 쿼리 × 5장 = 60장 확보 (포스트마다 완전히 다른 이미지 3장)
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

# 조명·인테리어(skyjwshin) 검색 쿼리. 2026-08-24 추가 — 이전엔 계정과
# 무관하게 UNSPLASH_QUERIES(건설 전용)만 있어서 조명 발행 시도에도 건설
# 현장 사진이 나올 뻔했다(실제로는 401로 먼저 걸림, _unsplash_key() 버그
# 참조). 계정 인자로 검색어 세트를 고르도록 분리한다.
LIGHTING_UNSPLASH_QUERIES = [
    ("pendant light interior", "펜던트 조명"),
    ("ceiling light living room", "거실 천장등"),
    ("floor lamp cozy room", "플로어 스탠드"),
    ("led strip light interior", "LED 라인조명"),
    ("bedside lamp warm light", "침실 무드등"),
    ("kitchen island lighting", "주방 조명"),
    ("minimal apartment interior", "미니멀 인테리어"),
    ("studio apartment cozy", "원룸 인테리어"),
    ("home renovation interior", "셀프 인테리어"),
    ("electrician installing light", "전기 시공"),
    ("modern living room lamp", "모던 거실 조명"),
    ("wall sconce light", "벽등"),
]

_QUERY_SETS = {
    "skyjwsin": UNSPLASH_QUERIES,
    "skyjwshin": LIGHTING_UNSPLASH_QUERIES,
}


def queries_for(blog_id: str | None = None) -> list[tuple[str, str]]:
    return _QUERY_SETS.get(blog_id or DEFAULT_ACCOUNT, UNSPLASH_QUERIES)


def _img_dir():
    return get_local_data_dir() / "images" / "blog_ai_batch"


def _unsplash_key() -> str:
    # 2026-08-24 실측: fetch_unsplash_images()가 이 함수를 _img_dir()보다
    # 먼저 호출하는데, load_dotenv()는 _img_dir()->get_local_data_dir()
    # 안에만 있었다. 그래서 첫 실행 시 키가 아직 안 읽혀 12개 쿼리 전부
    # 401이 나고("이미지 없이 발행"), 그제서야 뒤늦게 dotenv가 로드돼도
    # 이미 pool이 비어 소용없었다. 여기서도 로드해 순서 의존성을 없앤다.
    load_dotenv(override=True, encoding="utf-8")
    return os.environ.get("UNSPLASH_ACCESS_KEY", "")


def fetch_unsplash_images(count_per_query: int = 5, blog_id: str | None = None) -> list[dict]:
    images = []
    for q_en, q_ko in queries_for(blog_id):
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
        except Exception as e:  # noqa: BLE001 - Unsplash 이미지 검색/다운로드 커넥터 — 실패 시 경고 로그만 남기고 다음 이미지로 진행, 읽기전용 외부 API 호출
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
    except Exception as e:  # noqa: BLE001 - Unsplash 이미지 검색/다운로드 커넥터 — 실패 시 경고 로그만 남기고 다음 이미지로 진행, 읽기전용 외부 API 호출
        _log.warning("이미지 다운로드 실패 %s: %s", url, e)
        return None


def pick_3_images(all_images: list[dict], idx: int) -> list[str]:
    """포스트 인덱스 기준으로 이미지 3장 선택.

    60장이면 포스트마다 완전히 다른 이미지(0~2, 3~5, ..., 57~59).
    이미지가 부족하면 순환 할당.
    """
    n = len(all_images)
    if n == 0:
        return []
    start = (idx * 3) % n
    selected = [all_images[(start + j) % n] for j in range(3)]
    paths = []
    for i, img in enumerate(selected):
        fn = f"post{idx:02d}_img{i + 1}_{topic_key(img['url'])}.jpg"
        path = download_image(img["url"], fn)
        if path:
            paths.append(path)
        # Unsplash 다운로드 트리거 (정책 준수) - 실패해도 다음 이미지로 진행(읽기전용 외부 API 호출)
        with contextlib.suppress(Exception):
            requests.get(
                img["download_location"],
                headers={"Authorization": f"Client-ID {_unsplash_key()}"},
                timeout=5,
            )
        time.sleep(0.2)
    return paths
