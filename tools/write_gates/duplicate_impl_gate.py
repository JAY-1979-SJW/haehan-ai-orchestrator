"""신규 파일 생성 전 기존 구현 확인 게이트.

자동화 경로(scripts/naver/, ai_orchestrator/connectors/ 등)에 신규 .py 파일을
생성하려 할 때 capability_check.py로 기존 구현이 있는지 조회하고,
있으면 차단 사유를 반환한다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()

# 신규 파일 생성 시 기존 구현 확인을 강제하는 경로
AUTO_DIRS = [
    "scripts/naver/",
    "scripts/eum",
    "scripts/browser_agent/",
    "ai_orchestrator/connectors/",
]

# capability_check 키워드 추출 시 제외할 공통 조각
_SKIP_PARTS = {
    "scripts",
    "naver",
    "ai",
    "orchestrator",
    "connectors",
    "ops",
    "desktop",
    "browser",
    "agent",
    "collection",
    "analysis",
    "write",
}


def is_automation_path(path: str) -> bool:
    """상대경로("scripts/naver/...")·절대경로("<저장소 경로>/scripts/naver/...") 모두 인식.

    (2026-08-14: 절대경로 입력 시 startswith만으로는 항상 False가 되어 게이트가
    조용히 무력화되는 버그가 있었음 — 부분일치("/scripts/naver/" in path)를 추가)
    """
    p = path.replace("\\", "/")
    return any(p.startswith(d) or f"/{d}" in p for d in AUTO_DIRS)


def extract_keywords(path: str) -> list[str]:
    """경로에서 capability_check 검색 키워드 추출."""
    p = path.replace("\\", "/")
    # 절대경로면 저장소 위쪽 폴더명(예: C:/work/…)이 키워드로 섞이지 않게 자동화 경로부터만 본다
    for d in AUTO_DIRS:
        if p.startswith(d):
            break
        if f"/{d}" in p:
            p = p[p.index(f"/{d}") + 1 :]
            break
    # 경로 조각(디렉터리명)에서만 추출 — 파일명 제외 (신규 파일이라 의미 없음)
    dir_parts = p.split("/")[:-1]  # 파일명(마지막) 제외
    keywords: list[str] = []
    for part in dir_parts:
        word = part.lower().replace("-", "")
        if word and word not in _SKIP_PARTS and len(word) >= 3 and word not in keywords:
            keywords.append(word)
        if len(keywords) >= 2:
            break
    return keywords


def check(file_path: str, content: str) -> str | None:
    """신규 파일 생성 시 기존 구현이 있으면 차단 사유 문자열 반환, 아니면 None."""
    if not is_automation_path(file_path):
        return None

    # 이미 존재하는 파일 수정 → 통과 (신규 생성만 검사)
    full = Path(file_path) if Path(file_path).is_absolute() else ROOT / file_path
    if full.exists():
        return None

    keywords = extract_keywords(file_path)
    if not keywords:
        return None

    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "hooks" / "capability_check.py"), *keywords],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        encoding="utf-8",
    )
    output = (proc.stdout or "").strip()
    if not output or "기존 구현 없음" in output:
        return None

    return (
        f"신규 파일 생성 전 기존 구현 확인 필수\n"
        f"  대상 파일  : {file_path}\n"
        f"  검색 키워드: {' '.join(keywords)}\n"
        f"{output}\n"
        "⛔ 기존 구현이 있습니다.\n"
        "   위 API / 함수를 먼저 사용하세요.\n"
        "   정말 신규 파일이 필요하면 기존 구현과 완전히 다른 기능임을\n"
        "   먼저 설명한 뒤 작성하세요."
    )
