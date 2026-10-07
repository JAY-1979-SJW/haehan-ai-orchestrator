"""네이버 카페/캘린더/마이박스 명령 핸들러"""

from __future__ import annotations

import json
from typing import Any

from scripts.common.gate import check as gate_check
from scripts.naver.common.router_common import (
    _flag,
    _int_option,
    _option_phrase,
    _option_value,
    _parse_datetime_arg,
    _print_saved,
    _save_latest,
)


def _cafe_list(args: list[str]) -> None:
    """cafe list/cafes."""
    from datetime import datetime
    from pathlib import Path

    gate_check("scan_page")
    from scripts.naver.cafe import list_background_runner

    strict_domain = "--strict-domain" in args
    report = list_background_runner.collect_background(
        allow_mixed_readonly=not strict_domain,
        per_page=_int_option(args, "--per-page=", 100),
    )
    if not report.ok:
        raise SystemExit(json.dumps(report.to_dict(), ensure_ascii=False))
    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cafes": report.cafes,
        "favorites": report.favorites,
        "manages": report.manages,
        "joined_total": report.joined_total,
        "favorite_total": report.favorite_total,
        "manage_total": report.manage_total,
        "readonly": True,
        "attach_only": True,
        "browser_launch": False,
        "browser_close": False,
    }
    path = Path("data/naver_cafes_latest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"saved: {path}")


def _cafe_home(args: list[str]) -> None:
    """cafe home/main."""
    from datetime import datetime
    from pathlib import Path

    gate_check("scan_page")
    from scripts.naver.cafe import list_background_runner

    strict_domain = "--strict-domain" in args
    report = list_background_runner.collect_main_background(
        allow_mixed_readonly=not strict_domain,
    )
    if not report.ok:
        raise SystemExit(json.dumps(report.to_dict(), ensure_ascii=False))
    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        **report.to_dict(),
        "readonly": True,
        "attach_only": True,
        "browser_launch": False,
        "browser_close": False,
    }
    path = Path("data/naver_cafe_main_latest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"saved: {path}")


def _cafe_topic_search(args: list[str]) -> None:
    """cafe topic-search."""
    from datetime import datetime
    from pathlib import Path

    gate_check("scan_page")
    from scripts.naver.cafe import list_background_runner

    strict_domain = "--strict-domain" in args
    query = _option_phrase(args, "--query=") or _option_value(args, "--keywords=") or ""
    report = list_background_runner.collect_topic_search_background(
        allow_mixed_readonly=not strict_domain,
        keywords=query,
        limit_per_keyword=_int_option(args, "--limit=", 10),
    )
    if not report.ok:
        raise SystemExit(json.dumps(report.to_dict(), ensure_ascii=False))
    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        **report.to_dict(),
        "readonly": True,
        "attach_only": True,
        "browser_launch": False,
        "browser_close": False,
    }
    path = Path("data/naver_cafe_topic_search_latest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"saved: {path}")


def _cafe_join_submit(args: list[str]) -> None:
    """cafe join-submit(승인 게이트)."""
    from datetime import datetime
    from pathlib import Path

    from scripts.naver.cafe.join_request import APPROVAL_CONFIRM_TEXT

    cafe_url = (
        _option_value(args, "--cafe-url=")
        or _option_value(args, "--cafe=")
        or (args[0] if args and not str(args[0]).startswith("--") else "")
    )
    approved = "--approved" in args
    confirm = _option_value(args, "--confirm=") or ""
    approved_by = _option_value(args, "--approved-by=") or "operator"
    if not cafe_url:
        raise SystemExit("cafe join-submit requires --cafe-url=CAFE")
    if not approved or confirm != APPROVAL_CONFIRM_TEXT:
        raise SystemExit(f"cafe join-submit requires --approved --confirm={APPROVAL_CONFIRM_TEXT}")
    gate_check(
        "naver_cafe_join_submit",
        risk="approve",
        force=True,
        service="naver_cafe",
        cafe_url=cafe_url,
        approved_by=approved_by,
    )
    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ok": True,
        "cafe_url": cafe_url,
        "approval_gate": "naver_cafe_join_submit",
        "approved_by": approved_by,
        "browser_submit_executed": False,
        "final_click_adapter_required": True,
        "message": "Join submit approval gate passed; final browser click must be executed by a visible-form adapter.",
    }
    safe_cafe = "".join(ch for ch in cafe_url if ch.isalnum() or ch in ("_", "-")) or "cafe"
    path = Path(f"data/naver_cafe_{safe_cafe}_join_submit_latest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"saved: {path}")


def _cafe_join_request(args: list[str]) -> None:
    """cafe join-request(준비 전용)."""
    from datetime import datetime
    from pathlib import Path

    gate_check("scan_page")
    from scripts.naver.cafe import list_background_runner

    strict_domain = "--strict-domain" in args
    cafe_url = (
        _option_value(args, "--cafe-url=")
        or _option_value(args, "--cafe=")
        or (args[0] if args and not str(args[0]).startswith("--") else "")
    )
    if not cafe_url:
        raise SystemExit("cafe join-request requires --cafe-url=CAFE")
    nickname = _option_phrase(args, "--nickname=") or ""
    purpose = _option_phrase(args, "--purpose=") or ""
    answers = {}
    for arg in args:
        text = str(arg)
        if text.startswith("--answer=") and ":" in text:
            key, value = text.split("=", 1)[1].split(":", 1)
            answers[key.strip()] = value.strip()
    report = list_background_runner.collect_joined_cafe_background(
        cafe_url=cafe_url,
        mode="join-request",
        allow_mixed_readonly=not strict_domain,
        nickname=nickname,
        purpose=purpose,
        answers=answers,
    )
    if not report.ok:
        raise SystemExit(json.dumps(report.to_dict(), ensure_ascii=False))
    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        **report.to_dict(),
        "readonly": False,
        "prepare_only": True,
        "approval_required": True,
        "final_submit_blocked": True,
        "attach_only": True,
        "browser_launch": False,
        "browser_close": False,
    }
    safe_cafe = "".join(ch for ch in cafe_url if ch.isalnum() or ch in ("_", "-")) or "cafe"
    path = Path(f"data/naver_cafe_{safe_cafe}_join_request_latest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"saved: {path}")


def _cafe_collect(sub: str, args: list[str]) -> None:
    """cafe collect/boards."""
    from datetime import datetime
    from pathlib import Path

    gate_check("scan_page")
    from scripts.naver.cafe import list_background_runner

    strict_domain = "--strict-domain" in args
    cafe_url = (
        _option_value(args, "--cafe-url=")
        or _option_value(args, "--cafe=")
        or (args[0] if args and not str(args[0]).startswith("--") else "soho")
    )
    mode = "boards" if sub in ("boards", "collect-boards") or "--boards" in args else "home"
    report = list_background_runner.collect_joined_cafe_background(
        cafe_url=cafe_url,
        mode=mode,
        allow_mixed_readonly=not strict_domain,
    )
    if not report.ok:
        raise SystemExit(json.dumps(report.to_dict(), ensure_ascii=False))
    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        **report.to_dict(),
        "readonly": True,
        "attach_only": True,
        "browser_launch": False,
        "browser_close": False,
    }
    suffix = "boards" if mode == "boards" else "collect"
    safe_cafe = "".join(ch for ch in cafe_url if ch.isalnum() or ch in ("_", "-")) or "cafe"
    path = Path(f"data/naver_cafe_{safe_cafe}_{suffix}_latest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"saved: {path}")


def _cafe_posts(args: list[str]) -> None:
    """cafe posts."""
    from datetime import datetime

    from scripts.naver.cafe import NaverCafe
    from scripts.browser.cdp.connection import get_page

    gate_check("scan_page")
    cafe_url = _option_value(args, "--cafe-url=") or (args[0] if args and not str(args[0]).startswith("--") else "")
    board_no = _option_value(args, "--board-no=") or _option_value(args, "--board=") or ""
    limit = _int_option(args, "--limit=", 30)
    if not cafe_url:
        raise SystemExit("cafe posts requires --cafe-url=URL [--board-no=N] [--limit=30]")
    page = get_page()
    posts = NaverCafe(page).list_posts(cafe_url=cafe_url, board_no=board_no, limit=limit)
    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cafe_url": cafe_url,
        "board_no": board_no,
        "posts": posts,
    }
    _print_saved(out, _save_latest("naver_cafe_posts_latest.json", out))


