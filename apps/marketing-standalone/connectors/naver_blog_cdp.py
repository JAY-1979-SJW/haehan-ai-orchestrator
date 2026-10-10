"""CDP 로그인 + 발행 루프.

원본: scripts/naver/blog/marketing/publish.py. accounts/topics 의존은
이 앱의 사본(../core/blog_accounts.py, ../core/topic_dedup.py)으로 교체했다.

2026-09-12: Phase 1b 완료 — 실제 에디터 조작은 connectors/naver_writer.py
(원본 scripts/naver/blog/core/writer.py 사본)로 포팅했다. 다만 로그인은
원본(scripts/naver/common/auth.py, scripts/auth/credentials.py — 저장된 비밀번호로 자동
재로그인)을 그대로 가져오지 **않았다** — 이 독립 앱은 고객의 네이버 비밀번호를
절대 저장하지 않는다는 설계 원칙이라, 로그인 상태만 확인하고 안 맞으면 사용자
에게 브라우저에서 직접 로그인하라고 안내한다(자동 로그아웃/재로그인 없음).

⚠️ 실제 배포 전 라이브 발행 1건으로 검증 필수.
"""

from __future__ import annotations

import sys as _sys
import time
from datetime import datetime
from pathlib import Path as _Path

_APP_ROOT = _Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(_APP_ROOT))
from core.blog_accounts import DEFAULT_ACCOUNT, get_account  # noqa: E402
from core.topic_dedup import save_cache, topic_key  # noqa: E402


def connect_and_ensure_login(cdp_url: str = "http://localhost:9222", blog_id: str = DEFAULT_ACCOUNT):
    """CDP 연결 + 대상 블로그 계정(blog_id) 로그인 상태 확인. Returns: (playwright, browser, page).

    자동 로그인/재로그인은 하지 않는다(고객 비밀번호 미보관). 계정이 다르면
    browser=None을 반환하니, 호출부가 사용자에게 직접 로그인하라고 안내해야 한다.
    """
    from playwright.sync_api import sync_playwright

    target_alias = get_account(blog_id).get("public_alias") or blog_id

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(cdp_url)
    page = browser.contexts[0].pages[0]
    print(f"\n[CDP] 연결됨: {page.url}")

    page.goto("https://section.blog.naver.com/BlogHome.naver", wait_until="domcontentloaded", timeout=15000)
    time.sleep(2)
    detected_alias = page.evaluate(
        """() => {
            const a = document.querySelector('a[href*="admin.blog.naver.com/"]');
            if (!a) return null;
            const m = a.href.match(/admin\\.blog\\.naver\\.com\\/([a-zA-Z0-9_-]+)\\//);
            return m ? m[1] : null;
        }"""
    )
    print(f"[로그인] 현재 블로그 주소: {detected_alias}")

    if detected_alias != target_alias:
        print(f"  ❌ 로그인 계정 불일치 (현재: {detected_alias}, 기대: {target_alias})")
        print("     브라우저에서 직접 로그인한 뒤 다시 실행해주세요 (setup_gui.py의 '네이버 로그인 열기' 버튼).")
        browser.close()
        pw.stop()
        return pw, None, None

    return pw, browser, page


def publish_one(page, *, post: dict, img_paths: list[str]) -> dict:
    """포스트 1건 발행. body_segments + images로 이미지를 글 중간에 배치."""
    from connectors.naver_writer import write_post

    segments = post.get("body_segments") or []
    try:
        result = write_post(
            page,
            title=post["title"],
            body=post["body"],
            body_segments=segments if segments else None,
            tags=post["tags"],
            images=img_paths,
            visibility=post.get("visibility", "public"),
            require_approval=False,
        )
        ok = result.get("ok", False)
        log_no = result.get("log_no", "")
        print(f"  발행: {'✅ 성공' if ok else '❌ 실패'} log_no={log_no}")
    except Exception as e:  # noqa: BLE001 - 네이버 블로그 발행 CDP 작업 실패를 캡처해 ok=False, log_no='' 로 안전하게 처리 - 실패를 성공으로 위장하지 않음
        ok = False
        log_no = ""
        print(f"  발행 오류: {e}")

    return {"ok": ok, "log_no": log_no}


def record_success(
    cache: dict, *, topic: str, post: dict, log_no: str, img_paths: list[str], blog_id: str = DEFAULT_ACCOUNT
) -> None:
    entry = {
        "key": topic_key(post["title"]),
        "topic": topic,
        "title": post["title"],
        "tags": post["tags"],
        "log_no": log_no,
        "posted_at": datetime.now().isoformat(),
    }
    cache.setdefault("posted", []).append(entry)
    save_cache(cache, blog_id)
    print(f"  캐시 저장 ({len(cache['posted'])}개 누적, 계정: {blog_id})")
