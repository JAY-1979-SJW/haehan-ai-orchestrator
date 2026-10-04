"""네이버 카페 특정 게시판 — 증분 수집 계층.

책임:
    - 게시판 URL 빌더 (club_id + menu_id + page)
    - 파일 저장/로드 (JSON)
    - 기존 post_id 집합과 비교해 신규 글만 필터링 (중복 제거)
    - Runner 와 연결해 세션 재사용/재인증/재개 흐름 위에서 수집 실행

이 계층은 직접 로그인 자동화/본문·댓글 수집/대량 순회를 하지 않는다.
NaverCafeAdapter.collect_list 를 1페이지 기준으로 호출만 한다.

민감 로그 금지:
    - 쿠키, 세션, 헤더, 토큰 원문 금지.
    - 로그에 남기는 건 site_id / club_id / menu_id / 카운트 / 페이지 번호.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from .. import runner
from .naver_cafe_adapter import NaverCafeAdapter

logger = logging.getLogger(__name__)


SITE_ID = NaverCafeAdapter.site_id  # "naver_cafe"


# ── 수집 대상 설정 ────────────────────────────────────────────────
# 실제 운영 값은 환경변수로 주입 (.env 에 club_id, menu_id 명시).
# 여기 상수는 기본 placeholder — 테스트는 인자로 override 한다.
NAVER_CAFE_TARGET: dict[str, str] = {
    "club_id": os.environ.get("NAVER_CAFE_CLUB_ID", "").strip(),
    "menu_id": os.environ.get("NAVER_CAFE_MENU_ID", "").strip(),
}


# ── 저장 경로 ──────────────────────────────────────────────────────
def default_store_path() -> Path:
    """data/naver_cafe_posts.json — 환경변수 NAVER_CAFE_STORE_PATH 로 override 가능."""
    override = os.environ.get("NAVER_CAFE_STORE_PATH", "").strip()
    if override:
        return Path(override)
    # 패키지 루트(ai_orchestrator/..)의 data/ 디렉터리
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "data" / "naver_cafe_posts.json"


# ── 상태 코드 ──────────────────────────────────────────────────────
STATUS_COLLECTED = "NAVER_CAFE_COLLECTED"
STATUS_NO_NEW = "NAVER_CAFE_NO_NEW"
STATUS_BLOCKED_NOT_LOGGED_IN = "NAVER_CAFE_BLOCKED_NOT_LOGGED_IN"


# ── URL 빌더 ──────────────────────────────────────────────────────
def build_board_url(club_id: str, menu_id: str, *, page: int = 1) -> str:
    """특정 카페 게시판 1페이지 URL 빌드.

    네이버 카페의 ArticleList 레거시 라우팅을 사용한다. 이 URL 은 공개 목록
    페이지이며, 본문/댓글 수집으로 진입하지 않는다.
    """
    if not club_id or not menu_id:
        raise ValueError("club_id / menu_id 가 비어 있다 — NAVER_CAFE_TARGET 확인")
    qs = urlencode(
        {
            "search.clubid": club_id,
            "search.menuid": menu_id,
            "search.boardtype": "L",
            "search.page": max(1, int(page)),
        }
    )
    return f"https://cafe.naver.com/ArticleList.nhn?{qs}"


# ── 저장/로드 ──────────────────────────────────────────────────────
def _empty_record(club_id: str, menu_id: str) -> dict[str, Any]:
    return {
        "site": SITE_ID,
        "club_id": club_id,
        "menu_id": menu_id,
        "posts": [],
    }


def load_stored(path: Path) -> dict[str, Any]:
    """저장 파일 로드. 없으면 빈 레코드 반환. 파손 시 빈 레코드로 fallback."""
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return _empty_record("", "")
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("[NAVER-CAFE-STORE-READ-FAIL] err=%s", type(e).__name__)
        return _empty_record("", "")

    # 스키마 안정화
    if not isinstance(data, dict):
        return _empty_record("", "")
    data.setdefault("site", SITE_ID)
    data.setdefault("club_id", "")
    data.setdefault("menu_id", "")
    posts = data.get("posts")
    data["posts"] = posts if isinstance(posts, list) else []
    return data


def save_stored(path: Path, record: dict[str, Any]) -> None:
    """저장 파일 쓰기 (atomic replace). 민감 원문 미포함 가정."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def existing_ids(record: dict[str, Any]) -> set[str]:
    """저장 레코드에서 post_id 집합 추출. 공백/빈 id 는 제외."""
    out: set[str] = set()
    for p in record.get("posts", []):
        pid = (p.get("post_id") or "").strip()
        if pid:
            out.add(pid)
    return out


