"""마케팅 운영실 API — scripts/naver/blog/marketing/ 파이프라인을 웹에서 조회/승인/발행.

기존 파이프라인(주제 리서치·콘텐츠 생성·발행)을 그대로 호출만 한다 — 로직
중복 구현 없음. CDP 접속은 scripts.web_connector(get_page/run_on_browser_thread)
공용 브라우저 스레드를 재사용 — 요청마다 새 playwright 연결을 만들면 탭이
쌓여 CDP 자체가 느려지는 문제(2026-08-17 실측)를 피하기 위함.

발행(publish)은 항상 사용자 확인 후 confirmed=true로만 실행 — 자동 게시 없음.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ai_orchestrator.auth import require_role
from scripts.realtime_audit import emit_event

marketing_ops_router = APIRouter(prefix="/naver/marketing-ops", tags=["marketing-ops"])

_ROOT = Path(__file__).resolve().parents[2]
_RESEARCH_FILE = _ROOT / "data" / "blog_topic_research_latest.json"
_CACHE_FILE = _ROOT / "data" / "blog_topic_cache.json"
_REPORTS_DIR = _ROOT / "data" / "reports"
_PACKAGES_DIR = _ROOT / "data" / "marketing_packages"
_PACKAGES_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _latest_report(prefix: str) -> dict | None:
    files = sorted(_REPORTS_DIR.glob(f"{prefix}*.json"), reverse=True)
    if not files:
        return None
    return _load_json(files[0])


# ── 상태 조회 ────────────────────────────────────────────────────────────────


@marketing_ops_router.get("/state")
def get_state(user: dict = Depends(require_role("admin", "owner"))) -> dict[str, Any]:
    """오늘의 마케팅 운영실 화면 — 후보 주제, 발행 이력, 최신 성과, 대기 중인 패키지."""
    research = _load_json(_RESEARCH_FILE) or {}
    cache = _load_json(_CACHE_FILE) or {"posted": []}
    used_titles = {p.get("title", "") for p in cache.get("posted", [])}
    used_topics = {p.get("topic", "") for p in cache.get("posted", [])}

    candidates = [
        t
        for t in research.get("topics", [])
        if t.get("question_title") not in used_titles and t.get("question_title") not in used_topics
    ][:15]

    blog_analytics = _latest_report("blog_analytics_")
    packages = _list_packages()

    return {
        "ok": True,
        "generated_at": _now(),
        "research_generated_at": research.get("generated_at"),
        "candidate_topics": candidates,
        "recent_posted": list(reversed(cache.get("posted", [])))[:10],
        "blog_analytics_summary": {
            "referer": (blog_analytics or {}).get("referer"),
            "rank_pv": (blog_analytics or {}).get("rank_pv"),
        }
        if blog_analytics
        else None,
        "packages": packages,
    }


def _list_packages() -> list[dict]:
    items = []
    for f in sorted(_PACKAGES_DIR.glob("*.json"), reverse=True)[:30]:
        d = _load_json(f)
        if d:
            items.append(d)
    return items


@marketing_ops_router.get("/packages")
def list_packages(user: dict = Depends(require_role("admin", "owner"))) -> dict[str, Any]:
    return {"ok": True, "items": _list_packages()}


# ── 콘텐츠 패키지 생성 (블로그 원본 + 유튜브/쇼츠/인스타 파생) ───────────────────


class GeneratePackageRequest(BaseModel):
    topic: str
    keyword: str = ""
    source_description: str = ""
    angle: str = "지식iN 실제 질문에 답하는 실무 가이드"


@marketing_ops_router.post("/generate-package")
def generate_package(
    req: GeneratePackageRequest, user: dict = Depends(require_role("admin", "owner"))
) -> dict[str, Any]:
    """주제 1개 → 블로그 글(원본) + 유튜브 대본 + 쇼츠 3편 + 인스타 캡션. 발행 안 함(미리보기 전용)."""
    from scripts.naver.blog.marketing.content import generate_post
    from scripts.naver.blog.marketing.multichannel import generate_content_package

    topic_info = {
        "topic": req.topic,
        "keywords": [req.keyword, "건설실무", "건설업"] if req.keyword else ["건설실무", "건설업"],
        "angle": req.angle,
        "source_description": req.source_description,
    }
    blog_post = generate_post(topic_info, dry_run=False)
    if not blog_post:
        return {"ok": False, "error": "블로그 본문 생성 실패"}

    multi = generate_content_package(req.topic, req.angle)

    package_id = f"pkg_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    package = {
        "id": package_id,
        "created_at": _now(),
        "topic": req.topic,
        "keyword": req.keyword,
        "status": "pending_review",
        "blog": {
            "title": blog_post["title"],
            "body": blog_post["body"],
            "body_segments": blog_post.get("body_segments", []),
            "tags": blog_post.get("tags", []),
            "seo": blog_post.get("seo", {}),
        },
        "youtube": multi["youtube"],
        "shorts": multi["shorts"],
        "instagram": multi["instagram"],
        "publish_log": [],
    }
    path = _PACKAGES_DIR / f"{package_id}.json"
    path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")

    emit_event(
        "MARKETING_PACKAGE_GENERATE",
        site="naver_blog",
        workflow="marketing_ops",
        status="generated",
        risk="none",
        artifact_path=str(path),
        metadata={"topic": req.topic, "package_id": package_id},
    )
    return {"ok": True, "package": package}


# ── 승인 + 발행 (블로그만 — 유튜브/인스타는 아직 자동 게시 미구현) ────────────────


class PublishBlogRequest(BaseModel):
    package_id: str
    confirmed: bool = False


@marketing_ops_router.post("/publish-blog")
def publish_blog(req: PublishBlogRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict[str, Any]:
    """패키지의 블로그 콘텐츠를 실제로 네이버 블로그에 발행. confirmed=true 필수."""
    if not req.confirmed:
        return {"ok": False, "error": "발행은 confirmed=true 확인이 필요합니다 (외부 공개)"}

    path = _PACKAGES_DIR / f"{req.package_id}.json"
    package = _load_json(path)
    if not package:
        return {"ok": False, "error": "패키지를 찾을 수 없습니다"}

    from scripts.naver.blog.marketing import TARGET_BLOG_ID
    from scripts.naver.blog.marketing.images import pick_3_images
    from scripts.naver.blog.marketing.publish import existing_unsplash_fallback, record_success
    from scripts.naver.blog.marketing.topics import load_cache
    from scripts.web_connector import get_page, run_on_browser_thread

    blog = package["blog"]
    all_images = existing_unsplash_fallback()
    img_paths = pick_3_images(all_images, len(_list_packages()))

    def _do() -> dict:
        from scripts.naver.blog.core.writer import write_post

        page = get_page()
        return write_post(
            page,
            title=blog["title"],
            body=blog["body"],
            body_segments=blog.get("body_segments") or None,
            tags=blog.get("tags"),
            images=img_paths,
            visibility="public",
            require_approval=False,
        )

    result = run_on_browser_thread(_do, timeout=200)
    ok = bool(result and result.get("ok"))

    package["status"] = "published" if ok else "publish_failed"
    package["publish_log"].append(
        {"at": _now(), "blog_id": TARGET_BLOG_ID, "ok": ok, "log_no": (result or {}).get("log_no")}
    )
    path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")

    if ok:
        cache = load_cache()
        record_success(
            cache,
            topic=package["topic"],
            post={"title": blog["title"], "tags": blog.get("tags", [])},
            log_no=result.get("log_no", ""),
            img_paths=img_paths,
        )

    emit_event(
        "MARKETING_PACKAGE_PUBLISH",
        site="naver_blog",
        workflow="marketing_ops",
        status="published" if ok else "failed",
        risk="high",
        metadata={"package_id": req.package_id, "title": blog["title"]},
    )
    return {"ok": ok, "result": result}


class ApproveChannelRequest(BaseModel):
    package_id: str
    channel: str  # youtube | shorts | instagram


@marketing_ops_router.post("/approve-channel")
def approve_channel(req: ApproveChannelRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict[str, Any]:
    """유튜브/쇼츠/인스타는 자동 게시가 아직 없음 — '검토 완료' 표시만 남긴다(수동 게시용)."""
    path = _PACKAGES_DIR / f"{req.package_id}.json"
    package = _load_json(path)
    if not package:
        return {"ok": False, "error": "패키지를 찾을 수 없습니다"}
    package["publish_log"].append({"at": _now(), "channel": req.channel, "action": "approved_manual_publish"})
    path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "message": f"{req.channel} 승인됨 — 직접 게시해주세요(자동 게시 미구현)"}


# ── 블로그 이웃 목록 ────────────────────────────────────────────────────────

_NEIGHBORS_CACHE = _ROOT / "data" / "reports" / "blog_neighbors_latest.json"


@marketing_ops_router.get("/neighbors")
def get_neighbors(user: dict = Depends(require_role("admin", "owner"))) -> dict[str, Any]:
    """캐시된 이웃 목록 조회 (없으면 새로고침 안내만, CDP 호출은 /neighbors/refresh 로 별도)."""
    cached = _load_json(_NEIGHBORS_CACHE)
    if not cached:
        return {"ok": True, "cached": False, "neighbors": [], "active": 0, "dormant": 0, "total": 0}
    return {"ok": True, "cached": True, **cached}


@marketing_ops_router.post("/neighbors/refresh")
def refresh_neighbors(user: dict = Depends(require_role("admin", "owner"))) -> dict[str, Any]:
    """CDP로 실제 이웃 목록을 다시 조회해 캐시 갱신 (107명 기준 약 10~20초 소요)."""
    from scripts.naver.blog.community.neighbor_manager import BlogNeighborManager
    from scripts.naver.blog.marketing import TARGET_BLOG_ID
    from scripts.web_connector import get_page, run_on_browser_thread

    def _do() -> dict:
        page = get_page()
        nm = BlogNeighborManager(page, TARGET_BLOG_ID)
        result = nm.classify_activity(days_threshold=90)
        return result

    result = run_on_browser_thread(_do, timeout=60)
    if not result or not result.get("ok"):
        return {"ok": False, "error": "이웃 목록 조회 실패"}

    payload = {
        "generated_at": _now(),
        "blog_id": TARGET_BLOG_ID,
        "total": result["total"],
        "active": len(result["active"]),
        "dormant": len(result["dormant"]),
        "neighbors": result["active"] + result["dormant"],
    }
    _NEIGHBORS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _NEIGHBORS_CACHE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    emit_event(
        "MARKETING_NEIGHBORS_REFRESH",
        site="naver_blog",
        workflow="marketing_ops",
        status="ok",
        risk="none",
        metadata={"total": payload["total"], "active": payload["active"]},
    )
    return {"ok": True, **payload}
