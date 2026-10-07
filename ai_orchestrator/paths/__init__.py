"""저장소(소스 폴더) 위치 — 단일 정본 (T1-① 후속, 2026-10-07 폴더 순환 해소).

표준 라이브러리만 사용하고 프로젝트의 다른 모듈을 import 하지 않는 잎(leaf)
패키지다 — 패키지화한 이유는 폴더 단위 코드맵에서 ai_orchestrator 루트 노드에
있으면 ai_orchestrator 루트의 다른 모듈(router.py 등)이 ai_orchestrator/persistence
등을 쓰고 persistence가 루트의 paths를 쓰는 식으로 폴더 순환이 집계되기
때문이다(2026-10-07). paths/ 는 아무 것도 import하지 않는 독립 리프 폴더라
어느 서브패키지가 써도 순환이 생기지 않는다.

scripts.common.app_paths.repo_root()는 이 모듈을 재수출한다 — scripts → ai_orchestrator
import는 원래 허용된 방향이라 폴더 단위 순환이 생기지 않는다. ai_orchestrator
안의 호출자는 이 모듈을 직접 쓴다.

data_root()/config_root() 같은 윈도우 표준 앱데이터 경로 해석은 옮기지
않았다 — scripts/app_paths.py에 그대로 있다(다른 질문: "앱 데이터를
어디 쓰나" vs 이 모듈의 "저장소 소스가 어디 있나").
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def repo_root() -> Path:
    """이 저장소(소스 체크아웃)의 루트 폴더. 환경변수로 바꿀 수 없다(소스 위치는 실행 위치로 고정).

    worktree·Docker(COPY 로 들어간 /app 등)에서도 이 파일 기준 상대 경로이므로 항상 맞다.
    """
    return _REPO_ROOT