def _cafe_read(args: list[str]) -> None:
    """cafe read."""
    from datetime import datetime

    from scripts.naver.cafe import NaverCafe
    from scripts.browser.cdp.connection import get_page

    gate_check("scan_page")
    post_url = (
        _option_value(args, "--post-url=")
        or _option_value(args, "--url=")
        or (args[0] if args and not str(args[0]).startswith("--") else "")
    )
    if not post_url:
        raise SystemExit("cafe read requires --post-url=URL")
    page = get_page()
    post = NaverCafe(page).read_post(post_url)
    out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "post_url": post_url, "post": post}
    _print_saved(out, _save_latest("naver_cafe_post_latest.json", out))


def _cafe_write(sub: str, args: list[str]) -> None:
    """cafe write/prepare-post/publish (승인 게이트 포함)."""
    from scripts.naver.cafe import NaverCafe
    from scripts.naver.common.content import (
        APPROVAL_CONFIRM_TEXT,
        build_cafe_write_plan,
        save_cafe_submit_record,
        save_cafe_write_plan,
    )
    from scripts.browser.cdp.connection import get_page

    if sub not in ("write", "prepare-post", "publish"):
        print(
            "usage: python scripts/entry/cdp_cli.py naver cafe [list|home|topic-search|join-request|collect|boards|posts|read|write|publish] ..."
        )
        return

    cafe_url = _option_value(args, "--cafe-url=") or ""
    board_no = _option_value(args, "--board-no=") or ""
    # 새 글쓰기 구현(cafe/write/writer.py)은 게시판을 번호가 아니라 이름으로 고른다.
    board_name = _option_value(args, "--board-name=") or ""
    title = _option_value(args, "--title=") or ""
    body = _option_value(args, "--body=") or ""
    dry_run = "--dry-run" in args
    publish = sub == "publish" or "--publish" in args
    approved = "--approved" in args
    confirm = _option_value(args, "--confirm=") or ""
    approved_by = _option_value(args, "--approved-by=") or "operator"

    if not cafe_url or not (board_no or board_name) or not title:
        raise SystemExit("cafe write requires --cafe-url, --board-name, --title, and optional --body")
    if not dry_run and not board_name:
        raise SystemExit("cafe write requires --board-name=게시판이름 (--board-no 만으로는 게시판을 고를 수 없음)")
    if publish and (not approved or confirm != APPROVAL_CONFIRM_TEXT):
        raise SystemExit(f"cafe publish requires --approved --confirm={APPROVAL_CONFIRM_TEXT}")

    if publish:
        gate_check("blog_publish", force=approved, service="naver_cafe", cafe_url=cafe_url, board_no=board_no)
    else:
        gate_check("type_into", service="naver_cafe", cafe_url=cafe_url, board_no=board_no)

    plan = build_cafe_write_plan(
        cafe_url=cafe_url,
        board_no=board_no,
        title=title,
        body=body,
        publish=publish,
        approved_by=approved_by,
        dry_run=dry_run,
    )
    save_cafe_write_plan(plan)

    if dry_run:
        record = {**plan, "ok": True, "prepared": False, "published": False, "note": "dry-run only; no browser write"}
    else:
        page = get_page()
        # publish 는 위에서 --approved + 확인 문구를 통과한 경우에만 True — 그때만 승인 대기 없이 발행한다.
        result = NaverCafe(page).write_post(
            cafe_url=cafe_url, board_name=board_name, title=title, body=body, require_approval=not publish
        )
        ok = bool(result.get("ok"))
        record = {
            **plan,
            "ok": ok,
            "prepared": ok,
            # 임시저장 경로는 mode=awaiting_approval, 직접 발행 성공은 {"ok": True, "url": ...}
            "published": ok and publish and result.get("mode") != "awaiting_approval",
            "result": result,
        }
    path = save_cafe_submit_record(record)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    print(f"saved: {path}")


