"""네이버 블로그 CLI 진입점 (BlogWriter 기반 완전 자동화).

input() / 터미널 대기 없음. AI가 모든 단계를 자동 수행.

승인 흐름:
  1) write  → 작성 + 발행 패널 열기 + 태그/공개설정 → awaiting_approval 반환
  2) confirm → 사용자 승인 후 호출 → 확인 버튼 클릭 → 발행 완료

CLI 사용 예:
  python scripts/entry/cdp_cli.py naver blog write \\
      --title="제목" --body="본문" --tags="태그1,태그2" \\
      --category="일상" --visibility=public

  python scripts/entry/cdp_cli.py naver blog confirm   # 승인 후 발행 확정

  python scripts/entry/cdp_cli.py naver blog draft \\
      --title="제목" --body="본문"
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def run(task: str, args: list[str]) -> None:
    """블로그 작업 실행.

    task: write | draft | confirm | publish(no-approval)
    """
    match task:
        case "write":
            _task_write(args, save_draft_only=False, require_approval=True)
        case "publish":
            # 승인 게이트 없이 즉시 발행 (내부 테스트용)
            _task_write(args, save_draft_only=False, require_approval=False)
        case "confirm":
            _task_confirm(args)
        case "draft":
            _task_write(args, save_draft_only=True, require_approval=False)
        case _:
            print(f"  [오류] 알 수 없는 작업: {task}")
            print("  사용법: naver blog [write|draft|confirm] --title=제목 --body=본문")


# ── 인수 파싱 헬퍼 ────────────────────────────────────────────────────────────

def _opt(args: list[str], prefix: str) -> str | None:
    for a in args:
        if str(a).startswith(prefix):
            return str(a).split("=", 1)[1]
    return None


def _flag(args: list[str], name: str) -> bool:
    return name in [str(a) for a in args]


# ── 작성 실행 ─────────────────────────────────────────────────────────────────

def _task_write(args: list[str], save_draft_only: bool = False,
                require_approval: bool = True) -> None:
    """BlogWriter를 사용해 블로그 글 자동 작성.

    require_approval=True(기본): 발행 패널 열어둔 채로 awaiting_approval 반환.
    save_draft_only=True: 임시저장만.
    """
    from scripts.browser.cdp.connection import get_page
    from scripts.naver.blog.writer import write_post

    # 인수 파싱
    title     = _opt(args, "--title=") or ""
    body_file = _opt(args, "--body-file=")
    body      = Path(body_file).read_text(encoding="utf-8") if body_file else (_opt(args, "--body=") or "")
    category  = _opt(args, "--category=")
    tags_raw  = _opt(args, "--tags=") or ""
    tags      = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
    brand_raw = _opt(args, "--brand-tags=") or ""
    brand_tags = [t.strip() for t in brand_raw.split(",") if t.strip()] if brand_raw else None
    visibility = _opt(args, "--visibility=") or "public"
    dry_run   = _flag(args, "--dry-run")

    if not title:
        print("  [오류] --title=제목 필수")
        return
    if not body:
        print("  [오류] --body=본문 또는 --body-file=경로 필수")
        return

    mode = "임시저장" if save_draft_only else ("승인 대기" if require_approval else "즉시 발행")
    print(f"\n[작업] 네이버 블로그 글 {mode}")
    print(f"  제목     : {title[:60]}")
    print(f"  본문     : {body[:80]}{'…' if len(body) > 80 else ''}")
    print(f"  태그     : {', '.join(tags) or '자동 생성'}")
    print(f"  카테고리 : {category or '없음'}")
    print(f"  공개설정 : {visibility}")
    print(f"  모드     : {mode}")

    if dry_run:
        result: dict[str, Any] = {
            "ok": True,
            "mode": "dry_run",
            "title": title,
            "body_len": len(body),
            "tags": tags,
            "category": category,
            "visibility": visibility,
            "save_draft_only": save_draft_only,
            "require_approval": require_approval,
        }
        _save_and_print(result, "naver_blog_write_latest.json")
        return

    page = get_page()
    result = write_post(
        page,
        title=title,
        body=body,
        category=category,
        tags=tags if tags else None,
        brand_tags=brand_tags,
        visibility=visibility,
        save_draft_only=save_draft_only,
        require_approval=require_approval,
    )

    _save_and_print(result, "naver_blog_write_latest.json")

    if result.get("mode") == "awaiting_approval":
        s = result.get("summary", {})
        print("\n" + "=" * 60)
        print("  ★ 발행 승인 요청")
        print(f"  제목    : {s.get('title', '')}")
        print(f"  태그    : {', '.join(s.get('tags', []))}")
        print(f"  공개    : {s.get('visibility', '')}")
        print(f"  미리보기: {s.get('body_preview', '')[:80]}")
        print("=" * 60)
        print("  → 브라우저에서 내용을 확인한 뒤")
        print("  → 'naver blog confirm' 명령으로 발행을 확정하세요.")
    elif result.get("ok"):
        print(f"\n  ✓ {mode} 완료")
        if result.get("url"):
            print(f"  URL: {result['url']}")
    else:
        print(f"\n  ✗ {mode} 실패: {result.get('error', 'unknown')}")


def _task_confirm(args: list[str]) -> None:
    """발행 패널이 열린 상태에서 최종 발행 버튼 클릭 (사용자 승인 확정).

    write_post(..., require_approval=True) 결과 확인 후 호출.
    브라우저는 동일 세션이어야 한다.
    """
    from scripts.browser.cdp.connection import get_page
    from scripts.naver.blog.writer import confirm_publish

    dry_run = _flag(args, "--dry-run")
    if dry_run:
        print("  [dry-run] confirm_publish 호출 생략")
        return

    print("\n[작업] 블로그 발행 확정 (승인 완료)")
    page = get_page()
    result = confirm_publish(page)
    _save_and_print(result, "naver_blog_write_latest.json")

    if result.get("ok"):
        print("\n  ✓ 발행 완료")
        if result.get("url"):
            print(f"  URL: {result['url']}")
    else:
        print(f"\n  ✗ 발행 실패: {result.get('error', 'unknown')}")


def _save_and_print(payload: dict, name: str) -> None:
    path = Path("data") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved: {path}")
