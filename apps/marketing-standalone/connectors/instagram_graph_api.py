"""Instagram Graph API 정식 발행 — 릴스/이미지.

원본: scripts/instagram/api_publish.py (로직 0줄 변경, 로거만 이 앱 부트스트랩으로 교체).

인증: 이 앱을 쓰는 각 고객이 자기 Meta 앱(Instagram 로그인 방식)에서 발급한
액세스 토큰을 .env 의 IG_ACCESS_TOKEN 으로 보관한다(원문 출력 금지).

발행 3단계 (Meta 공식 흐름):
  1) POST /{ig-user-id}/media          → 컨테이너 생성(creation_id 반환)
  2) GET  /{container-id}?fields=status_code → FINISHED 될 때까지 폴링
  3) POST /{ig-user-id}/media_publish  → 실제 게시

⚠ video_url / image_url 은 **인터넷에서 공개 접근 가능한 URL**이어야 한다.
   로컬 파일 경로는 불가 — 릴레이 서버(Phase 1 별도 항목)에 올려 URL을 만든
   뒤 넘긴다.
"""

from __future__ import annotations

import json
import os
import sys as _sys
import time
import urllib.parse
import urllib.request
from pathlib import Path as _Path

from dotenv import load_dotenv

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from _bootstrap import get_logger

_log = get_logger(__name__)

GRAPH = "https://graph.instagram.com/v21.0"
POLL_INTERVAL = 5
POLL_MAX = 60  # 최대 5분

# 격리 원칙: 본사 저장소 상위 .env를 잘못 로드하는 사고 방지(2026-09-12) — 이 앱 폴더로 고정.
_APP_ENV_PATH = _Path(__file__).resolve().parents[1] / ".env"


def _creds() -> tuple[str, str]:
    load_dotenv(dotenv_path=_APP_ENV_PATH)
    tok = os.getenv("IG_ACCESS_TOKEN")
    uid = os.getenv("IG_USER_ID")
    if not tok or not uid:
        raise RuntimeError(".env 에 IG_ACCESS_TOKEN / IG_USER_ID 가 없습니다")
    return tok, uid


def _post(path: str, params: dict) -> dict:
    tok, _ = _creds()
    params = {**params, "access_token": tok}
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"{GRAPH}/{path}", data=data, method="POST")  # noqa: S310 (고정된 Meta Graph API 엔드포인트)
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
        return json.loads(r.read().decode())


def _get(path: str, params: dict) -> dict:
    tok, _ = _creds()
    qs = urllib.parse.urlencode({**params, "access_token": tok})
    with urllib.request.urlopen(f"{GRAPH}/{path}?{qs}", timeout=60) as r:  # noqa: S310
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
    """이미지 여러 장(최대 10)을 캐러셀 컨테이너로 묶는다."""
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
