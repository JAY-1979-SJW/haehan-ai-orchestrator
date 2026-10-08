"""사람(Claude Code)이 작성한 원고를 네이버 블로그에 발행한다.

GPT 자동 생성 경로(blog_ai_batch_20.py)를 대체한다. 2026-08-19 사업자 결정으로
OpenAI 호출을 차단했고(ai_orchestrator/llm/openai_guard.py), 글은 Claude Code가
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
import contextlib
import hashlib
import json
import sys
import time
from pathlib import Path

from scripts.naver.blog.accounts import BLOG_ACCOUNTS, DEFAULT_ACCOUNT

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.common.logger import get_logger  # noqa: E402
from scripts.naver.blog.marketing.content import seo_check, split_body  # noqa: E402

_log = get_logger("scripts.naver.blog.cli.blog_publish_manual")


def verify_login(port: int = 9222, blog_id: str | None = None) -> dict:
    """발행 전 네이버 로그인 상태를 **미리** 확인한다.

    2026-08-24 사고 ①: 세션이 만료돼 로그아웃된 걸 모르고 발행을 걸었더니
    `connect_and_ensure_login()`이 자동 재로그인을 시도하다 **캡차**에 막혀
    실패했다(`captcha_timeout`). 이미지 업로드까지 다 한 뒤에야 실패를
    알게 돼 시간이 버려졌다.

    그래서 **발행을 시작하기 전에 먼저 확인**하고, 로그아웃 상태면 곧바로
    멈춘다. **자동 재로그인은 시도하지 않는다** — 캡차는 사람만 풀 수 있고
    (CLAUDE.md), 반복 시도는 계정 잠금 위험만 키운다.

    2026-08-24 사고 ②: skyjwshin 첫 실전 발행에서 **정상 로그인 상태인데
    "로그아웃"으로 오판**했다. admin.blog.naver.com/{alias}/ 의 {alias}는
    로그인 ID가 아니라 **공개 주소**(커스텀 설정 시 하이픈 포함,
    "beautiful-light")인데, 정규식이 `[a-zA-Z0-9_]+`라 하이픈을 못 잡아
    매칭 자체가 실패했고, blogId가 비어 "로그아웃"으로 처리됐다. 정규식에
    하이픈을 추가하고, 비교 대상도 로그인 ID가 아니라
    `accounts.py::public_alias`(계정별 실제 공개 주소)로 바꿨다.

    반환: {"ok": bool, "blog_id": str, "reason": str}
    """
    from scripts.browser.cdp.cdp_helper import CDP
    from scripts.naver.blog.accounts import get_account

    account = get_account(blog_id)
    target_alias = account.get("public_alias") or account["blog_id"]

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
              var m = a ? a.href.match(/admin\\.blog\\.naver\\.com\\/([a-zA-Z0-9_-]+)\\//) : null;
              var t = document.body ? document.body.innerText : '';
              return JSON.stringify({
                blogId: m ? m[1] : '',
                loggedOut: t.indexOf('로그아웃 상태입니다') > -1
              });
            })()"""
        )
        info = json.loads(raw) if raw else {}
    except Exception as e:  # noqa: BLE001 - 블로그 수동발행 CLI — CDP 상태조회 실패는 에러 dict 반환, 사용이미지 이력로드/playwright 종료 실패는 무시하고 계속(중복발행 방지 캐시는 부가기능, 발행 자체 실패는 아님)
        return {"ok": False, "blog_id": "", "reason": f"브라우저/상태 확인 실패: {e}"}
    finally:
        if cdp is not None:
            cdp.close()

    detected_alias = info.get("blogId", "")
    if info.get("loggedOut") or not detected_alias:
        return {"ok": False, "blog_id": "", "reason": "네이버 로그아웃 상태"}
    if detected_alias != target_alias:
        return {
            "ok": False,
            "blog_id": detected_alias,
            "reason": f"다른 계정 로그인됨({detected_alias}, 기대: {target_alias})",
        }
    return {"ok": True, "blog_id": detected_alias, "reason": ""}


