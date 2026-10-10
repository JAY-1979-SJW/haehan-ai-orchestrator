"""조명·인테리어(skyjwshin) 블로그 주제 리서치 — 오늘의집 커뮤니티 기반 3중 검증.

건설 블로그(research_blog_topics.py)와 같은 구조를 쓰되, "카페 빈도" 자리를
카페 대신 **오늘의집 커뮤니티 검색 결과**로 채운다. skyjwshin은 사용자
소유 카페(haehan)뿐이라 편향을 피하려 공공 커뮤니티를 쓰기로 했다
(2026-08-24 사용자 결정). 오늘의집 외 클리앙·뽐뿌·82cook·네이트판도
조사했지만 이번엔 오늘의집만 검증 완료([[ohou-community-research]] 참조).

## 범위 — 조명 전용 → 조명+인테리어 전반 (2026-08-24 확장 결정)
처음엔 시드를 "조명" 관련어로만 좁혔었다. 사용자가 "오늘의집에서 인테리어
관련되어서도 모두 조사했나?"라고 물었고, 확인해보니 인테리어 일반어
(아파트·침대·리모델링·인테리어 등)를 전부 불용어로 걸러내고 있었다.
`accounts.py`의 skyjwshin 도메인이 원래 "조명인테리어"로 등록돼 있던
것과도 맞춰 범위를 인테리어 전반으로 넓혔다 — 조명 전용 SEED만으로는
자취·원룸·셀프인테리어 쪽 페인포인트가 안 잡혔다.

1. 조명 시드 키워드로 오늘의집 커뮤니티 검색 → 실제 게시글 제목/본문 수집
2. 게시글에서 반복 등장하는 키워드 후보 추출
3. 네이버 검색광고 키워드도구로 실제 월간 검색량 조회 (scripts.naver.searchad,
   건설 파이프라인과 동일 함수 재사용)
4. 검색량 상위 키워드로 지식iN 실제 질문 조회
   (scripts.naver.shopping.kin_client, 동일 함수 재사용)

출력: data/blog_topic_research_lighting_latest.json

사용:
    python -m scripts.naver.blog.cli.research_blog_topics_lighting
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

from scripts.community.sites.ohou import search_community  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402

load_dotenv(_ROOT / ".env", encoding="utf-8")

_log = get_logger(__name__)

OUT_PATH = _ROOT / "data" / "blog_topic_research_lighting_latest.json"

# 조명+인테리어 도메인 진입점 — 검증된 키워드 풀이 아직 없어(카페 데이터
# 부재) 최소 출발점만 잡는다. 이 시드로 오늘의집을 검색해 나온 실제
# 게시글에서 후보 키워드를 뽑는 게 목적이라, 시드 자체가 최종 주제가
# 되지는 않는다.
SEED_QUERIES = [
    # 조명 (원래 시드)
    "조명",
    "거실조명",
    "방등",
    "스탠드조명",
    "무드등",
    "펜던트조명",
    "조명교체",
    "led조명",
    # 인테리어 전반 (2026-08-24 추가 — accounts.py 도메인 "조명인테리어"에 맞춤)
    "셀프인테리어",
    "원룸꾸미기",
    "자취방인테리어",
    "집들이",
    "가구배치",
    "인테리어꿀팁",
]

# 2026-08-24 실측(오늘의집 시드 검색 48건, 중복제거 35건)에서 확인된
# 콘텐츠 각도 없는 일반어. 건설 파이프라인의 _GENERIC_WORDS와 같은 역할.
_GENERIC_WORDS = {
    "이렇게",
    "화이트",
    "곳곳에",
    "가장",
    "놓고",
    "만나기전에",
    "정리했어요",
    "도움부탁드려요",
    "시작한",
    "분위기를",
    "싶은",
    "공간에",
    "포인트를",
    "무드를",
    "같은",
    "어디에",
    "느낌이",
    "생각",
    "궁금",
    "추천해주세요",
    "추천해주세여",
    "좋을까요",
    "좋을까융",
    "합니다",
    "있어요",
    "했어요",
    # 2026-08-24 3차 실측 — 검색량 API가 준 상위권에 섞인 순수 조사/부사
    # (아무 문장에나 붙는 말이라 조명이든 인테리어든 콘텐츠 각도가 없음)
    # + 무관 브랜드 노이즈 1건.
    "바로",
    "어떻게",
    "이런",
    "다시",
    "캐치웰",  # 무선청소기 브랜드 — 우연히 "조명" 언급 글에 섞여 들어옴
    "커피",  # 조명/인테리어 둘 다와 무관(커피테이블 아닌 음료 얘기로 확인됨)
    # 주의: "아파트"·"침대"·"오브제"·"테이블"·"인테리어"·"리모델링"은
    # 범위를 조명 전용에서 조명+인테리어로 넓히며(위 docstring 참조)
    # 불용어에서 제외했다 — 지금은 유효한 주제 후보다.
}

# 2026-08-24 4차 — 오늘의집 단독 분석(검색광고 필터 없이 순수 빈도표)에서
# "있는","너무","제가","도와주세요" 같은 조사/부사/서술어가 상위권에 그대로
# 남는 걸 확인했다. 하나씩 리스트에 추가하는 건 밑 빠진 독이라(다음 도메인
# 리서치를 만들 때마다 반복될 문제), **어미 패턴으로 걸러내는 규칙**을
# 추가한다 — "~습니다/해요/네요/까요/거나" 등으로 끝나는 토큰은 거의 항상
# 서술어/부사이지 콘텐츠 키워드(명사)가 아니다.
_PREDICATE_SUFFIX_RE = re.compile(
    r"(습니다|합니다|했어요|해요|네요|까요|어요|아요|세요|거나|는데|은데|더라구요|"
    r"드려요|드립니다|였어요|이에요|예요|이네요|있어요|있나요|이나요|고요|지요|죠)$"
)
# 순수 대명사/부사 — 어미 규칙으로 안 걸러지는 짧은 기능어.
_PRONOUN_ADVERB_WORDS = {
    "제가",
    "저는",
    "저희",
    "우리",
    "너무",
    "정말",
    "많이",
    "이거",
    "저거",
    "그거",
    "이건",
    "저건",
    "그건",
    "이게",
    "저게",
    "그게",
    "그리고",
    "하지만",
    "그런데",
    "특히",
    "직접",
    "훨씬",
    "따로",
}
# 존재/소유 동사(있다·없다) 활용형 — "는/어/고/음" 등 어미가 짧고 다양해
# 정규식 한 줄로 못 잡는다. 콘텐츠 각도가 전혀 없는 말이라 통째로 막는다.
_EXISTENTIAL_VERB_FORMS = {
    "있는",
    "있어",
    "있고",
    "있음",
    "있지",
    "있을",
    "있게",
    "있던",
    "없는",
    "없어",
    "없고",
    "없음",
    "없지",
}


def _is_stopword(tok: str) -> bool:
    return (
        tok in _GENERIC_WORDS
        or tok in _PRONOUN_ADVERB_WORDS
        or tok in _EXISTENTIAL_VERB_FORMS
        or bool(_PREDICATE_SUFFIX_RE.search(tok))
    )


_MIN_SEARCH_VOLUME = 500
_TOP_KEYWORD_COUNT = 15
_KIN_DISPLAY = 10


def _collect_ohou_posts(seeds: list[str]) -> list[dict]:
    posts: list[dict] = []
    seen: set[str] = set()
    for q in seeds:
        try:
            r = search_community(q)
        except Exception as e:  # noqa: BLE001 - 커뮤니티 검색 기반 블로그 주제 리서치(읽기전용) - 검색 실패 시 경고 로그 후 해당 검색어만 skip
            _log.warning("[research-lighting] '%s' 검색 실패: %s", q, e)
            continue
        for p in r.get("posts", []):
            url = p.get("url", "")
            if url and url not in seen:
                seen.add(url)
                posts.append(p)
        time.sleep(1.0)
    return posts


def _top_keyword_candidates(posts: list[dict], top_n: int = 40) -> list[tuple[str, int]]:
    """2글자 이상 한글 복합어 후보. 건설과 달리 조명 용어는 2글자가 많아
    (등, 등기구 등 제외하고) 3글자 미만도 허용하되 불용어로 걸러낸다."""
    counter: Counter[str] = Counter()
    for p in posts:
        text = p.get("title", "") + " " + p.get("snippet", "")
        for tok in re.findall(r"[가-힣]{2,}", text):
            if not _is_stopword(tok):
                counter[tok] += 1
    return counter.most_common(top_n)


def _search_volume(candidates: list[tuple[str, int]]) -> list[dict]:
    from scripts.naver.searchad.keyword_tool import keyword_search_volume

    return keyword_search_volume(candidates, "ohou_freq")


def _real_questions(keyword_rows: list[dict]) -> list[dict]:
    from scripts.naver.shopping.kin_client import search_kin_questions

    topics = []
    for row in keyword_rows[:_TOP_KEYWORD_COUNT]:
        if row["total_search"] < _MIN_SEARCH_VOLUME:
            continue
        kw = row["keyword"]
        kin_query = f"조명 {kw}" if "조명" not in kw else kw
        questions = search_kin_questions(kin_query, display=_KIN_DISPLAY)
        time.sleep(0.3)
        if not questions:
            continue

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
                    "ohou_freq": row["ohou_freq"],
                    "search_volume": row["total_search"],
                    "competition": row["competition"],
                }
            )
    topics.sort(key=lambda t: (-t["search_volume"], -t["repeat_count"]))
    return topics


def run_research() -> dict:
    posts = _collect_ohou_posts(SEED_QUERIES)
    _log.info("[research-lighting] 오늘의집 게시글 %d건 수집(중복제거)", len(posts))
    if not posts:
        _log.warning("[research-lighting] 오늘의집 데이터 없음")
        return {"ok": False, "reason": "no_ohou_data"}

    candidates = _top_keyword_candidates(posts)
    _log.info("[research-lighting] 후보 키워드 %d개 추출", len(candidates))

    keyword_rows = _search_volume(candidates)
    _log.info("[research-lighting] 검색량 조회 완료 — 상위: %s", [r["keyword"] for r in keyword_rows[:5]])

    topics = _real_questions(keyword_rows)
    _log.info("[research-lighting] 실제 질문 기반 주제 %d개 확보", len(topics))

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "ohou_community",
        "ohou_post_count": len(posts),
        "keywords": keyword_rows,
        "topics": topics,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _log.info("[research-lighting] 저장 완료: %s", OUT_PATH)
    return {"ok": True, **result}


if __name__ == "__main__":
    r = run_research()
    print(json.dumps({k: v for k, v in r.items() if k != "keywords"}, ensure_ascii=False, indent=2)[:3000])
