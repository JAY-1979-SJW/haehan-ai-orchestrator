"""블로그 / 카페 / 네이버 카페 자동화 액션 (스레드풀 실행)."""

from __future__ import annotations

import asyncio
import logging

from ._broadcast import broadcast
from .login_watcher import login_precheck_and_enqueue

logger = logging.getLogger(__name__)


# ── 블로그 ────────────────────────────────────────────────────────────────────


async def run_blog_write(data: dict) -> None:
    title = data.get("title", "").strip()
    body = data.get("body", "").strip()
    visibility = data.get("visibility", "public")
    brand_tags = data.get("brand_tags") or []

    if not title or not body:
        await broadcast({"type": "blog_status", "status": "error", "error": "제목과 본문은 필수입니다."})
        return

    if await login_precheck_and_enqueue("blog_write", data):
        await broadcast({"type": "blog_status", "status": "waiting_login", "title": title})
        return

    await broadcast({"type": "blog_status", "status": "writing", "title": title})
    try:
        result = await asyncio.to_thread(_blog_write_sync, title, body, visibility, brand_tags)
    except Exception as exc:
        logger.error("blog_write error: %s", exc)
        await broadcast({"type": "blog_status", "status": "error", "error": str(exc)})
        return

    if result.get("mode") == "awaiting_approval":
        s = result.get("summary", {})
        await broadcast(
            {
                "type": "blog_status",
                "status": "awaiting_approval",
                "title": s.get("title", title),
                "tags": s.get("tags", []),
                "visibility": s.get("visibility", visibility),
                "body_preview": s.get("body_preview", ""),
            }
        )
    else:
        await broadcast({"type": "blog_status", "status": "error", "error": result.get("error", "작성 실패")})


def _blog_write_sync(title: str, body: str, visibility: str, brand_tags: list) -> dict:
    from scripts.naver.blog.writer import write_post
    from scripts.web_connector import get_page

    return write_post(
        get_page(), title=title, body=body, visibility=visibility, brand_tags=brand_tags or None, require_approval=True
    )


async def run_blog_confirm() -> None:
    await broadcast({"type": "blog_status", "status": "confirming"})
    try:
        result = await asyncio.to_thread(_blog_confirm_sync)
    except Exception as exc:
        logger.error("blog_confirm error: %s", exc)
        await broadcast({"type": "blog_status", "status": "error", "error": str(exc)})
        return

    if result.get("ok"):
        await broadcast({"type": "blog_status", "status": "done", "result_url": result.get("url", "")})
    else:
        await broadcast({"type": "blog_status", "status": "error", "error": result.get("error", "발행 실패")})


def _blog_confirm_sync() -> dict:
    from scripts.naver.blog.writer import confirm_publish
    from scripts.web_connector import get_page

    return confirm_publish(get_page())


# ── 카페 ──────────────────────────────────────────────────────────────────────


async def run_cafe_write(data: dict) -> None:
    cafe_url = data.get("cafe_url", "https://cafe.naver.com/0moo")
    board = data.get("board", "")
    title = data.get("title", "").strip()
    body = data.get("body", "").strip()
    tags = data.get("tags") or []
    members_only = data.get("members_only", False)

    if not title or not body:
        await broadcast({"type": "cafe_status", "status": "error", "error": "제목과 본문은 필수입니다."})
        return

    if await login_precheck_and_enqueue("cafe_write", data):
        await broadcast({"type": "cafe_status", "status": "waiting_login", "title": title, "board": board})
        return

    await broadcast({"type": "cafe_status", "status": "writing", "title": title, "board": board})
    try:
        result = await asyncio.to_thread(_cafe_write_sync, cafe_url, board, title, body, tags, members_only)
    except Exception as exc:
        logger.error("cafe_write error: %s", exc)
        await broadcast({"type": "cafe_status", "status": "error", "error": str(exc)})
        return

    if result.get("mode") == "awaiting_approval":
        s = result.get("summary", {})
        await broadcast(
            {
                "type": "cafe_status",
                "status": "awaiting_approval",
                "title": s.get("title", title),
                "board": s.get("board", board),
                "body_preview": s.get("body_preview", ""),
            }
        )
    else:
        await broadcast({"type": "cafe_status", "status": "error", "error": result.get("error", "작성 실패")})


def _cafe_write_sync(cafe_url: str, board: str, title: str, body: str, tags: list, members_only: bool) -> dict:
    from scripts.naver.cafe.writer import write_post
    from scripts.web_connector import get_page

    return write_post(
        get_page(),
        cafe_url=cafe_url,
        board_name=board,
        title=title,
        body=body,
        tags=tags or None,
        members_only=members_only,
        require_approval=True,
    )


