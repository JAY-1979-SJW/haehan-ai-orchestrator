"""네이버 지식iN 검색 OpenAPI 클라이언트 — 실제 질문 제목 조사용.

키워드 검색량(searchad)만으로는 "얼마나 검색되는지"만 알 수 있고 "무엇을 궁금해
하는지"는 알 수 없다. 지식iN 검색은 실제 사용자가 올린 질문 제목을 그대로
보여주므로, 블로그 콘텐츠의 제목·앵글을 사람들이 쓰는 표현에 맞추는 데 쓴다.

(2026-10-08 W10: 서버 connectors 에서 도구 집 scripts/naver/shopping/ 로 이동 —
블로그 리서치 CLI 만 쓰는 도구 구현이라 scripts → connectors 역방향 import 를 없앴다.)

기존 naver_search_client.py(blog/shop 전용)와 별개 모듈로 둔 이유: kin.json은
동일 OpenAPI 스펙이지만 응답 필드가 달라 공유 파서를 억지로 맞추는 것보다
명확히 분리하는 게 낫다고 판단.

설계 원칙은 naver_search_client.py와 동일:
- GET 전용, 비로그인 공개 검색만 사용
- client_id/secret 로그 노출 금지
"""

from __future__ import annotations

import logging
import re

import requests

from scripts.naver.shopping import naver_openapi_config as cfg_mod

logger = logging.getLogger(__name__)

_PATH_KIN = "/v1/search/kin.json"
_TAG_RE = re.compile(r"</?b>")
_DOC_ID_RE = re.compile(r"docId=(\d+)")


def _strip_tags(s: str) -> str:
    return _TAG_RE.sub("", s or "")


def _doc_id(link: str) -> str:
    """kin 링크의 docId(질문글 고유ID) 추출. 답변 여러 개가 각각 검색결과로
    잡히면 answerNo만 다르고 docId는 동일 — 이걸로 같은 질문글인지 판별한다."""
    m = _DOC_ID_RE.search(link or "")
    return m.group(1) if m else link


def search_kin_questions(query: str, *, display: int = 20) -> list[dict]:
    """지식iN에서 query로 검색된 실제 질문 제목·설명을 반환. 같은 질문글에
    답변이 여러 개 달려 중복 검색되는 경우 docId 기준으로 1건만 남긴다.

    Returns: [{"title": str, "description": str, "link": str, "doc_id": str}, ...]
    """
    cfg = cfg_mod.load_config()
    if not cfg.client_id or not cfg.client_secret:
        logger.warning("[naver_kin] NAVER_OPENAPI_CLIENT_ID/SECRET 미설정")
        return []

    resp = requests.get(
        "https://openapi.naver.com" + _PATH_KIN,
        headers={
            "X-Naver-Client-Id": cfg.client_id,
            "X-Naver-Client-Secret": cfg.client_secret,
        },
        params={"query": query, "display": min(display, 100), "sort": "sim"},
        timeout=10,
    )
    if resp.status_code != 200:
        logger.warning("[naver_kin] 검색 실패 %s: status=%s", query, resp.status_code)
        return []

    items = resp.json().get("items", [])
    seen_doc_ids: set[str] = set()
    out = []
    for it in items:
        link = it.get("link", "")
        doc_id = _doc_id(link)
        if doc_id in seen_doc_ids:
            continue  # 같은 질문글의 다른 답변 — 중복
        seen_doc_ids.add(doc_id)
        out.append(
            {
                "title": _strip_tags(it.get("title", "")),
                "description": _strip_tags(it.get("description", "")),
                "link": link,
                "doc_id": doc_id,
            }
        )
    return out