# ── 정규화 / 증분 ───────────────────────────────────────────────────
_PERSIST_FIELDS = ("post_id", "title", "author", "created_at", "url")


def _normalize_item(raw: dict[str, Any]) -> dict[str, str]:
    """어댑터가 뱉은 raw item 을 저장 스키마로 변환.

    - 어댑터는 'date' 필드로 날짜를 반환하므로, 저장 스키마에서 'created_at' 으로 매핑.
    - 어떤 경우에도 쿠키/토큰/HTML 원문이 섞이지 않도록 허용 키만 추림.
    """
    return {
        "post_id": str(raw.get("post_id") or "").strip(),
        "title": str(raw.get("title") or "").strip(),
        "author": str(raw.get("author") or "").strip(),
        "created_at": str(raw.get("created_at") or raw.get("date") or "").strip(),
        "url": str(raw.get("url") or "").strip(),
    }


def filter_new_posts(
    items: Iterable[dict[str, Any]],
    existing: set[str],
) -> tuple[list[dict[str, str]], int]:
    """정규화 + 중복 제거. (new_posts, skipped_count) 반환.

    - post_id 가 비어 있는 항목은 스킵 (skipped_count 에 포함).
    - 같은 호출 내 중복 post_id 도 1개만 남긴다.
    """
    seen: set[str] = set()
    new_posts: list[dict[str, str]] = []
    skipped = 0
    for raw in items:
        norm = _normalize_item(raw)
        pid = norm["post_id"]
        if not pid:
            skipped += 1
            continue
        if pid in existing or pid in seen:
            skipped += 1
            continue
        seen.add(pid)
        new_posts.append(norm)
    return new_posts, skipped


def merge_record(
    record: dict[str, Any],
    new_posts: list[dict[str, str]],
    *,
    club_id: str,
    menu_id: str,
) -> dict[str, Any]:
    """기존 레코드에 new_posts append. post_id 기준 중복 제거 (last-wins).

    club_id/menu_id 는 최신 값으로 갱신한다 (초기 빈 레코드 케이스 지원).
    """
    merged = dict(record)
    merged["site"] = SITE_ID
    merged["club_id"] = club_id or record.get("club_id", "")
    merged["menu_id"] = menu_id or record.get("menu_id", "")

    by_id: dict[str, dict[str, str]] = {}
    for p in record.get("posts", []):
        pid = (p.get("post_id") or "").strip()
        if pid:
            by_id[pid] = {k: p.get(k, "") for k in _PERSIST_FIELDS}
    for p in new_posts:
        pid = p.get("post_id") or ""
        if pid:
            by_id[pid] = p
    merged["posts"] = list(by_id.values())
    return merged


# ── collect_new_posts (어댑터 호출자) ──────────────────────────────
def collect_new_posts(  # noqa: PLR0913 - 수집 작업 공개 함수, 시그니처 유지
    adapter: NaverCafeAdapter,
    page: Any,
    existing: set[str],
    *,
    club_id: str,
    menu_id: str,
    page_num: int = 1,
    max_pages: int = 1,
) -> dict[str, Any]:
    """어댑터로 1페이지 목록을 읽어 new_posts / skipped_count 를 계산.

    Returns:
        {"status": <STATUS_*>, "new_posts": [...], "skipped_count": n,
         "page_num": k, "cursor": <board_url>}
    """
    board_url = build_board_url(club_id, menu_id, page=page_num)
    result = adapter.collect_list(
        page,
        cursor=board_url,
        page_num=page_num,
        max_pages=max_pages,
    )
    if not result.get("done"):
        return {
            "status": STATUS_BLOCKED_NOT_LOGGED_IN,
            "new_posts": [],
            "skipped_count": 0,
            "page_num": page_num,
            "cursor": board_url,
            "reason": result.get("reason", ""),
        }
    new_posts, skipped = filter_new_posts(result.get("items", []), existing)
    status = STATUS_COLLECTED if new_posts else STATUS_NO_NEW
    return {
        "status": status,
        "new_posts": new_posts,
        "skipped_count": skipped,
        "page_num": page_num,
        "cursor": board_url,
    }


