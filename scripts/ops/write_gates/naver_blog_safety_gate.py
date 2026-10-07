"""네이버 블로그 자동화 안전 게이트 (2026-08-14 추가).

경로와 무관하게 파일 "내용"을 검사해 아래 두 사고 패턴을 차단한다.

  1. Blog 작성기 클래스를 검증된 경로(scripts/naver/, ai_orchestrator/connectors/, tests/)
     밖에서 직접 import해서 즉석 스크립트로 쓰는 패턴 → 기존 write-to-naver API/
     정식 파이프라인 재사용 유도. (스크래치패드 등 임의 경로에서 파이프라인을
     재구현하다가 발행 사고가 난 전례 있음)
  2. Ctrl+A(전체선택) 직후 폰트 크기 변경 함수를 호출하는 위험 패턴
     (전체선택 상태에서 폰트 크기 툴바 조작 시 본문이 소실되는 사고 재현됨)
"""

from __future__ import annotations

import re

# 검증된 파이프라인 경로 — 아래 클래스를 직접 import해도 되는 위치
REVIEWED_BLOG_PATHS = [
    "scripts/naver/",
    "ai_orchestrator/connectors/",
    "tests/",
    # 2026-09-12: 고객 판매용 독립 제품(marketing_app_modularization_20260908.md
    # 기준서에 따라 원본 사본을 이식하는 리뷰된 작업 위치). 스크래치패드/임시
    # 스크립트가 아니라 이 경로 자체가 정식 제품 코드 위치다.
    "apps/marketing-standalone/",
]

# 문자열 결합: 이 게이트 정의 파일 자체가 스스로의 검사에 걸리지 않도록
_BLOG_WRITER_CLASS_NAME = "Blog" + "Writer"
_FONT_SIZE_FN_NAME = "set_font" + "_size"
_CTRL_A_FONT_SIZE_RE = re.compile(
    r"(Control\+A|Control\+a)[\s\S]{0,200}" + _FONT_SIZE_FN_NAME + r"\(",
    re.IGNORECASE,
)


def is_reviewed_blog_path(path: str) -> bool:
    """상대경로("scripts/naver/...")·절대경로("<저장소 경로>/scripts/naver/...") 모두 인식."""
    p = path.replace("\\", "/")
    return any(p.startswith(d) or f"/{d}" in p for d in REVIEWED_BLOG_PATHS)


def is_test_path(file_path: str) -> bool:
    p = file_path.replace("\\", "/")
    name = p.rsplit("/", 1)[-1]
    return "/tests/" in f"/{p}" or name.startswith("test_") or name.endswith("_test.py")


def check_blogwriter_bypass(file_path: str, content: str) -> str | None:
    """검증되지 않은 경로에서 Blog 작성기 클래스를 직접 써서 파이프라인을 재구현하는지 검사."""
    if _BLOG_WRITER_CLASS_NAME not in content:
        return None
    if is_reviewed_blog_path(file_path):
        return None
    return (
        f"{_BLOG_WRITER_CLASS_NAME}를 검증된 경로 밖(스크래치패드/임시 스크립트 등)에서 직접 호출하려 합니다.\n"
        "   네이버 블로그 작성/발행은 이미 검증된 파이프라인이 있습니다:\n"
        "     - API: POST /api/v1/naver/blog/write-to-naver (서버 구동 중이면 이걸 사용)\n"
        "     - 코드: ai_orchestrator/connectors/naver_blog/naver_blog_router.py write_to_naver()\n"
        "   즉석 스크립트로 단계를 새로 짜지 말고 위 경로를 그대로 호출하세요.\n"
        "   (2026-08-14: 즉석 스크립트가 검증되지 않은 순서로 본문을 지운 사고 발생)"
    )


def check_ctrl_a_font_size(file_path: str, content: str) -> str | None:
    """Ctrl+A(전체선택) 직후 폰트 크기 변경 함수를 호출하는 위험 패턴 검사.

    테스트 파일(tests/, test_*.py)은 이 패턴을 문자열 리터럴로 검증하기 위해
    의도적으로 포함하므로 검사 대상에서 제외한다.
    """
    if is_test_path(file_path):
        return None
    if _FONT_SIZE_FN_NAME not in content:
        return None
    if _CTRL_A_FONT_SIZE_RE.search(content):
        return (
            f"Ctrl+A(전체선택) 직후 {_FONT_SIZE_FN_NAME}() 호출 패턴이 감지됐습니다.\n"
            "   이 조합은 선택된 본문 텍스트가 소실되는 사고를 재현한 위험 패턴입니다.\n"
            "   (2026-08-14: 네이버 블로그 본문이 이 패턴으로 두 번 지워짐)\n"
            "   본문 전체 폰트 크기를 바꿔야 한다면 텍스트 입력 시점에 서식을 지정하거나,\n"
            "   전체선택 없이 문단 단위로 적용하세요."
        )
    return None


def check(file_path: str, content: str) -> str | None:
    """등록된 위험 패턴 검사를 순서대로 실행, 첫 차단 사유를 반환."""
    for fn in (check_blogwriter_bypass, check_ctrl_a_font_size):
        msg = fn(file_path, content)
        if msg:
            return msg
    return None
