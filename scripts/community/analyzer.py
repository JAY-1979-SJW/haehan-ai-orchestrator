"""커뮤니티 게시글 → AI 트렌드·수익 기회 분석.

수집된 게시글(제목·날짜·조회·댓글)을 GPT에 주고 구조화 인사이트 생성:
  - summary: 한 줄 요약
  - trends: 지금 흐름/핫토픽
  - opportunities: 수익 기회(반복되는 불편 → 아이디어)
  - topics: 토픽 분포
  - actions: 액션 제안
"""

from __future__ import annotations

import json
import re
from typing import Any

_MAX_POSTS = 120
_MAX_CHARS = 11000


def analyze_posts(posts: list[dict], context: str = "") -> dict[str, Any]:
    """게시글 목록 → AI 인사이트 리포트."""
    posts = [p for p in (posts or []) if (p.get("title") or "").strip()][:_MAX_POSTS]
    if not posts:
        return {"ok": False, "error": "분석할 게시글이 없습니다"}

    from ai_orchestrator.openai_proxy_caller import call_openai_chat

    # 게시글을 압축 텍스트로 (제목 + 조회/댓글 신호)
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

    prompt = (
        "당신은 커뮤니티 트렌드·시장기회 분석가입니다. 아래는 커뮤니티 게시글 목록입니다"
        f"{('(' + context + ')') if context else ''}.\n"
        "조회수·댓글수가 높을수록 관심이 큰 글입니다. 이를 바탕으로 분석하세요.\n\n"
        "아래 JSON 형식으로만 출력(설명·마크다운 금지):\n"
        "{\n"
        '  "summary": "전체 흐름 한 줄 요약",\n'
        '  "trends": ["지금 뜨는 주제/흐름 3~6개"],\n'
        '  "opportunities": [{"idea":"수익 아이디어", "why":"근거(어떤 반복되는 불편/니즈)"}],\n'
        '  "topics": [{"name":"토픽", "share":"대략 비중(예: 높음/중간/낮음)"}],\n'
        '  "actions": ["바로 해볼 만한 구체 액션 3~5개"]\n'
        "}\n\n"
        f"[게시글 {len(posts)}건]\n{body}"
    )
    res = call_openai_chat(message=prompt, max_tokens=2500)
    if not res.ok:
        return {"ok": False, "error": res.error_code or "분석 실패"}

    raw = res.text.strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {"ok": False, "error": "분석 결과 파싱 실패", "raw": raw[:300]}
    try:
        data = json.loads(m.group(0))
    except Exception:
        return {"ok": False, "error": "분석 결과 JSON 오류", "raw": raw[:300]}

    return {
        "ok": True,
        "analyzed_count": len(posts),
        "summary": str(data.get("summary", "")),
        "trends": data.get("trends", []) or [],
        "opportunities": data.get("opportunities", []) or [],
        "topics": data.get("topics", []) or [],
        "actions": data.get("actions", []) or [],
    }