# ── Runner 연동 ────────────────────────────────────────────────────
def run_naver_cafe_collect_job(  # noqa: PLR0913 - 수집 작업 공개 함수, 시그니처 유지
    adapter: NaverCafeAdapter,
    page: Any,
    *,
    job_id: str,
    club_id: str = "",
    menu_id: str = "",
    store_path: Path | None = None,
    page_num: int = 1,
    max_pages: int = 1,
    auto_reauth: bool = True,
    reauth_timeout_sec: int | None = None,
    sleeper: Any = None,
    clock: Any = None,
) -> str:
    """세션 재사용 흐름 위에서 1페이지 증분 수집 실행.

    흐름:
        1. runner.run_with_session 으로 ensure_session
        2. 세션 ACTIVE → work() 내부에서 collect_new_posts + 저장
        3. 세션 만료 → PAUSED_FOR_REAUTH (runner 가 처리)
        4. 재인증 후 resume 은 runner.resume_job 로 호출자가 담당
    """
    cid = club_id or NAVER_CAFE_TARGET.get("club_id", "")
    mid = menu_id or NAVER_CAFE_TARGET.get("menu_id", "")
    if not cid or not mid:
        raise ValueError("club_id / menu_id 필수 (NAVER_CAFE_TARGET 또는 인자)")

    path = store_path if store_path is not None else default_store_path()

    def _work(p: Any) -> str:
        record = load_stored(path)
        existing = existing_ids(record)
        outcome = collect_new_posts(
            adapter,
            p,
            existing,
            club_id=cid,
            menu_id=mid,
            page_num=page_num,
            max_pages=max_pages,
        )
        new_posts = outcome["new_posts"]
        skipped = outcome["skipped_count"]

        if outcome["status"] == STATUS_BLOCKED_NOT_LOGGED_IN:
            # runner 가 이 예외를 받아 PAUSED_FOR_REAUTH 로 전환.
            raise runner.SessionExpiredMidJob(
                reason=outcome.get("reason") or "not_logged_in",
                current_step="collect",
                cursor=outcome.get("cursor", ""),
            )

        if new_posts:
            merged = merge_record(record, new_posts, club_id=cid, menu_id=mid)
            save_stored(path, merged)

        logger.info(
            "[NAVER-CAFE-COLLECT] site=%s page=%d new=%d skipped=%d status=%s",
            SITE_ID,
            page_num,
            len(new_posts),
            skipped,
            outcome["status"],
        )
        return f"status={outcome['status']} new={len(new_posts)} skipped={skipped} page={page_num}"

    return runner.run_with_session(
        adapter,
        page,
        job_id=job_id,
        site_id=SITE_ID,
        work=_work,
        current_step="collect",
        params={"club_id": cid, "menu_id": mid, "page_num": page_num},
        auto_reauth=auto_reauth,
        reauth_timeout_sec=reauth_timeout_sec,
        sleeper=sleeper,
        clock=clock,
    )


__all__ = [
    "NAVER_CAFE_TARGET",
    "SITE_ID",
    "STATUS_BLOCKED_NOT_LOGGED_IN",
    "STATUS_COLLECTED",
    "STATUS_NO_NEW",
    "build_board_url",
    "collect_new_posts",
    "default_store_path",
    "existing_ids",
    "filter_new_posts",
    "load_stored",
    "merge_record",
    "run_naver_cafe_collect_job",
    "save_stored",
]
