"""앱별 데이터 저장 경로 — 환경변수 AI_DATA_ROOT 기준.

AI_DATA_ROOT 가 설정되어 있으면 C:\\AI 에이전트\\{앱폴더} 를 사용하고,
없으면 기존 프로젝트 내 data/{앱키} 로 폴백한다.

사용 예:
    from scripts.common.data_paths import get_app_dir
    OUT = get_app_dir("cafe")   # Path("C:\\AI 에이전트\\카페") 또는 Path("data/cafe")
"""

from __future__ import annotations

import os
from pathlib import Path

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.app_paths import repo_root

# 앱 키 → C:\AI 에이전트 하위 폴더명 매핑
_APP_FOLDER: dict[str, str] = {
    "cafe": "카페",
    "blog": "블로그",
    "smartstore": "스마트스토어",
    "youtube": "유튜브",
    "eum": "EUM",
    "grant_radar": "지원사업",
    "gonobi": "고노비",
    "g2b": "나라장터",
    "naver_search": "네이버검색",
    "mail": "메일",
    "fax": "팩스",
}

# 프로젝트 루트 — T1-① 정본(scripts.common.app_paths.repo_root) 위임. 값은 기존과 동일
# (이 파일 기준 두 단계 위 == app_paths.py 기준 한 단계 위, 같은 저장소 루트).
_PROJECT_ROOT = repo_root()


def get_app_dir(app: str, sub: str = "") -> Path:
    """앱별 데이터 디렉터리 반환 + 자동 생성.

    Args:
        app: 앱 키 (cafe / blog / smartstore / youtube / eum / grant_radar / gonobi / g2b / naver_search / mail / fax)
        sub: 하위 폴더명 (선택)
    """
    root_env = os.environ.get("AI_DATA_ROOT", "").strip()
    if root_env:
        folder = _APP_FOLDER.get(app, app)
        base = Path(root_env) / folder
    else:
        base = data_dir() / app

    target = base / sub if sub else base
    target.mkdir(parents=True, exist_ok=True)
    return target
