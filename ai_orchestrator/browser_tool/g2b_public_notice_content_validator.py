"""
G2B 공개 공고 콘텐츠 유효성 판정 모듈

URL 도달 성공(LIVE_PASS)과 실제 공고 콘텐츠 유효성(CONTENT_VALID_PASS)을 분리한다.

원칙:
- "시스템 접근 안내" / "요청하신 페이지를 찾을수 없습니다" 는 CONTENT_VALID_PASS 불가
- "나라장터" 단어만으로 CONTENT_VALID_PASS 승격 불가
- positive signal 2개 이상 + negative signal 없을 때만 CONTENT_VALID_PASS 후보
- g2b.go.kr / www.g2b.go.kr 도메인 이탈 시 CONTENT_INVALID
- wildcard 서브도메인 자동 content valid 불가
- 쿠키/session/token/password/otp 저장 없음
- DB write 없음
- click/type/fill/submit/download 실행 없음
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

# ── content_verdict 값 ──────────────────────────────────────────────────────

CONTENT_VALID_PASS = "CONTENT_VALID_PASS"  # noqa: S105
LIVE_REACHABLE = "LIVE_REACHABLE"
REACHABLE_BUT_NOT_CONTENT_VALID = "REACHABLE_BUT_NOT_CONTENT_VALID"
CONTENT_INVALID = "CONTENT_INVALID"
CONTENT_UNKNOWN = "CONTENT_UNKNOWN"
CONTENT_BLOCKED_BY_POLICY = "CONTENT_BLOCKED_BY_POLICY"

# ── 허용 도메인 ──────────────────────────────────────────────────────────────

_ALLOWED_CONTENT_DOMAINS: frozenset[str] = frozenset(
    {
        "g2b.go.kr",
        "www.g2b.go.kr",
    }
)

# ── positive signal (공고 콘텐츠 지표) ──────────────────────────────────────

_POSITIVE_SIGNALS: tuple[str, ...] = (
    "공고명",
    "공고번호",
    "수요기관",
    "개찰",
    "입찰공고",
    "조달청",
    "업무구분",
    "게시일시",
    "공고기관",
    "입찰방법",
    "입찰마감",
    "낙찰방법",
    "추정가격",
    "공고일자",
    "공사명",
    "용역명",
    "물품명",
)

# ── negative signal (콘텐츠 무효 지표) ──────────────────────────────────────

_NEGATIVE_SIGNALS: tuple[str, ...] = (
    "시스템 접근 안내",
    "요청하신 페이지를 찾을수 없습니다",
    "로그인",
    "인증서",
    "접근이 제한",
    "세션",
    "권한이 없",
    "결제",
    "계약",
    "투찰",
    "오류가 발생",
    "에러",
    "잘못된 접근",
    "올바르지 않은 URL",
)

# ── 차단 경로 패턴 (후보 URL 분류용) ────────────────────────────────────────

_BLOCKED_HREF_PATTERNS: tuple[str, ...] = (
    "/login",
    "/cert",
    "/bid_submit",
    "/contract",
    "/payment",
    "/download",
    "/upload",
    "egovuserreqstlogin",
    "usercert",
    "ptb05001p",
    "ctb01001",
    "checkout",
    "ptb04001p",
)

_DOWNLOAD_HREF_PATTERNS: tuple[str, ...] = (
    "/file/download",
    "fileDown",
    "attachDown",
    "bdgtFileDown",
    ".hwp",
    ".hwpx",
    ".pdf",
    ".zip",
    ".xls",
    ".xlsx",
    ".doc",
)

_NEEDS_VERIFICATION_DOMAINS: frozenset[str] = frozenset(
    {
        "shop.g2b.go.kr",
        "api.g2b.go.kr",
    }
)

_BODY_TEXT_SAMPLE_MAX_LEN = 1000


def _extract_positive_signals(text: str) -> list[str]:
    return [s for s in _POSITIVE_SIGNALS if s in text]


def _extract_negative_signals(text: str) -> list[str]:
    return [s for s in _NEGATIVE_SIGNALS if s in text]


def is_g2b_public_notice_content_valid(
    title: str,
    body_text: str,
    final_url: str,
) -> bool:
    """title/body_text/final_url 기준으로 콘텐츠 유효 여부 반환."""
    parsed = urlparse(final_url)
    if parsed.netloc not in _ALLOWED_CONTENT_DOMAINS:
        return False
    combined = f"{title}\n{body_text}"
    if _extract_negative_signals(combined):
        return False
    pos = _extract_positive_signals(combined)
    return len(pos) >= 2


def _judge_content_verdict(
    domain_valid: bool,
    reachable: bool,
    final_netloc: str,
    positive_signals: list[str],
    negative_signals: list[str],
) -> tuple[str, str, bool]:
    """(content_verdict, invalid_reason, content_valid) 판정."""
    if not domain_valid:
        return CONTENT_INVALID, f"final_url 도메인 이탈: {final_netloc!r}", False
    if not reachable:
        return CONTENT_UNKNOWN, "live 실행 결과 없음", False
    if negative_signals:
        return REACHABLE_BUT_NOT_CONTENT_VALID, "; ".join(negative_signals), False
    if len(positive_signals) >= 2:
        return CONTENT_VALID_PASS, "", True
    if positive_signals:
        return LIVE_REACHABLE, "positive signal 부족 (2개 미만)", False
    return CONTENT_UNKNOWN, "signal 판단 기준 부족", False


def _classify_candidate_links(
    raw_links: list[str], final_netloc: str
) -> tuple[list[str], list[str], list[str], list[str]]:
    """(candidate, safe, blocked, needs_verification) 후보 URL 분류."""
    candidate_urls: list[str] = []
    safe_candidate_urls: list[str] = []
    blocked_candidate_urls: list[str] = []
    needs_verification_candidate_urls: list[str] = []

    for href in raw_links:
        if not isinstance(href, str):
            continue
        href = href.strip()
        if not href or href.startswith("#") or href.startswith("javascript"):
            continue
        parsed_href = urlparse(href)
        # 상대 경로는 final_url 도메인 기준
        netloc = parsed_href.netloc or final_netloc
        lower_href = href.lower()

        if netloc in _NEEDS_VERIFICATION_DOMAINS:
            needs_verification_candidate_urls.append(href)
        elif netloc not in _ALLOWED_CONTENT_DOMAINS:
            # g2b 도메인 외부 → 후보 아님
            continue
        elif any(p in lower_href for p in _BLOCKED_HREF_PATTERNS):
            blocked_candidate_urls.append(href)
        elif any(p in lower_href for p in _DOWNLOAD_HREF_PATTERNS):
            blocked_candidate_urls.append(href)
        else:
            candidate_urls.append(href)
            safe_candidate_urls.append(href)

    return (
        candidate_urls,
        safe_candidate_urls,
        blocked_candidate_urls,
        needs_verification_candidate_urls,
    )


def classify_g2b_public_notice_content(result: dict[str, Any]) -> dict[str, Any]:
    """
    live runner 결과 dict를 받아 content verdict 및 보강 필드를 반환한다.

    입력 필드(live runner 결과):
      input_url, final_url, title, body_text_sample, body_text_length,
      verdict(live_verdict), mock_used, local_agent_used, server_browser_used

    반환 필드:
      input_url, final_url, title, body_text_length, body_text_sample,
      content_verdict, content_valid, reachable, invalid_reason,
      positive_signals, negative_signals,
      candidate_urls, safe_candidate_urls, blocked_candidate_urls,
      needs_verification_candidate_urls, verdict
    """
    input_url: str = result.get("input_url", "")
    final_url: str = result.get("final_url", "") or input_url
    title: str = result.get("title", "") or ""
    raw_body: str = result.get("body_text_sample", "") or ""
    body_text_sample = raw_body[:_BODY_TEXT_SAMPLE_MAX_LEN]
    body_text_length: int = result.get("body_text_length", len(raw_body))
    live_verdict: str = result.get("verdict", "") or ""
    reachable: bool = live_verdict in ("LIVE_PASS", "LIVE_REACHABLE")

    parsed_final = urlparse(final_url)
    domain_valid = parsed_final.netloc in _ALLOWED_CONTENT_DOMAINS

    combined = f"{title}\n{body_text_sample}"
    positive_signals = _extract_positive_signals(combined)
    negative_signals = _extract_negative_signals(combined)

    # content_verdict 판정
    content_verdict, invalid_reason, content_valid = _judge_content_verdict(
        domain_valid, reachable, parsed_final.netloc, positive_signals, negative_signals
    )

    # 후보 URL 분류 (links 필드가 있을 경우)
    raw_links: list[str] = result.get("links", []) or []
    (
        candidate_urls,
        safe_candidate_urls,
        blocked_candidate_urls,
        needs_verification_candidate_urls,
    ) = _classify_candidate_links(raw_links, parsed_final.netloc)

    return {
        "input_url": input_url,
        "final_url": final_url,
        "title": title,
        "body_text_length": body_text_length,
        "body_text_sample": body_text_sample,
        "content_verdict": content_verdict,
        "content_valid": content_valid,
        "reachable": reachable,
        "invalid_reason": invalid_reason,
        "positive_signals": positive_signals,
        "negative_signals": negative_signals,
        "candidate_urls": candidate_urls,
        "safe_candidate_urls": safe_candidate_urls,
        "blocked_candidate_urls": blocked_candidate_urls,
        "needs_verification_candidate_urls": needs_verification_candidate_urls,
        "verdict": content_verdict,
    }


def validate_g2b_public_notice_content_result(result: dict[str, Any]) -> dict[str, Any]:
    """classify_g2b_public_notice_content의 별칭 (호환성 유지)."""
    return classify_g2b_public_notice_content(result)


def extract_g2b_public_notice_url_candidates(page_result: dict[str, Any]) -> dict[str, Any]:
    """
    live runner 결과에서 URL 후보를 추출하고 정책 분류를 반환한다.

    반환:
      safe_candidate_urls, blocked_candidate_urls,
      needs_verification_candidate_urls, candidate_url_count,
      safe_candidate_url_count, blocked_candidate_url_count,
      needs_verification_candidate_url_count
    """
    classified = classify_g2b_public_notice_content(page_result)
    safe = classified["safe_candidate_urls"]
    blocked = classified["blocked_candidate_urls"]
    needs_v = classified["needs_verification_candidate_urls"]
    return {
        "safe_candidate_urls": safe,
        "blocked_candidate_urls": blocked,
        "needs_verification_candidate_urls": needs_v,
        "candidate_url_count": len(safe) + len(blocked) + len(needs_v),
        "safe_candidate_url_count": len(safe),
        "blocked_candidate_url_count": len(blocked),
        "needs_verification_candidate_url_count": len(needs_v),
    }


def enrich_live_result_with_content_verdict(
    live_result: dict[str, Any],
) -> dict[str, Any]:
    """
    live runner 결과 dict에 content verdict 필드를 추가하여 반환한다.
    기존 필드는 그대로 유지하고, 콘텐츠 판정 필드만 추가한다.
    """
    classified = classify_g2b_public_notice_content(live_result)
    enriched = dict(live_result)
    enriched["content_verdict"] = classified["content_verdict"]
    enriched["content_valid"] = classified["content_valid"]
    enriched["content_invalid_reason"] = classified["invalid_reason"]
    enriched["positive_signals"] = classified["positive_signals"]
    enriched["negative_signals"] = classified["negative_signals"]
    enriched["candidate_url_count"] = len(classified["candidate_urls"])
    enriched["safe_candidate_url_count"] = len(classified["safe_candidate_urls"])
    enriched["blocked_candidate_url_count"] = len(classified["blocked_candidate_urls"])
    return enriched
