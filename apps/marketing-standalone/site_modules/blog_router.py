"""사람이 작성한 원고를 네이버 블로그에 발행한다 (CLI).

원본: scripts/naver/blog/cli/blog_publish_manual.py. accounts/images/topics
의존을 전부 이 앱 사본으로 교체했다. 발행 로직 자체(connectors/naver_blog_cdp.py)는
Phase 1b 전까지 원본 저장소의 writer.py/auth.py에 브리지된 상태다
(naver_blog_cdp.py 상단 docstring 참조).

사용:
    python blog_router.py draft.json --check
    python blog_router.py draft.json --publish
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys as _sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(_APP_ROOT))

from _bootstrap import get_logger  # noqa: E402
from core import ai_writer  # noqa: E402
from core.blog_accounts import DEFAULT_ACCOUNT, get_account  # noqa: E402
from core.content_rules import seo_check, split_body  # noqa: E402
from core.license_check import verify_license  # noqa: E402

_log = get_logger(__name__)

_LICENSE_PATH = _APP_ROOT / "config" / "license.txt"


def _check_license() -> bool:
    if not _LICENSE_PATH.exists():
        return False
    return verify_license(_LICENSE_PATH.read_text(encoding="utf-8").strip())


def verify_login(port: int = 9222, blog_id: str | None = None) -> dict:
    """발행 전 네이버 로그인 상태를 미리 확인한다. 자동 재로그인은 시도하지
    않는다 — 캡차는 사람만 풀 수 있다."""
    from connectors.cdp_helper import CDP

    account = get_account(blog_id)
    target_alias = account.get("public_alias") or account["blog_id"]

    cdp = None
    try:
        cdp = CDP(port=port)
        cdp.navigate("https://section.blog.naver.com/BlogHome.naver", wait=3)
        import time as _time

        _time.sleep(1.5)
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
    except Exception as e:  # noqa: BLE001 - 블로그 CDP 상태조회/사용이미지 이력로드/playwright 종료 처리 — 각 except는 상태확인 실패를 에러 dict로 반환하거나 이력로드 실패를 무시하고 빈 이력으로 계속 진행할 뿐, 발행 자체를 승인 없이 강행하지 않음
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
    if path.suffix.lower() != ".json":
        raise ValueError(f"원고 파일은 .json이어야 합니다: {path}")
    if not path.is_file():
        raise ValueError(f"원고 파일을 찾을 수 없습니다: {path}")
    raw = path.read_text(encoding="utf-8")
    draft = json.loads(raw)
    for key in ("title", "body"):
        if not draft.get(key):
            raise ValueError(f"원고에 '{key}'가 없습니다")
    draft.setdefault("tags", [])
    draft.setdefault("images", [])
    return draft


def review(draft: dict) -> dict:
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
    if draft.get("images") or not auto_images:
        return draft.get("images", [])
    images = collect_images(draft, blog_id=blog_id)
    if images:
        draft["images"] = images
        draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        _log.info("[manual] 이미지 %d장 확보 후 원고에 저장: %s", len(images), draft_path)
    return images


def collect_images(draft: dict, count: int = 3, blog_id: str | None = None) -> list[str]:
    given = [str(p) for p in draft.get("images", []) if Path(p).exists()]
    if given:
        return given

    from connectors.blog_images import fetch_unsplash_images, pick_3_images
    from core.topic_dedup import load_cache

    pool = fetch_unsplash_images(count_per_query=3)
    if not pool:
        _log.warning("[manual] Unsplash 이미지 수집 실패 — 이미지 없이 발행")
        return []

    used: set[str] = set()
    try:
        for p in load_cache(blog_id).get("posted", []):
            for path in p.get("img_paths", []) or []:
                used.add(str(path))
    except Exception as e:  # noqa: BLE001 - 블로그 CDP 상태조회/사용이미지 이력로드/playwright 종료 처리 — 각 except는 상태확인 실패를 에러 dict로 반환하거나 이력로드 실패를 무시하고 빈 이력으로 계속 진행할 뿐, 발행 자체를 승인 없이 강행하지 않음
        _log.debug("[manual] 사용 이미지 이력 로드 실패(무시): %s", e)

    slots = max(1, len(pool) // 3)
    base = int(hashlib.md5(draft["title"].encode("utf-8"), usedforsecurity=False).hexdigest()[:8], 16) % slots
    for offset in range(slots):
        picked = pick_3_images(pool, (base + offset) % slots)[:count]
        if not picked or not used.intersection(str(p) for p in picked):
            return picked
    return pick_3_images(pool, base)[:count]


def publish(draft: dict, auto_images: bool = True, blog_id: str | None = None) -> dict:
    from connectors.naver_blog_cdp import connect_and_ensure_login, publish_one, record_success
    from core.topic_dedup import load_cache

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
        "visibility": draft.get("visibility", "public"),
    }
    pw, _browser, page = connect_and_ensure_login(blog_id=target_blog_id)
    try:
        result = publish_one(page, post=post, img_paths=images)
    finally:
        try:
            pw.stop()
        except Exception as e:  # noqa: BLE001 - 블로그 CDP 상태조회/사용이미지 이력로드/playwright 종료 처리 — 각 except는 상태확인 실패를 에러 dict로 반환하거나 이력로드 실패를 무시하고 빈 이력으로 계속 진행할 뿐, 발행 자체를 승인 없이 강행하지 않음
            _log.debug("playwright stop 실패(무시): %s", e)

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


def generate_draft(topic: str, keywords: list[str] | None = None, length: str = "medium") -> dict:
    """AI로 주제 → {title, body, tags} 초안 생성. site_modules 진입점(설정화면 연동)."""
    return ai_writer.draft(topic, keywords=keywords, length=length)


def main() -> None:
    if not _check_license():
        print("❌ 라이선스가 등록되지 않았습니다. setup_gui.py를 먼저 실행해 라이선스를 인증해주세요.")
        return

    ap = argparse.ArgumentParser()
    ap.add_argument("draft", nargs="?", help="원고 JSON 경로 (--topic 사용 시 생략 가능)")
    ap.add_argument("--topic", default=None, help="AI로 초안을 새로 생성할 주제 (draft.json 대신 사용)")
    ap.add_argument("--keywords", default="", help="--topic 사용 시 콤마구분 키워드")
    ap.add_argument("--length", default="medium", choices=["short", "medium", "long"])
    ap.add_argument("--account", default=None, help=f"대상 블로그 계정 (기본: {DEFAULT_ACCOUNT})")
    ap.add_argument("--check", action="store_true", help="점검만 (기본)")
    ap.add_argument("--publish", action="store_true", help="실제 발행")
    ap.add_argument("--no-images", action="store_true", help="이미지 자동 수집 끄기")
    ap.add_argument("--port", type=int, default=9222, help="CDP 포트")
    args = ap.parse_args()

    blog_id = get_account(args.account)["blog_id"]

    if args.topic:
        keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
        gen = generate_draft(args.topic, keywords=keywords, length=args.length)
        if not gen.get("ok"):
            print(f"❌ AI 초안 생성 실패: {gen.get('error')}")
            if gen.get("hint"):
                print(f"   {gen['hint']}")
            return
        draft_path = Path(f"draft_{blog_id}_auto.json")
        draft_path.write_text(
            json.dumps(
                {"title": gen["title"], "body": gen["body"], "tags": gen["tags"], "topic": args.topic},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"✅ AI 초안 생성 완료 → {draft_path}")
    elif args.draft:
        draft_path = Path(args.draft)
    else:
        print("❌ draft.json 경로 또는 --topic 중 하나는 필요합니다.")
        return

    draft = load_draft(draft_path)
    ensure_images(draft, draft_path, auto_images=not args.no_images, blog_id=blog_id)
    review(draft)

    if not args.publish:
        print("\n※ 실제 발행하려면 --publish")
        return

    login = verify_login(port=args.port, blog_id=blog_id)
    if not login["ok"]:
        print(f"\n❌ 발행 중단 — {login['reason']}")
        print(f"   브라우저에서 {blog_id} 계정으로 직접 로그인한 뒤 다시 실행하세요.")
        return

    result = publish(draft, auto_images=not args.no_images, blog_id=blog_id)
    if result.get("ok"):
        print(f"\n✅ 발행 완료: log_no={result.get('log_no')}")
    else:
        print(f"\n❌ 발행 실패: {result}")


if __name__ == "__main__":
    main()
