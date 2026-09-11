"""커뮤니티 게시글 → 트렌드·수익 기회 분석용 데이터 준비.

2026-09-12: 유료 OpenAI API 호출을 제거했다(사용자 지시 — "클로드 코드로 해야지
오픈ai api 관련되어서 모두 삭제해"). 분석 자체는 더 이상 이 함수가 자동으로
하지 않는다 — 수집된 게시글을 정리된 텍스트로 만들어 반환하면, 그걸 Claude
Code(대화형 세션)가 직접 읽고 인사이트를 낸다. API 비용 없음, 승인 절차 불필요.
"""

from __future__ import annotations

from typing import Any

_MAX_POSTS = 120
_MAX_CHARS = 11000


def prepare_posts_for_review(posts: list[dict], context: str = "") -> dict[str, Any]:
    """게시글 목록 → Claude Code가 직접 읽고 분석할 정리된 텍스트.

    옛 analyze_posts()처럼 자동으로 trends/opportunities를 만들어내지 않는다.
    이 함수는 순수 데이터 가공만 하고(무료), 실제 "분석"은 이 결과를 받아본
    Claude Code 세션이 그 자리에서 직접 수행한다.
    """
    posts = [p for p in (posts or []) if (p.get("title") or "").strip()][:_MAX_POSTS]
    if not posts:
        return {"ok": False, "error": "분석할 게시글이 없습니다"}

    lines = []
    for i, p in enumerate(posts, 1):
        meta = []
        if p.get("views"):
            meta.append(f"조회{p['views']}")
        if p.get("comments"):
            meta.append(f"댓글{p['comments']}")
        if p.get("date"):
            meta.append(str(p["date"]))
        suffix = f" ({', '.join(meta)})" if meta else ""
        lines.append(f"{i}. {p['title']}{suffix}")
    body = "\n".join(lines)[:_MAX_CHARS]

    return {
        "ok": True,
        "post_count": len(posts),
        "context": context,
        "formatted_text": body,
    }
