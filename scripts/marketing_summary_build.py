"""건설공무 카페·유튜브 조사 결과를 admin-web 마케팅 탭용 JSON으로 정리.

신규 수집을 하지 않는다 — 이미 세션 중 확보한 데이터(data/cafe/*)를 읽어
요약만 한다. 유튜브 벤치마크는 API로 실측한 값을 그대로 옮겨 적었다(재수집 아님).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAFE_DETAIL = ROOT / "data" / "cafe" / "_month_full_detail_20260816.json"
CAFE_KEYWORD_TREND = ROOT / "data" / "cafe" / "건설공무_적산산출내역서단가_분석.xlsx"
OUT = ROOT / "data" / "marketing" / "summary_latest.json"

KEYWORDS = ["적산", "물량산출", "AI", "인공지능", "내역서", "자동화"]

METHODOLOGY = {
    "recent_full": {
        "source": "_month_full_detail_20260816.json",
        "period": "2026-07 ~ 2026-08 (약 6주)",
        "scope": "전체 게시판 무필터 전수 수집 (2,477건)",
    },
    "long_term_keyword": {
        "source": "건설공무_적산산출내역서단가_분석.xlsx",
        "period": "2025-09 ~ 2026-06 (10개월)",
        "scope": "'적산/산출/내역서/단가' 키워드로 사전 필터링된 게시판만 (월 30~180건)",
    },
    "caveat": (
        "두 데이터셋은 수집 범위가 달라 월별 건수를 직접 비교(병합)하면 안 된다. "
        "최근 데이터의 월평균 건수(1,157~1,317건)가 과거(30~179건)보다 7~40배 많은 건 "
        "활동 폭증이 아니라 수집 범위(키워드 필터 vs 전수) 차이다. "
        "장기 추이는 키워드 데이터로, 카페 전체 성격(노무·고용 이슈 비중 등)은 "
        "최근 전수 데이터로 판단한다 — 병합하지 않고 역할을 구분해 병기한다."
    ),
}


def top_cafe_posts(limit: int = 15) -> list[dict]:
    if not CAFE_DETAIL.exists():
        return []
    data = json.loads(CAFE_DETAIL.read_text(encoding="utf-8"))
    data.sort(key=lambda r: int(r.get("view_count") or 0), reverse=True)
    rows = []
    for r in data[:limit]:
        rows.append(
            {
                "title": r.get("title"),
                "board": r.get("board"),
                "view_count": int(r.get("view_count") or 0),
                "comment_count": int(r.get("comment_count") or 0),
                "date": r.get("date_str"),
            }
        )
    return rows


def keyword_cafe_posts(limit: int = 15) -> list[dict]:
    if not CAFE_DETAIL.exists():
        return []
    data = json.loads(CAFE_DETAIL.read_text(encoding="utf-8"))
    hits = [r for r in data if any(k in (r.get("title") or "") for k in KEYWORDS)]
    hits.sort(key=lambda r: int(r.get("view_count") or 0), reverse=True)
    rows = []
    for r in hits[:limit]:
        rows.append(
            {
                "title": r.get("title"),
                "board": r.get("board"),
                "view_count": int(r.get("view_count") or 0),
                "comment_count": int(r.get("comment_count") or 0),
                "date": r.get("date_str"),
            }
        )
    return rows


# 세션 중 YouTube Data API로 실측한 값(재수집 아님, 2026-08-16 기준 스냅샷)
YOUTUBE_BENCHMARKS = [
    {
        "title": "엑셀로 만드는 공사 계약 내역서 만들기",
        "channel": "기술자들",
        "views": 85246,
        "note": "건설공무 실무 검색군 전체 1위",
    },
    {
        "title": "재고관리 프로그램 사지 말고 직접 만들어 쓰세요 EP.11",
        "channel": "윤자동",
        "views": 370088,
        "note": "엑셀VBA, AI 에이전트 콘텐츠 최상위 벤치마크",
    },
    {
        "title": "[콘엑스AI] AI 공사 내역서 자동화 프로그램 사용법",
        "channel": "기술자들",
        "views": 8012,
        "note": "댓글이 실사용 문의형 — 신뢰도 가장 높은 경쟁 사례",
    },
    {
        "title": "AI로 견적서 자동화하는 법, 코딩 몰라도 됩니다",
        "channel": "윤자동",
        "views": 80107,
        "note": "Replit 활용, 댓글에 회의적 반응 혼재",
    },
    {
        "title": "클로드 쓴다면 당장 이거 써보세요(코워크)",
        "channel": "소소한 AI 입문노트",
        "views": 461454,
        "note": "실전 튜토리얼형 최상위, 댓글에 실사용 후기 다수",
    },
]

COMPETITORS = [
    {
        "name": "ConPublicAI (건설 공무·행정 AI 길잡이)",
        "url": "https://conpublicai.pages.dev/",
        "found_via": "건설공무 카페 게시글(2026-08-05, 조회수 151)",
        "assessment": "1인 개발 추정, 무료 모델(Gemini/Gemma) 기반 RAG 챗봇. "
        "국가계약법 조문을 정확히 인용하는 등 실제 작동 확인됨. "
        "법령 Q&A 단일 기능만 제공 — 적산/물량산출/내역서 자동화는 없음.",
    },
    {
        "name": "고려전산(EMS) 적산실무 강의",
        "url": None,
        "found_via": "카페 정기 협찬 광고",
        "assessment": "카페 운영진과 협찬 관계 — 유기적 무료 홍보글은 배척 리스크, 유료 광고는 진입 가능.",
    },
]

STRATEGY = {
    "target": {
        "track_a": "건설공무·적산 실무자 (네이버 '건설공무' 카페 24.3만명 규모)",
        "track_b": "건설업 종사자로 한정 (범용 사무직으로 확대하지 않음)",
    },
    "pricing": {
        "free": "물량산출 웹앱 1일 3건, PDF/이미지 다운로드(워터마크), 저장 불가. GPT 교육 콘텐츠 전부 무료 공개.",
        "individual": "월 1.9만~2.9만원 — 무제한 사용, xlsx 다운로드, 결과 저장/이력, 내역서 자동 연동.",
        "b2b": "견적 기반 — 다중 사용자, 배치 처리, 사내 단가표 연동, 전담 지원.",
    },
    "positioning": "얼굴 비공개 + 본인 육성 + '건설 전문 AI 강사' 브랜딩 + 법적 근거 인용 + 본인 건설경력 신뢰",
    "distribution": [
        "유튜브 검색 SEO (검증된 제목 패턴: 'OO 만드는 법', 'OO 1초 완성', 'OO A to Z')",
        "카페는 유기적 홍보 금지 — conpublicai처럼 '정보공유' 톤으로만 접근, 유료 광고는 별도 검토",
        "경쟁 영상 댓글, 카카오 오픈채팅, 디시인사이드 등 보조 채널",
    ],
}

CONTENT_PLAN = [
    {
        "track": "A",
        "title": "GPT로 실무자가 직접 만드는 내역서 자동화 웹앱",
        "status": "1순위 — 카페·유튜브 데이터 교집합",
    },
    {
        "track": "B",
        "title": "물량산출 완성품 데모(제작과정 비공개, 결과만 시연)",
        "status": "A 영상 말미 CTA로 자연 연결",
    },
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_note": "2026-08-16 세션 데이터 기준 정리 (재수집 아님)",
        "cafe_top_posts": top_cafe_posts(),
        "cafe_keyword_posts": keyword_cafe_posts(),
        "youtube_benchmarks": YOUTUBE_BENCHMARKS,
        "competitors": COMPETITORS,
        "strategy": STRATEGY,
        "content_plan": CONTENT_PLAN,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {OUT}")


if __name__ == "__main__":
    main()
