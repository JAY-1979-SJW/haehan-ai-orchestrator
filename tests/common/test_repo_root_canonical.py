"""T1-① 경로 처리 정본화 1단계 — scripts.common.app_paths.repo_root() 가 모든 진입점에서 같은 값을 내는지.

배경: 운영 코드 약 439개 파일이 저장소 루트를 각자 Path(__file__).resolve().parents[N]
으로 계산한다(TOOL_MODULARIZATION_PLAN.md §3-1). repo_root() 를 단일 정본으로 삼고,
실행 위치가 다른 진입점(저장소 루트 실행·scripts/ CLI·orchestrator_v1 모듈 import·
Docker /app)에서 같은 절대경로를 내는지 고정한다. 동작 변경 없음 — 기존 각 파일의
parents[N] 계산과 같은 폴더를 가리키는지만 확인.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.common.app_paths import repo_root
from scripts.common.data_paths import _PROJECT_ROOT as DATA_PATHS_ROOT

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_repo_root_matches_this_file_based_computation():
    assert repo_root() == REPO_ROOT


def test_data_paths_delegates_to_same_repo_root():
    """data_paths.py 가 더 이상 자체 parents[2] 계산을 하지 않고 정본에 위임하는지."""
    assert DATA_PATHS_ROOT == repo_root()


def test_repo_root_from_subprocess_cwd_elsewhere():
    """실행 위치(cwd)가 저장소 밖이어도 __file__ 기준이라 같은 값이 나와야 한다
    (CLI를 scripts/ 밑에서 돌리거나 다른 디렉터리에서 돌리는 경우의 대체 시험 —
    실제 cwd 의존이 없음을 확인하는 것이 핵심)."""
    code = "from scripts.common.app_paths import repo_root; print(repo_root())"
    # 저장소 루트를 sys.path 에 넣어 cwd와 무관하게 import 되게 한다(실제 CLI도 동일 방식)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(Path.home()),  # 저장소 밖 cwd
        env={**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert result.stdout.strip() == str(REPO_ROOT)


def test_orchestrator_v1_module_import_sees_same_repo_root():
    """orchestrator_v1/ 하위 모듈에서 import 해도 같은 정본을 본다(패키지 깊이 무관)."""
    import orchestrator_v1

    assert Path(orchestrator_v1.__file__).resolve().parents[1] == repo_root()


def test_docker_app_workdir_layout_matches_repo_root_assumption():
    """Dockerfile이 COPY . . 로 저장소 내용을 /app 바로 아래 두므로(WORKDIR /app),
    컨테이너 안에서도 scripts/common/app_paths.py 기준 parents[1] 이 /app 과 같아야 한다 —
    이 파일 자체가 그 상대 구조를 쓰므로 검증은 Dockerfile 레이아웃 자체를 읽어 확인."""
    dockerfile = REPO_ROOT / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")
    assert "WORKDIR /app" in text
    assert "COPY . ." in text
    # scripts/common/app_paths.py 는 저장소 루트 바로 아래 scripts/ 안에 있어야
    # parents[1] 이 WORKDIR(/app)과 같은 폴더를 가리킨다.
    assert (REPO_ROOT / "scripts" / "common" / "app_paths.py").exists()
