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
    python -m scripts.naver.blog.cli.blog_publish_manual draft.json --check     # 점검만
    python -m scripts.naver.blog.cli.blog_publish_manual draft.json --publish   # 실제 발행
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.logger import get_logger  # noqa: E402
from scripts.naver.blog.marketing.content import seo_check, split_body  # noqa: E402

_log = get_logger("scripts.naver.blog.cli.blog_publish_manual")


def verify_login(port: int = 9222, blog_id: str | None = None) -> dict:
    """발행 전 네이버 로그인 상태를 **미리** 확인한다.

    2026-08-24 사고: 세션이 만료돼 로그아웃된 걸 모르고 발행을 걸었더니
    `connect_and_ensure_login()`이 자동 재로그인을 시도하다 **캡차**에 막혀
    실패했다(`captcha_timeout`). 이미지 업로드까지 다 한 뒤에야 실패를
    알게 돼 시간이 버려졌다.

    그래서 **발행을 시작하기 전에 먼저 확인**하고, 로그아웃 상태면 곧바로
    멈춘다. **자동 재로그인은 시도하지 않는다** — 캡차는 사람만 풀 수 있고
    (CLAUDE.md), 반복 시도는 계정 잠금 위험만 키운다.

    반환: {"ok": bool, "blog_id": str, "reason": str}
    """
    from scripts.cdp_helper import CDP
    from scripts.naver.blog.accounts import get_account

    target_blog_id = blog_id or get_account()["blog_id"]

    # CDP 연결 자체도 try 안에서 한다 — 브라우저가 안 떠 있으면 여기서
    # URLError가 나는데, 밖에 두면 깔끔한 실패 대신 트레이스백이 터진다.
    cdp = None
    try:
        cdp = CDP(port=port)
        cdp.navigate("https://section.blog.naver.com/BlogHome.naver", wait=3)
        time.sleep(1.5)
        raw = cdp.js(
            """(function(){
              var a = document.querySelector('a[href*="admin.blog.naver.com/"]');
              var m = a ? a.href.match(/admin\\.blog\\.naver\\.com\\/([a-zA-Z0-9_]+)\\//) : null;
              var t = document.body ? document.body.innerText : '';
              return JSON.stringify({
                blogId: m ? m[1] : '',
                loggedOut: t.indexOf('로그아웃 상태입니다') > -1
              });
            })()"""
        )
        info = json.loads(raw) if raw else {}
    except Exception as e:
        return {"ok": False, "blog_id": "", "reason": f"브라우저/상태 확인 실패: {e}"}
    finally:
        if cdp is not None:
            cdp.close()

    blog_id = info.get("blogId", "")
    if info.get("loggedOut") or not blog_id:
        return {"ok": False, "blog_id": "", "reason": "네이버 로그아웃 상태"}
    if blog_id != target_blog_id:
        return {"ok": False, "blog_id": blog_id, "reason": f"다른 계정 로그인됨({blog_id}, 기대: {target_blog_id})"}
    return {"ok": True, "blog_id": blog_id, "reason": ""}


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
    images = draft.get("images", [])
    print(f"이미지: {len(images)}장")
    for img in images:
        print(f"  · {img}")
    if seo["warnings"]:
        print("\n⚠️ 점검 결과")
        for w in seo["warnings"]:
            print(f"  · {w}")
    else:
        print("\n✅ 점검 통과")
    return seo


def ensure_images(draft: dict, draft_path: Path, auto_images: bool = True, blog_id: str | None = None) -> list[str]:
    """--check 단계에서 이미지를 미리 확보해 원고 파일에 확정 저장한다.

    발행 승인은 이미지 포함 상태를 보고 이뤄져야 하므로(2026-08-23 사용자
    요청), --publish 시점에 처음 수집하던 것을 --check 시점으로 당긴다.
    이미 draft["images"]가 채워져 있으면(이전 --check에서 확정됨) 그대로
    재사용하고, Unsplash를 다시 호출하지 않는다.
    """
    if draft.get("images") or not auto_images:
        return draft.get("images", [])
    images = collect_images(draft, blog_id=blog_id)
    if images:
        draft["images"] = images
        draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        _log.info("[manual] 이미지 %d장 확보 후 원고에 저장: %s", len(images), draft_path)
    return images


