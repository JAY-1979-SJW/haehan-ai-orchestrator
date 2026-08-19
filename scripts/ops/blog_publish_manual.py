"""사람(Claude Code)이 작성한 원고를 네이버 블로그에 발행한다.

GPT 자동 생성 경로(blog_ai_batch_20.py)를 대체한다. 2026-08-19 사업자 결정으로
OpenAI 호출을 차단했고(ai_orchestrator/openai_guard.py), 글은 Claude Code가
직접 조사·작성한다. GPT는 학습 데이터만으로 쓰다 보니 "2022년 건설산업기본법",
"최저임금 10,000원" 같은 없는 수치를 지어내는 문제가 실제로 있었다.

원고 형식 (JSON 또는 마크다운 프론트매터):

    {
      "title": "제목 (30~50자, 핵심 키워드 포함)",
      "tags": ["태그1", "태그2", "태그3"],
      "body": "[이런 상황이시죠]\\n...\\n\\n[이렇게 하시면 됩니다]\\n...",
      "images": ["C:/path/a.jpg", "C:/path/b.jpg"]   # 선택
    }

본문 작성 원칙(content.py 프롬프트와 동일한 기준):
  [기] 진짜 막힌 지점 특정  [승] 왜 헷갈리나
  [전] 이렇게 하시면 됩니다 (본체 50~60%)  [결] 정리하면
  · 소제목은 [대괄호] — 네이버는 마크다운을 렌더링하지 않는다
  · 수치·법령은 확인된 것만. 모르면 "어디서 확인하는지"를 알려준다

사용:
    python -m scripts.ops.blog_publish_manual draft.json --check     # 점검만
    python -m scripts.ops.blog_publish_manual draft.json --publish   # 실제 발행
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.logger import get_logger  # noqa: E402
from scripts.naver.blog_marketing.content import seo_check, split_body  # noqa: E402

_log = get_logger("scripts.ops.blog_publish_manual")


def load_draft(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    draft = json.loads(raw)
    for key in ("title", "body"):
        if not draft.get(key):
            raise ValueError(f"원고에 '{key}'가 없습니다")
    draft.setdefault("tags", [])
    draft.setdefault("images", [])
    return draft


def review(draft: dict) -> dict:
    """발행 전 점검. content.py 와 같은 기준을 쓴다."""
    seo = seo_check(title=draft["title"], body=draft["body"], keywords=draft.get("tags", []))
    print(f"제목: {draft['title']}  ({len(draft['title'])}자)")
    print(f"본문: {len(draft['body'])}자  |  태그: {', '.join(draft.get('tags', [])) or '없음'}")
    print(f"이미지: {len(draft.get('images', []))}장")
    if seo["warnings"]:
        print("\n⚠️ 점검 결과")
        for w in seo["warnings"]:
            print(f"  · {w}")
    else:
        print("\n✅ 점검 통과")
    return seo


def collect_images(draft: dict, count: int = 3) -> list[str]:
    """원고에 이미지가 없으면 Unsplash에서 자동 수집한다.

    기존 구현(scripts/naver/blog_marketing/images.py)을 그대로 쓴다 — Unsplash
    정책상 download_location 트리거까지 처리해준다(CLAUDE.md 참조).
    """
    given = [str(p) for p in draft.get("images", []) if Path(p).exists()]
    if given:
        return given

    from scripts.naver.blog_marketing.images import fetch_unsplash_images, pick_3_images

    pool = fetch_unsplash_images(count_per_query=3)
    if not pool:
        _log.warning("[manual] Unsplash 이미지 수집 실패 — 이미지 없이 발행")
        return []
    # 제목 해시로 인덱스를 잡아 글마다 다른 이미지가 붙게 한다.
    idx = abs(hash(draft["title"])) % max(1, len(pool) // 3 or 1)
    return pick_3_images(pool, idx)[:count]


def publish(draft: dict, auto_images: bool = True) -> dict:
    from scripts.naver.blog_marketing.publish import connect_and_ensure_login, publish_one

    body = draft["body"]
    images = collect_images(draft) if auto_images else [str(p) for p in draft.get("images", []) if Path(p).exists()]
    post = {
        "title": draft["title"],
        "body": body,
        "body_segments": split_body(body, parts=max(1, len(images))) if images else None,
        "tags": draft.get("tags", []),
    }
    pw, _browser, page = connect_and_ensure_login()
    try:
        return publish_one(page, post=post, img_paths=images)
    finally:
        try:
            pw.stop()
        except Exception:
            pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("draft", help="원고 JSON 경로")
    ap.add_argument("--check", action="store_true", help="점검만 (기본)")
    ap.add_argument("--publish", action="store_true", help="실제 발행")
    ap.add_argument("--no-images", action="store_true", help="이미지 자동 수집 끄기")
    args = ap.parse_args()

    draft = load_draft(Path(args.draft))
    seo = review(draft)

    if not args.publish:
        print("\n※ 실제 발행하려면 --publish")
        return

    if seo["warnings"]:
        print("\n경고가 있는 상태로 발행합니다 (사람이 확인함).")
    result = publish(draft, auto_images=not args.no_images)
    print(f"\n{'✅ 발행 완료' if result.get('ok') else '❌ 발행 실패'}  log_no={result.get('log_no', '')}")


if __name__ == "__main__":
    main()