def _cmd_cafe(sub: str, args: list[str]) -> None:
    if sub in ("list", "cafes"):
        _cafe_list(args)
        return

    if sub in ("home", "main", "main-page"):
        _cafe_home(args)
        return

    if sub in ("topic-search", "search", "topics"):
        _cafe_topic_search(args)
        return

    if sub in ("join-submit", "join-approve"):
        _cafe_join_submit(args)
        return

    if sub in ("join", "join-request", "join-prepare", "approval-request"):
        _cafe_join_request(args)
        return

    if sub in ("collect", "collect-home", "member-collect", "boards", "collect-boards"):
        _cafe_collect(sub, args)
        return

    if sub in ("posts", "list-posts", "articles"):
        _cafe_posts(args)
        return

    if sub in ("read", "read-post", "post"):
        _cafe_read(args)
        return

    _cafe_write(sub, args)


def _cmd_calendar(sub: str, args: list[str]) -> None:
    from datetime import datetime

    from scripts.naver.common.calendar_tasks import NaverCalendar
    from scripts.browser.cdp.connection import get_page

    if sub in ("list", "events"):
        gate_check("scan_page")
        events = NaverCalendar(get_page()).list_events()
        out: dict[str, Any] = {"generated_at": datetime.now().isoformat(timespec="seconds"), "events": events}
        _print_saved(out, _save_latest("naver_calendar_events_latest.json", out))
        return

    if sub not in ("add", "prepare", "save"):
        print(
            "usage: python scripts/entry/cdp_cli.py naver calendar [list|add] --title=TITLE --start=ISO [--end=ISO] [--dry-run|--execute] [--save --approved --confirm=NAVER_APPROVED_SAVE]"
        )
        return

    title = _option_value(args, "--title=") or ""
    start_raw = _option_value(args, "--start=") or ""
    end_raw = _option_value(args, "--end=") or ""
    location = _option_value(args, "--location=") or ""
    memo = _option_value(args, "--memo=") or ""
    save = sub == "save" or _flag(args, "--save")
    dry_run = _flag(args, "--dry-run") or not _flag(args, "--execute")
    approved = _flag(args, "--approved")
    confirm = _option_value(args, "--confirm=") or ""

    if not title or not start_raw:
        raise SystemExit("calendar add requires --title=TITLE --start=ISO")
    if save and (not approved or confirm != "NAVER_APPROVED_SAVE"):
        raise SystemExit("calendar save requires --approved --confirm=NAVER_APPROVED_SAVE")

    plan = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "calendar_add",
        "title": title,
        "start": start_raw,
        "end": end_raw,
        "location": location,
        "memo_present": bool(memo),
        "dry_run": dry_run,
        "save_requested": save,
        "approval_required": save,
    }
    if dry_run:
        out = {**plan, "ok": True, "note": "dry-run only; no browser write"}
        _print_saved(out, _save_latest("naver_calendar_add_latest.json", out))
        return

    gate_check("blog_publish" if save else "type_into", force=approved, service="naver_calendar")
    result = NaverCalendar(get_page()).add_event(
        title=title,
        start=_parse_datetime_arg(start_raw, "--start"),
        end=_parse_datetime_arg(end_raw, "--end") if end_raw else None,
        location=location,
        memo=memo,
        confirm=save,
    )
    out = {**plan, "ok": bool(result.get("ok")), "result": result}
    _print_saved(out, _save_latest("naver_calendar_add_latest.json", out))


