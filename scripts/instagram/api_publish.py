"""Instagram Graph API 정식 발행 — 릴스/이미지 (CDP 클릭 자동화 대체).

CDP로 인스타 웹 UI를 클릭해 릴스를 올리는 방식은 UI가 세션마다 달라져
실패했다(2026-08-19 실측). 정식 API 경로가 훨씬 안정적이다.

인증: Meta 앱 'Banditbul Publisher'(Instagram 로그인 방식)에서 발급한
액세스 토큰을 .env 의 IG_ACCESS_TOKEN 으로 보관한다(원문 출력 금지).

발행 3단계 (Meta 공식 흐름):
  1) POST /{ig-user-id}/media          → 컨테이너 생성(creation_id 반환)
  2) GET  /{container-id}?fields=status_code → FINISHED 될 때까지 폴링
  3) POST /{ig-user-id}/media_publish  → 실제 게시

릴스 탭 노출 조건: 9:16 비율, 5~90초, H.264. scripts/instagram/reel.py 가
1080x1920으로 뽑으므로 길이만 맞추면 된다.

⚠ video_url / image_url 은 **인터넷에서 공개 접근 가능한 URL**이어야 한다.
   로컬 파일 경로는 불가 — haehan-ai.kr public/ 등에 올려 URL을 만든 뒤 넘긴다.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

from dotenv import load_dotenv

from scripts.logger import get_logger

_log = get_logger(__name__)

GRAPH = "https://graph.instagram.com/v21.0"
POLL_INTERVAL = 5
POLL_MAX = 60  # 최대 5분


def _creds() -> tuple[str, str]:
    load_dotenv()
    tok = os.getenv("IG_ACCESS_TOKEN")
    uid = os.getenv("IG_USER_ID")
    if not tok or not uid:
        raise RuntimeError(".env 에 IG_ACCESS_TOKEN / IG_USER_ID 가 없습니다")
    return tok, uid


def _post(path: str, params: dict) -> dict:
    tok, _ = _creds()
    params = {**params, "access_token": tok}
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"{GRAPH}/{path}", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _get(path: str, params: dict) -> dict:
    tok, _ = _creds()
    qs = urllib.parse.urlencode({**params, "access_token": tok})
    with urllib.request.urlopen(f"{GRAPH}/{path}?{qs}", timeout=60) as r:
        return json.loads(r.read().decode())


def create_reel_container(video_url: str, caption: str, share_to_feed: bool = True) -> str:
    _, uid = _creds()
    res = _post(
        f"{uid}/media",
        {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true" if share_to_feed else "false",
        },
    )
    cid = res.get("id")
    if not cid:
        raise RuntimeError(f"컨테이너 생성 실패: {res}")
    _log.info(f"[ig-api] 릴스 컨테이너 생성: {cid}")
    return cid


def wait_ready(container_id: str) -> None:
    """Instagram 서버의 영상 처리 완료(FINISHED)까지 대기."""
    for i in range(POLL_MAX):
        res = _get(container_id, {"fields": "status_code,status"})
        code = res.get("status_code")
        if code == "FINISHED":
            _log.info(f"[ig-api] 처리 완료 ({i * POLL_INTERVAL}s)")
            return
        if code == "ERROR":
            raise RuntimeError(f"영상 처리 실패: {res}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"처리 대기 시간 초과: {container_id}")


def publish(container_id: str) -> dict:
    _, uid = _creds()
    res = _post(f"{uid}/media_publish", {"creation_id": container_id})
    _log.info(f"[ig-api] 발행 완료: {res}")
    return res


def publish_reel(video_url: str, caption: str, confirmed: bool = False) -> dict:
    """릴스 발행 전 과정. confirmed=True 일 때만 실제 게시한다."""
    cid = create_reel_container(video_url, caption)
    wait_ready(cid)
    if not confirmed:
        _log.info("[ig-api] confirmed=False — 컨테이너까지만 생성, 게시 안 함")
        return {"container_id": cid, "published": False}
    res = publish(cid)
    return {"container_id": cid, "published": True, **res}


def create_carousel(image_urls: list[str], caption: str) -> str:
    """이미지 여러 장(최대 10)을 캐러셀 컨테이너로 묶는다.

    CDP 웹 업로드로는 다중 선택이 안 됐지만(2026-08-19), API는 각 장을
    is_carousel_item 컨테이너로 만든 뒤 CAROUSEL 컨테이너로 묶으면 된다.
    """
    _, uid = _creds()
    if not 2 <= len(image_urls) <= 10:
        raise ValueError("캐러셀은 2~10장이어야 합니다")

    children = []
    for url in image_urls:
        res = _post(f"{uid}/media", {"image_url": url, "is_carousel_item": "true"})
        cid = res.get("id")
        if not cid:
            raise RuntimeError(f"자식 컨테이너 실패: {res}")
        children.append(cid)
    _log.info(f"[ig-api] 캐러셀 자식 {len(children)}개 생성")

    res = _post(
        f"{uid}/media",
        {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption},
    )
    parent = res.get("id")
    if not parent:
        raise RuntimeError(f"캐러셀 컨테이너 실패: {res}")
    _log.info(f"[ig-api] 캐러셀 컨테이너: {parent}")
    return parent


def publish_carousel(image_urls: list[str], caption: str, confirmed: bool = False) -> dict:
    cid = create_carousel(image_urls, caption)
    if not confirmed:
        return {"container_id": cid, "published": False}
    res = publish(cid)
    return {"container_id": cid, "published": True, **res}


def whoami() -> dict:
    _, uid = _creds()
    return _get(uid, {"fields": "id,username,account_type"})


# ══════════════════════════════════════════════════════════════════════════════
# 스토리 발행 (media_type=STORIES) — caption 미지원, image_url 또는 video_url만
# ══════════════════════════════════════════════════════════════════════════════


def create_story_container(*, image_url: str = "", video_url: str = "") -> str:
    if bool(image_url) == bool(video_url):
        raise ValueError("image_url 또는 video_url 중 하나만 지정해야 합니다")
    _, uid = _creds()
    params: dict = {"media_type": "STORIES"}
    params["image_url" if image_url else "video_url"] = image_url or video_url
    res = _post(f"{uid}/media", params)
    cid = res.get("id")
    if not cid:
        raise RuntimeError(f"스토리 컨테이너 생성 실패: {res}")
    _log.info(f"[ig-api] 스토리 컨테이너 생성: {cid}")
    return cid


def publish_story(*, image_url: str = "", video_url: str = "", confirmed: bool = False) -> dict:
    """스토리 발행. confirmed=True 일 때만 실제 게시한다."""
    cid = create_story_container(image_url=image_url, video_url=video_url)
    if video_url:
        wait_ready(cid)
    if not confirmed:
        _log.info("[ig-api] confirmed=False — 컨테이너까지만 생성, 게시 안 함")
        return {"container_id": cid, "published": False}
    res = publish(cid)
    return {"container_id": cid, "published": True, **res}


# ══════════════════════════════════════════════════════════════════════════════
# 인사이트 (읽기 전용)
# ══════════════════════════════════════════════════════════════════════════════

# 미디어 타입별 지원 메트릭이 달라 media_type 인자로 분기한다(Graph API 제약).
_MEDIA_INSIGHT_METRICS = {
    "REELS": "reach,likes,comments,saved,shares,plays,total_interactions",
    "IMAGE": "reach,likes,comments,saved,shares,total_interactions",
    "CAROUSEL": "reach,likes,comments,saved,shares,total_interactions",
}


def get_media_insights(media_id: str, media_type: str = "IMAGE") -> dict:
    """게시물 하나의 인사이트(도달·참여 등). media_type: REELS | IMAGE | CAROUSEL."""
    metrics = _MEDIA_INSIGHT_METRICS.get(media_type.upper(), _MEDIA_INSIGHT_METRICS["IMAGE"])
    res = _get(f"{media_id}/insights", {"metric": metrics})
    return {row["name"]: row.get("values", [{}])[0].get("value") for row in res.get("data", [])}


def get_account_insights(metrics: str = "reach,profile_views,website_clicks", period: str = "day") -> dict:
    """계정 단위 인사이트. period: day | week | days_28."""
    _, uid = _creds()
    res = _get(f"{uid}/insights", {"metric": metrics, "period": period})
    return {row["name"]: row.get("values", []) for row in res.get("data", [])}


# ══════════════════════════════════════════════════════════════════════════════
# 해시태그 검색 (읽기 전용) — 주당 신규 해시태그 조회 30개 한도
# ══════════════════════════════════════════════════════════════════════════════


def search_hashtag_id(name: str) -> str:
    """해시태그 이름(# 제외) → hashtag_id. 이후 top/recent_media 조회에 사용."""
    _, uid = _creds()
    res = _get("ig_hashtag_search", {"user_id": uid, "q": name})
    data = res.get("data") or []
    if not data:
        raise RuntimeError(f"해시태그를 찾을 수 없습니다: {name}")
    return data[0]["id"]


def get_hashtag_media(hashtag_id: str, kind: str = "top", limit: int = 20) -> list[dict]:
    """kind: top | recent. caption/permalink/like_count/comments_count 반환."""
    _, uid = _creds()
    edge = "top_media" if kind == "top" else "recent_media"
    res = _get(
        f"{hashtag_id}/{edge}",
        {"user_id": uid, "fields": "id,caption,permalink,like_count,comments_count,timestamp", "limit": limit},
    )
    return res.get("data", [])
