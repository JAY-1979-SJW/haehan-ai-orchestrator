"""네이버 블로그 CLI 진입점 (BlogWriter 기반 완전 자동화).

input() / 터미널 대기 없음. AI가 모든 단계를 자동 수행.

CLI 사용 예:
  python scripts/cdp_client.py naver blog write \\
      --title="제목" --body="본문" --tags="태그1,태그2" \\
      --category="일상" --visibility=public

  python scripts/cdp_client.py naver blog draft \\
      --title="제목" --body="본문"
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def run(task: str, args: list[str]) -> None:
    """블로그 작업 실행.

    task: write | draft | publish
    """
    match task:
        case "write" | "publish":
            _task_write(args, save_draft_only=False)
        case "draft":
            _task_write(args, save_draft_only=True)
        case _:
            print(f"  [오류] 알 수 없는 작업: {task}")
            print("  사용법: naver blog [write|draft] --title=제목 --body=본문 [--tags=태그1,태그2] [--category=카테고리] [--visibility=public]")


# ── 인수 파싱 헬퍼 ────────────────────────────────────────────────────────────

def _opt(args: list[str], prefix: str) -> str | None:
    for a in args:
        if str(a).startswith(prefix):
            return str(a).split("=", 1)[1]
    return None


def _flag(args: list[str], name: str) -> bool:
    return name in [str(a) for a in args]


# ── 작성 실행 ─────────────────────────────────────────────────────────────────

def _task_write(args: list[str], save_draft_only: bool = False) -> None:
    """BlogWriter를 사용해 블로그 글 자동 작성·발행."""
    from scripts.web_connector import get_page
    from scripts.naver.blog.writer import write_post

    # 인수 파싱
    title    = _opt(args, "--title=") or ""
    body     = _opt(args, "--body=") or ""
    category = _opt(args, "--category=")
    tags_raw = _opt(args, "--tags=") or ""
    tags     = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
    visibility = _opt(args, "--visibility=") or "public"
    dry_run  = _flag(args, "--dry-run")

    if not title:
        print("  [오류] --title=제목 필수")
        return
    if not body:
        print("  [오류] --body=본문 필수")
        return

    mode = "임시저장" if save_draft_only else "즉시 발행"
    print(f"\n[작업] 네이버 블로그 글 {mode}")
    print(f"  제목     : {title[:60]}")
    print(f"  본문     : {body[:80]}{'…' if len(body) > 80 else ''}")
    print(f"  태그     : {', '.join(tags) or '없음'}")
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
        visibility=visibility,
        save_draft_only=save_draft_only,
    )

    _save_and_print(result, "naver_blog_write_latest.json")

    if result.get("ok"):
        print(f"\n  ✓ {mode} 완료")
        if result.get("url"):
            print(f"  URL: {result['url']}")
    else:
        print(f"\n  ✗ {mode} 실패: {result.get('error', 'unknown')}")


def _save_and_print(payload: dict, name: str) -> None:
    path = Path("data") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved: {path}")
