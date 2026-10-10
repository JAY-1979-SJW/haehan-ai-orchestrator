"""건설 블로그 주제 리서치 파이프라인 — 3중 검증 자동화.

1. 건설공무카페 수집 데이터(data/cafe/gunmu_all_boards/)에서 제목 키워드 빈도 집계
2. 네이버 검색광고 키워드도구로 실제 월간 검색량 조회 (scripts.naver.searchad)
3. 검색량 상위 키워드에 대해 네이버 지식iN 실제 질문 제목 조회
   (scripts.naver.shopping.kin_client)
4. 반복 등장(2회 이상)하는 실제 질문을 우선해 블로그 주제 후보로 저장

카페 언급만 봐서는 "카페 안에서만 화제"인지 구분이 안 되고(예: 실적신고),
검색량만 봐서는 "정확히 뭘 궁금해하는지" 모른다(예: 나라장터). 세 단계를
교차 검증해야 실제 콘텐츠 각도가 나온다.

출력: data/blog_topic_research_latest.json
      {"generated_at", "keywords": [...], "topics": [...]}

scripts/naver/blog/cli/blog_ai_batch_20.py 는 이 파일이 있으면(30일 이내) TOPIC_SEED
대신 이 결과를 우선 사용한다.

사용:
    python -m scripts.naver.blog.cli.research_blog_topics
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv  # noqa: E402

from scripts.common.logger import get_logger  # noqa: E402

load_dotenv(_ROOT / ".env", encoding="utf-8")

_log = get_logger(__name__)

BOARDS_DIR = _ROOT / "data" / "cafe" / "gunmu_all_boards"
OUT_PATH = _ROOT / "data" / "blog_topic_research_latest.json"

_GENERIC_WORDS = {
    "문의",
    "문의드립니다",
    "드립니다",
    "질문드립니다",
    "도와주세요",
    "되나요",
    "안녕하세요",
    "문의드려요",
    "경우",
    "질문입니다",
    "기준",
    "방법",
    "작성",
    "있습니다",
    "공무",
    "공사",
    "현장",
    "건설",
    "건축",
    "여부",
    "전문",
    "등록",
    "가입",
    "취득",
    "정산",
    # 지식iN에서 다른 업종/일상 주제로 새는 단독 일반어 (복합어는 통과시킴, 예: 건강보험)
    "질문",
    "어떻게",
    "생각",
    "건강",
    "채용",
    "모집",
    "구합니다",
    "구인",
    "관련",
    "확인",
    "처리",
    "정도",
    "궁금",
    "직원",
    "본사",
    "부탁드립니다",
}

# 건설업 밖에서는 쓰이지 않아 그대로 검색해도 결과가 깨끗한 전용어.
# 여기 없는 키워드는 지식iN 검색 시 "건설업 " 접두를 붙여 문맥을 강제한다.
_CONSTRUCTION_SPECIFIC_KEYWORDS = {
    "하도급지킴이",
    "키스콘",
    "건설e음",
    "건설E음",
    "안전관리계획서",
    "관급공사",
    "흙막이",
    "일용근로자",
    "적격심사",
    "현장대리인",
    "안전관리자",
    "고용산재",
    "퇴직공제",
    "실적신고",
    "노무비",
}

_MIN_SEARCH_VOLUME = 500  # 이 이상만 실제 콘텐츠 대상으로 채택
_TOP_KEYWORD_COUNT = 15  # 지식iN까지 조회할 상위 키워드 수
_KIN_DISPLAY = 10


def _load_cafe_titles() -> list[str]:
    titles = []
    seen = set()
    for fp in sorted(BOARDS_DIR.glob("*.json")):
        if fp.name == "_summary.json":
            continue
        try:
            items = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001 - 블로그 주제 리서치용 캐시 JSON 로드(읽기전용) - 로드 실패 시 경고 로그 후 해당 파일 skip
            _log.warning("[research] 로드 실패 %s: %s", fp, e)
            continue
        for a in items:
            aid = a.get("article_id")
            if not aid or aid in seen:
                continue
            seen.add(aid)
            titles.append(a.get("title", ""))
    return titles


def _top_keyword_candidates(titles: list[str], top_n: int = 40) -> list[tuple[str, int]]:
    """2글자 단어는 건설 문맥과 무관한 다른 업종/일상 화제로 새는 경우가 많아
    (예: 연금, 시공, 서류, 신고, 휀스) 3글자 이상 복합어만 후보로 삼는다."""
    counter: Counter[str] = Counter()
    for title in titles:
        for tok in re.findall(r"[가-힣]{3,}", title):
            if tok not in _GENERIC_WORDS:
                counter[tok] += 1
    return counter.most_common(top_n)


def _search_volume(candidates: list[tuple[str, int]]) -> list[dict]:
    from scripts.naver.searchad.keyword_tool import keyword_search_volume

    return keyword_search_volume(candidates, "cafe_freq")


def _real_questions(keyword_rows: list[dict]) -> list[dict]:
    from scripts.naver.shopping.kin_client import search_kin_questions

    topics = []
    for row in keyword_rows[:_TOP_KEYWORD_COUNT]:
        if row["total_search"] < _MIN_SEARCH_VOLUME:
            continue
        kw = row["keyword"]
        # 건설업 전용어(하도급지킴이, 키스콘 등)는 그대로 검색해도 결과가 깨끗하지만,
        # 나라장터/국민연금/건강보험처럼 업종 불문 범용어는 지식iN 검색이 일반인
        # 개인 질문(아르바이트생 국민연금가입 등)까지 섞어와 "건설업" 문맥을 강제한다.
        kin_query = kw if kw in _CONSTRUCTION_SPECIFIC_KEYWORDS else f"건설업 {kw}"
        questions = search_kin_questions(kin_query, display=_KIN_DISPLAY)
        time.sleep(0.3)
        if not questions:
            continue

        # 지식iN 응답의 HTML 엔티티(&quot; 등) 해제, 말줄임표로 잘린 제목/설명은
        # 블로그 주제·인용 근거로 쓰기엔 불완전해 제외.
        clean = {}
        for q in questions:
            t = html.unescape(q["title"]).strip()
            d = html.unescape(q.get("description", "")).strip()
            if t and not t.endswith("....") and t not in clean:
                clean[t] = d if not d.endswith("....") else ""
        title_counts = Counter(clean.keys())
        for title, count in title_counts.most_common(5):
            topics.append(
                {
                    "keyword": kw,
                    "question_title": title,
                    "question_description": clean[title],
                    "repeat_count": count,
                    "cafe_freq": row["cafe_freq"],
                    "search_volume": row["total_search"],
                    "competition": row["competition"],
                }
            )
    # docId 중복 제거 후에는 진짜 반복 질문이 드물어(실측: 74건 중 2~3건) 반복
    # 신호만으로 우선순위를 매기지 않는다. 검색량(실수요 크기) 우선, 반복은 보조 신호.
    topics.sort(key=lambda t: (-t["search_volume"], -t["repeat_count"]))
    return topics


def run_research() -> dict:
    titles = _load_cafe_titles()
    _log.info("[research] 카페 게시글 %d건 로드", len(titles))
    if not titles:
        _log.warning("[research] 카페 데이터 없음 — data/cafe/gunmu_all_boards/ 먼저 수집 필요")
        return {"ok": False, "reason": "no_cafe_data"}

    candidates = _top_keyword_candidates(titles)
    _log.info("[research] 후보 키워드 %d개 추출", len(candidates))

    keyword_rows = _search_volume(candidates)
    _log.info("[research] 검색량 조회 완료 — 상위: %s", [r["keyword"] for r in keyword_rows[:5]])

    topics = _real_questions(keyword_rows)
    _log.info("[research] 실제 질문 기반 주제 %d개 확보", len(topics))

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cafe_post_count": len(titles),
        "keywords": keyword_rows,
        "topics": topics,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _log.info("[research] 저장 완료: %s", OUT_PATH)
    return {"ok": True, **result}


if __name__ == "__main__":
    r = run_research()
    print(json.dumps({k: v for k, v in r.items() if k != "keywords"}, ensure_ascii=False, indent=2)[:3000])
