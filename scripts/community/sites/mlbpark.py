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


def _parse_age_hours(date_text: str) -> float | None:
    """'N시간전' / 'N분전' / 'N일전' → 경과 시간(시간 단위).

    Returns:
        시간(float) — 파싱 성공.
        None       — 판단 불가(파싱 실패, DOM 텍스트 겹침 등). "오래된 글"로
                     단정하지 않는다 — 호출부에서 건너뛰기만 하고 순회는
                     계속한다. 오직 명확한 절대 날짜(MM.DD)만 컷오프 신호로 쓴다.
    """
    import re

    t = (date_text or "").strip()
    m = re.match(r"^(\d+)\s*시간전$", t)
    if m:
        return float(m.group(1))
    m = re.match(r"^(\d+)\s*분전$", t)
    if m:
        return float(m.group(1)) / 60
    m = re.match(r"^(\d+)\s*일전$", t)
    if m:
        return float(m.group(1)) * 24
    return None


def _is_absolute_date(date_text: str) -> bool:
    """'MM.DD' 절대 날짜 형식인지(상대시각 표기 기간을 넘어간 오래된 글 신호)."""
    import re

    return bool(re.match(r"^\d{1,2}\.\d{1,2}$", (date_text or "").strip()))


def list_board_range(page: Any, board: str, *, days: int = 7, max_pages: int = 300) -> dict[str, Any]:
    """게시판을 페이지네이션으로 순회해 최근 N일치 게시글을 모은다.

    MLB파크는 최근 글엔 'N시간전/N분전/N일전' 상대시각을, 오래된 글엔
    'MM.DD' 절대날짜를 쓴다 — 절대날짜가 보이면 N일 창을 벗어난 것으로
    보고 수집을 멈춘다(정확한 날짜 파싱보다 안전한 근사치).
    """
    from scripts.community.universal_extractor import _dedup

    code = BOARDS.get(board, board)
    cutoff_hours = days * 24
    all_posts: list[dict[str, Any]] = []
    stopped_reason = "max_pages_reached"

    for p in range(1, max_pages + 1):
        url = f"{BASE_URL}/mp/b.php?m=list&b={code}&page={p}"
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        from scripts.community.universal_extractor import _HEURISTIC_JS

        try:
            h = page.evaluate(_HEURISTIC_JS)
        except Exception:
            h = {"posts": []}
        posts = _dedup(h.get("posts", []) or [])
        if not posts:
            stopped_reason = "no_more_posts"
            break

        # 공지/고정글 1~2개가 오래된 절대날짜를 달고 최신글 사이에 섞여 나오는 경우가
        # 있어(관찰됨), 한 건이라도 절대날짜면 바로 멈추지 않는다 — 페이지 내 다수
        # (과반)가 절대날짜/기간초과일 때만 "진짜 오래된 페이지"로 판단한다.
        old_count = 0
        for post in posts:
            date_text = post.get("date", "")
            if _is_absolute_date(date_text):
                old_count += 1
                continue
            age = _parse_age_hours(date_text)
            if age is not None and age > cutoff_hours:
                old_count += 1
                continue
            all_posts.append(post)  # age=None(파싱 불가)도 일단 포함 — 놓치는 것보다 낫다

        if posts and old_count / len(posts) > 0.5:
            stopped_reason = "reached_date_cutoff"
            break

    return {
        "ok": True,
        "board": board,
        "days": days,
        "pages_scanned": p,
        "stopped_reason": stopped_reason,
        "count": len(all_posts),
        "posts": all_posts,
    }
