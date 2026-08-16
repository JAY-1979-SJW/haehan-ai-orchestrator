"""건설공무 관련 타인 블로그 대상 댓글·공감 — 검색 → 미리보기 → 승인 후 실행.

이웃(neighbor) 대상 자동화(blog_mixin_neighbor.py)와 달리, "이웃이 아닌 검색 결과"를
대상으로 한다. 정책상 위험도가 높은 작업이라 두 단계로 나눈다:

  1. plan   — 검색 + 댓글 초안 생성만. 실제 사이트에 아무것도 쓰지 않는다(읽기 전용).
              결과를 JSON으로 저장하고 사람이 검토하게 한다.
  2. execute — plan 결과 파일을 읽어 실제로 방문+공감+댓글을 수행한다.
              반드시 사용자 승인 후에만 호출한다(gate.force_approved 필요).

댓글은 광고/링크 없이, 그 글 제목을 참고한 짧고 진짜같은 한 줄 반응만 생성한다.
자기 채널 홍보는 절대 넣지 않는다(스팸 신고 리스크).
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

from ai_orchestrator.local_agent.browser.agent import BrowserAgent

ROOT = Path(__file__).resolve().parents[4]
PLAN_PATH = ROOT / "data" / "blog_engage_plan_latest.json"
LOG_PATH = ROOT / "data" / "blog_engage_log_latest.json"

# 광고/링크 없는 짧은 반응 템플릿 — 글 제목을 참고해 자연스럽게 고름
COMMENT_TEMPLATES = [
    "좋은 정보 감사합니다, 도움이 많이 됐어요!",
    "저도 비슷한 상황이라 공감하면서 읽었습니다.",
    "실무에 바로 참고할 수 있는 내용이네요, 감사합니다.",
    "정리 잘해주셔서 이해가 쉬웠습니다!",
    "저희 현장도 비슷한 이슈가 있었는데 참고하겠습니다.",
]


def _own_blog_ids(exclude: set[str]) -> set[str]:
    return exclude


def plan(query: str, agent: BrowserAgent, max_targets: int = 8, exclude_blog_ids: list[str] | None = None) -> dict:
    """검색만 수행. 아무것도 쓰지 않음(read-only)."""
    results = agent.blog_search(query, max_results=max_targets * 2)
    exclude = set(exclude_blog_ids or [])

    targets = []
    for r in results:
        url = r.get("href") or r.get("url") or r.get("link") or ""
        if not url or "blog.naver.com" not in url:
            continue
        blog_id = r.get("blog_id") or url.split("blog.naver.com/")[-1].split("/")[0]
        if blog_id in exclude:
            continue
        title = r.get("title", "")
        comment = random.choice(COMMENT_TEMPLATES)
        targets.append(
            {
                "blog_id": blog_id,
                "url": url,
                "title": title,
                "planned_comment": comment,
                "planned_like": True,
            }
        )
        if len(targets) >= max_targets:
            break

    payload = {
        "query": query,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "target_count": len(targets),
        "targets": targets,
        "note": "read-only 계획입니다. 아무것도 게시되지 않았습니다. execute() 호출 전 반드시 사람이 검토하세요.",
    }
    PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLAN_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def execute(
    agent: BrowserAgent, plan_path: str | Path = PLAN_PATH, delay_seconds: float = 8.0, add_neighbor: bool = True
) -> dict:
    """plan() 결과를 읽어 실제로 방문+공감+댓글 수행. 승인 후에만 호출할 것."""
    data = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    results = []
    for t in data["targets"]:
        row = {"blog_id": t["blog_id"], "url": t["url"], "liked": False, "commented": False, "error": ""}
        row["neighbor_added"] = False
        try:
            like_r = agent.blog_like_post(t["url"])
            row["liked"] = bool(like_r.get("ok"))
            time.sleep(1.5)
            cmt_r = agent.blog_write_comment(t["url"], t["planned_comment"])
            row["commented"] = bool(cmt_r.get("ok"))
            if not cmt_r.get("ok"):
                row["error"] = cmt_r.get("error", "")
            time.sleep(1.5)
            if add_neighbor:
                nb_r = agent.blog_add_neighbor(t["url"])
                row["neighbor_added"] = bool(nb_r.get("ok"))
                if not nb_r.get("ok") and not row["error"]:
                    row["error"] = nb_r.get("error", "")
        except Exception as e:
            row["error"] = str(e)
        results.append(row)
        time.sleep(delay_seconds)

    payload = {
        "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "results": results,
        "success_like": sum(1 for r in results if r["liked"]),
        "success_comment": sum(1 for r in results if r["commented"]),
        "success_neighbor": sum(1 for r in results if r.get("neighbor_added")),
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
