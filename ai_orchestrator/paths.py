"""저장소(소스 폴더) 위치 — 단일 정본 (T1-① 후속, 2026-10-07 폴더 순환 해소).

표준 라이브러리만 사용하고 프로젝트의 다른 모듈을 import 하지 않는다
(ai_orchestrator/__init__.py가 비어 있어 이 모듈을 import해도 부작용이 없다).

scripts.app_paths.repo_root()는 이 모듈을 재수출한다 — scripts → ai_orchestrator
import는 원래 허용된 방향이라 폴더 단위 순환이 생기지 않는다(ai_orchestrator의
파일이 scripts.app_paths를 쓰면 ai_orchestrator↔scripts 양방향 간선이 생겨
순환으로 집계되던 문제의 해결). ai_orchestrator 안의 호출자는 이 모듈을
직접 쓴다.

data_root()/config_root() 같은 윈도우 표준 앱데이터 경로 해석은 옮기지
않았다 — scripts/app_paths.py에 그대로 있다(다른 질문: "앱 데이터를
어디 쓰나" vs 이 모듈의 "저장소 소스가 어디 있나").
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def repo_root() -> Path:
    """이 저장소(소스 체크아웃)의 루트 폴더. 환경변수로 바꿀 수 없다(소스 위치는 실행 위치로 고정).

    worktree·Docker(COPY 로 들어간 /app 등)에서도 이 파일 기준 상대 경로이므로 항상 맞다.
    """
    return _REPO_ROOT