def collect_images(draft: dict, count: int = 3, blog_id: str | None = None) -> list[str]:
    """원고에 이미지가 없으면 Unsplash에서 자동 수집한다.

    기존 구현(scripts/naver/blog/marketing/images.py)을 그대로 쓴다 — Unsplash
    정책상 download_location 트리거까지 처리해준다(CLAUDE.md 참조).
    """
    given = [str(p) for p in draft.get("images", []) if Path(p).exists()]
    if given:
        return given

    from scripts.naver.blog.marketing.images import fetch_unsplash_images, pick_3_images

    pool = fetch_unsplash_images(count_per_query=3, blog_id=blog_id)
    if not pool:
        _log.warning("[manual] Unsplash 이미지 수집 실패 — 이미지 없이 발행")
        return []

    # 글마다 다른 이미지가 붙게 인덱스를 잡는다.
    #
    # 2026-08-24 수정: 기존엔 `abs(hash(title)) % (len(pool)//3)` 이었는데
    # ① 파이썬 `hash()`는 프로세스마다 시드가 달라 재현이 안 되고
    # ② 나눗셈 때문에 후보 구간이 좁아 **서로 다른 두 글에 완전히 같은
    #    사진 3장이 붙는 사고**가 실제로 났다(draft_03 == draft_04).
    # 기준서 4.2 "콘텐츠 고유성" 위반이므로 **안정 해시(md5) + 이미 쓴
    # 이미지 회피**로 바꾼다.
    used: set[str] = set()
    try:
        from scripts.naver.blog.marketing.topics import load_cache

        for p in load_cache(blog_id).get("posted", []):
            for path in p.get("img_paths", []) or []:
                used.add(str(path))
    except Exception as e:
        _log.debug("[manual] 사용 이미지 이력 로드 실패(무시): %s", e)

    slots = max(1, len(pool) // 3)
    base = int(hashlib.md5(draft["title"].encode("utf-8")).hexdigest()[:8], 16) % slots
    for offset in range(slots):  # 이미 쓴 조합이면 다음 구간으로 밀어서 재시도
        picked = pick_3_images(pool, (base + offset) % slots)[:count]
        if not picked or not used.intersection(str(p) for p in picked):
            return picked
    return pick_3_images(pool, base)[:count]  # 전부 겹치면 어쩔 수 없이 반환


def publish(draft: dict, auto_images: bool = True, blog_id: str | None = None) -> dict:
    from scripts.naver.blog.accounts import get_account
    from scripts.naver.blog.marketing.publish import connect_and_ensure_login, publish_one, record_success
    from scripts.naver.blog.marketing.topics import load_cache

    target_blog_id = blog_id or get_account()["blog_id"]
    body = draft["body"]
    images = (
        collect_images(draft, blog_id=target_blog_id)
        if auto_images
        else [str(p) for p in draft.get("images", []) if Path(p).exists()]
    )
    post = {
        "title": draft["title"],
        "body": body,
        "body_segments": split_body(body, parts=max(1, len(images))) if images else None,
        "tags": draft.get("tags", []),
    }
    pw, _browser, page = connect_and_ensure_login(blog_id=target_blog_id)
    try:
        result = publish_one(page, post=post, img_paths=images)
    finally:
        try:
            pw.stop()
        except Exception:
            pass

    # 2026-08-19 GPT 차단 이후 이 수동 경로가 기본이 됐는데, 캐시 기록이
    # 빠져 있어서 중복 발행 방지가 무력화돼 있었다(2026-08-22 발견).
    if result.get("ok") and result.get("log_no"):
        cache = load_cache(target_blog_id)
        record_success(
            cache,
            topic=draft.get("topic", draft["title"]),
            post=post,
            log_no=result["log_no"],
            img_paths=images,
            blog_id=target_blog_id,
        )
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("draft", help="원고 JSON 경로")
    ap.add_argument(
        "--account", choices=["skyjwsin", "skyjwshin"], default=None, help="대상 블로그 계정 (기본: skyjwsin)"
    )
    ap.add_argument("--check", action="store_true", help="점검만 (기본)")
    ap.add_argument("--publish", action="store_true", help="실제 발행")
    ap.add_argument("--no-images", action="store_true", help="이미지 자동 수집 끄기")
    ap.add_argument("--port", type=int, default=9222, help="CDP 포트")
    args = ap.parse_args()

    from scripts.naver.blog.accounts import get_account

    blog_id = get_account(args.account)["blog_id"]

    draft_path = Path(args.draft)
    draft = load_draft(draft_path)
    ensure_images(draft, draft_path, auto_images=not args.no_images, blog_id=blog_id)
    seo = review(draft)

    if not args.publish:
        print("\n※ 실제 발행하려면 --publish")
        return

    # 발행 직전 로그인 확인 — 이미지 업로드까지 다 해놓고 캡차로 실패하는
    # 낭비를 막는다(2026-08-24 사고). 실패 시 자동 재로그인 없이 멈춘다.
    login = verify_login(port=args.port, blog_id=blog_id)
    if not login["ok"]:
        print(f"\n❌ 발행 중단 — {login['reason']}")
        print(f"   브라우저에서 {blog_id} 계정으로 직접 로그인한 뒤 다시 실행하세요.")
        print("   (캡차·OTP는 자동 처리 불가 — 반복 시도 시 계정 잠금 위험)")
        sys.exit(2)
    print(f"\n[로그인 확인] {login['blog_id']} ✅")

    if seo["warnings"]:
        print("\n경고가 있는 상태로 발행합니다 (사람이 확인함).")
    result = publish(draft, auto_images=not args.no_images, blog_id=blog_id)
    print(f"\n{'✅ 발행 완료' if result.get('ok') else '❌ 발행 실패'}  log_no={result.get('log_no', '')}")


if __name__ == "__main__":
    main()