async def run_cafe_confirm() -> None:
    await broadcast({"type": "cafe_status", "status": "confirming"})
    try:
        result = await asyncio.to_thread(_cafe_confirm_sync)
    except Exception as exc:
        logger.error("cafe_confirm error: %s", exc)
        await broadcast({"type": "cafe_status", "status": "error", "error": str(exc)})
        return

    if result.get("ok"):
        await broadcast({"type": "cafe_status", "status": "done", "result_url": result.get("url", "")})
    else:
        await broadcast({"type": "cafe_status", "status": "error", "error": result.get("error", "발행 실패")})


def _cafe_confirm_sync() -> dict:
    from scripts.naver.cafe.writer import confirm_publish
    from scripts.web_connector import get_page

    return confirm_publish(get_page())


# ── 네이버 카페 목록 / 게시글 ──────────────────────────────────────────────────


async def run_naver_cafe_list(ws) -> None:
    await ws.send_json({"type": "naver_cafe_list", "status": "loading"})
    try:
        cafes = await asyncio.to_thread(_naver_cafe_list_sync)
        await ws.send_json({"type": "naver_cafe_list", "status": "done", "cafes": cafes})
    except Exception as exc:
        logger.error("naver_cafe_list error: %s", exc)
        await ws.send_json({"type": "naver_cafe_list", "status": "error", "error": str(exc)})


def _naver_cafe_list_sync() -> list:
    from scripts.naver.cafe import NaverCafe
    from scripts.web_connector import get_page

    return NaverCafe(get_page()).open_my_cafes()


async def run_naver_cafe_posts(ws, data: dict) -> None:
    cafe_url = data.get("cafe_url", "")
    board_no = data.get("board_no", "")
    limit = int(data.get("limit", 30))
    await ws.send_json({"type": "naver_cafe_posts", "status": "loading", "cafe_url": cafe_url})
    try:
        posts = await asyncio.to_thread(_naver_cafe_posts_sync, cafe_url, board_no, limit)
        await ws.send_json({"type": "naver_cafe_posts", "status": "done", "cafe_url": cafe_url, "posts": posts})
    except Exception as exc:
        logger.error("naver_cafe_posts error: %s", exc)
        await ws.send_json({"type": "naver_cafe_posts", "status": "error", "error": str(exc)})


def _naver_cafe_posts_sync(cafe_url: str, board_no, limit: int) -> list:
    from scripts.naver.cafe import NaverCafe
    from scripts.web_connector import get_page

    return NaverCafe(get_page()).list_posts(cafe_url=cafe_url, board_no=board_no, limit=limit)


async def run_naver_cafe_read(ws, data: dict) -> None:
    post_url = data.get("post_url", "")
    await ws.send_json({"type": "naver_cafe_read", "status": "loading"})
    try:
        post = await asyncio.to_thread(_naver_cafe_read_sync, post_url)
        await ws.send_json({"type": "naver_cafe_read", "status": "done", "post": post})
    except Exception as exc:
        logger.error("naver_cafe_read error: %s", exc)
        await ws.send_json({"type": "naver_cafe_read", "status": "error", "error": str(exc)})


def _naver_cafe_read_sync(post_url: str) -> dict:
    from scripts.naver.cafe import NaverCafe
    from scripts.web_connector import get_page

    return NaverCafe(get_page()).read_post(post_url=post_url)


# ── resume executor (login_watcher 에서 호출) ─────────────────────────────────


def default_resume_executor(cmd) -> bool:
    """LOGGED_IN 감지 후 원래 action 재실행. 무한 재진입 방지(_from_resume=True)."""
    payload = dict(cmd.original_payload or {})
    payload["_from_resume"] = True

    dispatch_map = {
        "blog_write": run_blog_write,
        "blog_confirm": lambda d: run_blog_confirm(),
        "cafe_write": run_cafe_write,
        "cafe_confirm": lambda d: run_cafe_confirm(),
        "browser_action": _run_browser_action_from_payload,
    }
    runner = dispatch_map.get(cmd.action)
    if runner is None:
        return False

    import asyncio as _asyncio

    try:
        loop = _asyncio.get_event_loop()
    except RuntimeError:
        return False

    try:
        loop.call_soon_threadsafe(lambda: _asyncio.create_task(runner(payload)))
    except RuntimeError:
        _asyncio.create_task(runner(payload))  # noqa: RUF006
    return True


async def _run_browser_action_from_payload(payload: dict) -> None:
    from .browser_routes import execute_browser_action

    await execute_browser_action(payload, send_to=None)