def _cmd_mybox(sub: str, args: list[str]) -> None:
    from datetime import datetime
    from pathlib import Path

    from scripts.naver.common.mybox import NaverMyBox
    from scripts.browser.cdp.connection import get_page

    if sub in ("list", "files"):
        gate_check("scan_page")
        limit = _int_option(args, "--limit=", 50)
        items = NaverMyBox(get_page()).list_files(limit=limit)
        out: dict[str, Any] = {"generated_at": datetime.now().isoformat(timespec="seconds"), "files": items}
        _print_saved(out, _save_latest("naver_mybox_files_latest.json", out))
        return

    if sub == "search":
        gate_check("scan_page")
        query = _option_value(args, "--query=") or " ".join(a for a in args if not str(a).startswith("--"))
        if not query:
            raise SystemExit("mybox search requires --query=TEXT")
        items = NaverMyBox(get_page()).search(query)
        out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "query": query, "files": items}
        _print_saved(out, _save_latest("naver_mybox_search_latest.json", out))
        return

    if sub != "upload":
        print("usage: python scripts/entry/cdp_cli.py naver mybox [list|search|upload] ...")
        return

    local_path = (
        _option_value(args, "--file=")
        or _option_value(args, "--path=")
        or (args[0] if args and not str(args[0]).startswith("--") else "")
    )
    dry_run = _flag(args, "--dry-run") or not _flag(args, "--execute")
    approved = _flag(args, "--approved")
    confirm = _option_value(args, "--confirm=") or ""
    if not local_path:
        raise SystemExit("mybox upload requires --file=PATH")
    if not Path(local_path).exists():
        raise SystemExit(f"upload file not found: {local_path}")
    if not dry_run and (not approved or confirm != "NAVER_APPROVED_UPLOAD"):
        raise SystemExit("mybox upload execute requires --approved --confirm=NAVER_APPROVED_UPLOAD")

    plan = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow": "mybox_upload",
        "file_name": Path(local_path).name,
        "file_size": Path(local_path).stat().st_size,
        "dry_run": dry_run,
        "approval_required": True,
    }
    if dry_run:
        out = {**plan, "ok": True, "note": "dry-run only; no browser upload"}
        _print_saved(out, _save_latest("naver_mybox_upload_latest.json", out))
        return

    gate_check("blog_publish", force=approved, service="naver_mybox", file=Path(local_path).name)
    result = NaverMyBox(get_page()).upload(local_path)
    out = {**plan, "ok": bool(result.get("ok")), "result": result}
    _print_saved(out, _save_latest("naver_mybox_upload_latest.json", out))
