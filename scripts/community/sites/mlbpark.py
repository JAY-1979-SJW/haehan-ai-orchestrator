"""MLB파크(mlbpark.donga.com) 게시판 게시글 수집.

범용 휴리스틱(universal_extractor.extract_posts)으로 이미 잘 동작하는 걸
2026-09-12 확인했지만(불펜 게시판 50건), 매번 URL을 손으로 조립하지 않도록
게시판 별칭과 헬퍼를 이 모듈에 정리해둔다.

로그인 불필요, GPT 폴백 없이 헤리스틱만으로 충분.
"""

from __future__ import annotations

from typing import Any

BASE_URL = "https://mlbpark.donga.com"

BOARDS = {
    "불펜": "bullpen",
    "자유게시판": "mbs4",
    "해외야구": "mbs5",
    "국내야구": "mbs2",
}


def board_url(board: str) -> str:
    """별칭(BOARDS 키) 또는 실제 게시판 코드 → 게시글 목록 URL."""
    code = BOARDS.get(board, board)
    return f"{BASE_URL}/mp/b.php?m=list&b={code}"


def list_board(page: Any, board: str, *, max_posts: int = 50) -> list[dict[str, Any]]:
    """게시판(별칭 또는 코드) → 게시글 목록(제목/링크/작성시각)."""
    from scripts.community.universal_extractor import extract_posts

    url = board_url(board)
    if not url.startswith(BASE_URL):
        raise ValueError(f"mlbpark.donga.com URL만 허용됩니다: {url!r}")
    result = extract_posts(page, url, max_posts=max_posts)
    if not result.get("ok"):
        return []
    return result.get("posts", [])
