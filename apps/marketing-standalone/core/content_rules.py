"""발행 전 본문 SEO/품질 점검 — 순수 로직, 외부 미의존 (L1).

원본: scripts/naver/blog/marketing/content.py
차이점: generate_post()(GPT 자동생성, 2026-08-19부터 차단됨)는 이식하지
않았다. 이 앱에서는 사람(또는 운영자)이 직접 쓴 원고를 seo_check()로
점검만 한다.
"""

from __future__ import annotations

import re

TARGET_BODY_CHARS = 3500
MIN_BODY_CHARS = 2500
MIN_TAG_COUNT = 15
TARGET_TAG_COUNT = 25


def seo_check(*, title: str, body: str, keywords: list[str]) -> dict:
    """발행 전 최소 SEO 점검. 차단하지 않고 경고만 남긴다(사람이 최종 확인)."""
    warnings = []
    if not (20 <= len(title) <= 60):
        warnings.append(f"제목 길이 {len(title)}자 (권장 20~60자)")
    if len(body) < MIN_BODY_CHARS:
        warnings.append(f"본문 {len(body)}자 (최소 {MIN_BODY_CHARS}자 미달 — 답이 덜 담겼을 수 있음)")
    main_kw = keywords[0] if keywords else ""
    if main_kw and main_kw not in title:
        warnings.append(f"핵심 키워드 '{main_kw}'가 제목에 없음")
    if main_kw and body.count(main_kw) < 2:
        warnings.append(f"핵심 키워드 '{main_kw}' 본문 출현 {body.count(main_kw)}회 (권장 2회 이상)")
    if len(keywords) < MIN_TAG_COUNT:
        warnings.append(
            f"태그 {len(keywords)}개 (최소 {MIN_TAG_COUNT}개, 목표 {TARGET_TAG_COUNT}개 — "
            "상위노출 경쟁 글 실측 기준, 관련어를 최대한 뽑아 채울 것)"
        )
    if "##" in body:
        warnings.append("마크다운 소제목(##) 잔존 — 네이버는 렌더링하지 않음")
    if "[" not in body:
        warnings.append("소제목([ ]) 구조 없음")

    weak = _weak_writing(body)
    if weak:
        warnings.append(f"내용 없는 표현 {len(weak)}건: {', '.join(weak[:3])}")
    if not re.search(r"\[정리하면|\[결론|정리하면 이", body):
        warnings.append("결론 문단 없음 — 설명만 하고 답을 안 낸 글일 수 있음")

    risky = _risky_claims(body)
    if risky:
        warnings.append(f"검증 필요 수치 {len(risky)}건: {', '.join(risky[:3])}")

    ai_ratio = _ai_section_ratio(body)
    if ai_ratio > 0.35:
        warnings.append(f"AI 섹션 비중 {ai_ratio:.0%} (권장 20~25%, 실무 답변이 본체여야 함)")
    return {"ok": not warnings, "warnings": warnings, "ai_ratio": ai_ratio}


def _weak_writing(body: str) -> list[str]:
    """정보가 0인 일반론 표현을 찾는다."""
    phrases = [
        "복잡할 수 있습니다",
        "중요합니다",
        "필요합니다만",
        "정확한 이해가 필요",
        "주의가 필요합니다",
        "다양한 요소",
        "여러 가지가 있습니다",
        "말씀드리겠습니다",
    ]
    return [ph for ph in phrases if ph in body]


def _risky_claims(body: str) -> list[str]:
    """AI가 지어내기 쉬운 단정적 수치·법령 표현을 찾아 경고 목록으로 돌려준다."""
    pats = [
        (r"\d{4}년\s*[가-힣]*법", "법령 연도"),
        (r"제?\s*\d+조", "법 조항"),
        (r"\d+(\.\d+)?\s*%", "요율"),
        (r"\d{1,3},\d{3}\s*원", "금액"),
    ]
    hits: list[str] = []
    for pat, label in pats:
        for m in re.finditer(pat, body):
            frag = m.group(0)
            if label == "요율" and frag.strip().replace(" ", "") in {"100%", "0%", "10%", "50%"}:
                continue
            hits.append(f"{label}({frag})")
    return list(dict.fromkeys(hits))


def _ai_section_ratio(body: str) -> float:
    """'AI' 소제목 아래 섹션이 전체 본문에서 차지하는 비중."""
    lines = body.split("\n")
    h2_idx = [
        i
        for i, ln in enumerate(lines)
        if re.match(r"^##\s", ln.strip()) or re.match(r"^\[[^\]]{2,30}\]\s*$", ln.strip())
    ]
    ai_headings = [i for i in h2_idx if "AI" in lines[i]]
    if not ai_headings or len(body) == 0:
        return 0.0
    start = ai_headings[0]
    later = [i for i in h2_idx if i > start]
    end = later[0] if later else len(lines)
    section_text = "\n".join(lines[start:end])
    return len(section_text) / len(body)


def split_body(body: str, parts: int = 3) -> list[str]:
    """본문을 단락(빈 줄) 기준으로 parts 등분. 이미지를 글 중간에 끼우기 위해 사용."""
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    if len(paragraphs) < parts:
        chunk = max(1, len(body) // parts)
        return [body[i * chunk : (i + 1) * chunk].strip() for i in range(parts)]

    per = len(paragraphs) // parts
    segments = []
    for i in range(parts):
        start = i * per
        end = (i + 1) * per if i < parts - 1 else len(paragraphs)
        segments.append("\n\n".join(paragraphs[start:end]))
    return segments
