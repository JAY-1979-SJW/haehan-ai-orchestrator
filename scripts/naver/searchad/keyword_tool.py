"""네이버 검색광고 키워드도구 — 월간 검색량/경쟁정도 조회 (읽기 전용).

GET https://api.searchad.naver.com/keywordstool?hintKeywords=...&showDetail=1

사용:
    from scripts.naver.searchad.keyword_tool import get_keyword_stats
    stats = get_keyword_stats(["실적신고", "4대보험"])
    # [{"keyword": "실적신고", "pc_count": 1234, "mobile_count": 5678, "competition": "높음"}, ...]
"""

from __future__ import annotations

import requests

from scripts.common.logger import get_logger
from scripts.naver.searchad.auth import build_headers, load_credentials

_log = get_logger(__name__)

_BASE_URL = "https://api.searchad.naver.com"
_URI = "/keywordstool"
_MAX_KEYWORDS_PER_CALL = 5  # 네이버 키워드도구 API 1회 호출 시 힌트키워드 최대 개수


def _to_int(v) -> int:
    """API가 노출량이 극히 적을 때 '< 10' 문자열을 반환하는 경우가 있어 안전 변환."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _fetch_batch(keywords: list[str]) -> list[dict]:
    cred = load_credentials()
    if not all([cred["customer_id"], cred["secret_key"], cred["access_license"]]):
        raise RuntimeError("naver_searchad 자격증명이 없습니다. scripts.auth.credentials.set_cred로 먼저 등록하세요.")

    headers = build_headers(
        method="GET",
        uri=_URI,
        access_license=cred["access_license"],
        secret_key=cred["secret_key"],
        customer_id=cred["customer_id"],
    )
    # hintKeywords는 키워드별 공백을 허용하지 않는다(포함 시 400 에러) — 공백만 제거.
    cleaned = [kw.replace(" ", "") for kw in keywords]
    params = {"hintKeywords": ",".join(cleaned), "showDetail": "1"}

    resp = requests.get(_BASE_URL + _URI, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    out = []
    for item in data.get("keywordList", []):
        out.append(
            {
                "keyword": item.get("relKeyword", ""),
                "pc_count": _to_int(item.get("monthlyPcQcCnt")),
                "mobile_count": _to_int(item.get("monthlyMobileQcCnt")),
                "competition": item.get("compIdx", ""),
                "monthly_ad_count_pc": _to_int(item.get("monthlyAvePcClkCnt")),
            }
        )
    return out


def get_keyword_stats(keywords: list[str]) -> list[dict]:
    """키워드 목록의 월간 PC/모바일 검색량을 조회. 5개씩 나눠서 호출."""
    results: list[dict] = []
    for i in range(0, len(keywords), _MAX_KEYWORDS_PER_CALL):
        batch = keywords[i : i + _MAX_KEYWORDS_PER_CALL]
        try:
            results.extend(_fetch_batch(batch))
        except Exception as e:  # noqa: BLE001 - 네이버 검색광고 키워드 무료 조회 배치(_fetch_batch) 실패를 경고 로그로 남기고 다음 배치로 계속 진행하는 읽기전용 API 호출.
            _log.warning("[searchad] 키워드 조회 실패 %s: %s", batch, e)
    return results


def keyword_search_volume(candidates: list[tuple[str, int]], freq_key: str) -> list[dict]:
    """(키워드, 빈도) 후보의 월간 검색량을 붙여 총검색량 내림차순으로 돌려준다(조회 안 된 키워드는 뺌).

    research_blog_topics·research_blog_topics_lighting 의 _search_volume 이 빈도 열 이름
    (cafe_freq/ohou_freq)만 다르게 똑같이 복사해 쓰던 본문을 한 곳으로 모았다.
    후보 키워드는 공백을 뺀 값으로 조회 결과 keyword 와 맞춘다.
    """
    keywords = [w for w, _ in candidates]
    stats = get_keyword_stats(keywords)

    by_kw: dict[str, dict] = {}
    for s in stats:
        for orig in keywords:
            if orig.replace(" ", "") == s["keyword"]:
                by_kw[orig] = s

    rows = []
    for w, freq in candidates:
        stat = by_kw.get(w)
        if not stat:
            continue
        rows.append(
            {
                "keyword": w,
                freq_key: freq,
                "pc": stat["pc_count"],
                "mobile": stat["mobile_count"],
                "total_search": stat["pc_count"] + stat["mobile_count"],
                "competition": stat["competition"],
            }
        )
    rows.sort(key=lambda r: -r["total_search"])
    return rows