def load_draft(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    draft = json.loads(raw)
    for key in ("title", "body"):
        if not draft.get(key):
            raise ValueError(f"원고에 '{key}'가 없습니다")
    draft.setdefault("tags", [])
    draft.setdefault("images", [])
    return draft


def apply_author_signature(draft: dict, blog_id: str | None) -> dict:
    """계정에 고정 작성자 서명(accounts.py::author_signature/author_photo)이
    등록돼 있으면 본문 끝에 자동으로 붙인다.

    2026-08-24 사용자 요청 — skyjwshin 첫 글에서 수동으로 붙였던 걸(신재우
    자격증·경력 소개 + 증명사진) 앞으로는 매 글 자동으로 붙게 만들었다.
    CTA(주제마다 Claude가 새로 쓰는 것)와 달리 이건 글 내용과 무관하게
    항상 동일한 고정 텍스트라 재작성 대상이 아니다. 이미 붙어 있으면
    중복 삽입하지 않는다(재실행 안전).
    """
    from scripts.naver.blog.accounts import get_account

    account = get_account(blog_id)
    sig = account.get("author_signature")
    if sig and sig.strip() not in draft["body"]:
        draft["body"] = draft["body"].rstrip() + sig

    photo = account.get("author_photo")
    if photo and Path(photo).exists() and photo not in draft.get("images", []):
        draft.setdefault("images", []).append(photo)

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
    except Exception as e:  # noqa: BLE001 - 블로그 수동발행 CLI — CDP 상태조회 실패는 에러 dict 반환, 사용이미지 이력로드/playwright 종료 실패는 무시하고 계속(중복발행 방지 캐시는 부가기능, 발행 자체 실패는 아님)
        _log.debug("[manual] 사용 이미지 이력 로드 실패(무시): %s", e)

    slots = max(1, len(pool) // 3)
    # 제목 기반 결정적 구간 선택일 뿐 보안 용도 아님(bandit B324, 2026-09-29 확인).
    base = int(hashlib.md5(draft["title"].encode("utf-8"), usedforsecurity=False).hexdigest()[:8], 16) % slots
    for offset in range(slots):  # 이미 쓴 조합이면 다음 구간으로 밀어서 재시도
        picked = pick_3_images(pool, (base + offset) % slots)[:count]
        if not picked or not used.intersection(str(p) for p in picked):
            return picked
    return pick_3_images(pool, base)[:count]  # 전부 겹치면 어쩔 수 없이 반환


def publish(draft: dict, auto_images: bool = True, blog_id: str | None = None, approval: str | None = None) -> dict:
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
        result = publish_one(page, post=post, img_paths=images, approval=approval)
    finally:
        # playwright 인스턴스 정리(stop) 실패는 무시 — 리소스 정리 실패가 발행 결과에 영향 없음
        with contextlib.suppress(Exception):
            pw.stop()

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
        "--account", choices=list(BLOG_ACCOUNTS), default=None, help=f"대상 블로그 계정 (기본: {DEFAULT_ACCOUNT})"
    )
    ap.add_argument("--check", action="store_true", help="점검만 (기본)")
    ap.add_argument("--publish", action="store_true", help="실제 발행")
    from scripts.common.gate import CONFIRM_TEXTS

    ap.add_argument("--confirm", default=None, help=f"실제 발행 승인 문구(직접 입력): {CONFIRM_TEXTS['blog_publish']}")
    ap.add_argument("--no-images", action="store_true", help="이미지 자동 수집 끄기")
    ap.add_argument("--port", type=int, default=9222, help="CDP 포트")
    args = ap.parse_args()

    from scripts.naver.blog.accounts import get_account

    blog_id = get_account(args.account)["blog_id"]

    draft_path = Path(args.draft)
    draft = load_draft(draft_path)
    # 순서 중요: ensure_images()는 draft["images"]가 이미 채워져 있으면
    # 아예 수집을 건너뛴다. author_signature를 먼저 붙이면 작성자 사진
    # 하나만 들어간 상태로 "이미 채워짐" 취급돼 본문 사진 수집이 통째로
    # 스킵된다 — 반드시 본문 사진부터 모으고 나서 서명을 붙인다.
    ensure_images(draft, draft_path, auto_images=not args.no_images, blog_id=blog_id)
    before = json.dumps(draft, ensure_ascii=False, sort_keys=True)
    draft = apply_author_signature(draft, blog_id)
    if json.dumps(draft, ensure_ascii=False, sort_keys=True) != before:
        draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    seo = review(draft)

    if not args.publish:
        print("\n※ 실제 발행하려면 --publish --confirm=<승인 문구>")
        return

    from scripts.common.gate import GateBlocked, require_approved

    try:  # 로그인·이미지 작업 전에 승인 문구부터 확인한다
        require_approved("blog_publish", args.confirm, via="blog_publish_manual")
    except GateBlocked as exc:
        raise SystemExit(f"발행 차단: {exc.result.reason} (사용자가 직접 입력한 승인 문구가 필요합니다)") from exc

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
    result = publish(draft, auto_images=not args.no_images, blog_id=blog_id, approval=args.confirm)
    print(f"\n{'✅ 발행 완료' if result.get('ok') else '❌ 발행 실패'}  log_no={result.get('log_no', '')}")


if __name__ == "__main__":
    main()
