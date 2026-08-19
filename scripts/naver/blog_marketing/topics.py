"""주제 선정 - 리서치 결과 로드, 발행 캐시, AI 보충 생성.

scripts/ops/research_blog_topics.py 가 만드는 data/blog_topic_research_latest.json
(카페 빈도 + 네이버 검색광고 실검색량 + 지식iN 실제 질문 3중 검증)을 우선 사용한다.
AI는 주제를 새로 지어내지 않고 실제 질문을 그대로 쓰는 것이 원칙 - 리서치 풀이
부족할 때만 나머지를 AI로 보충 생성한다(이 보충분은 인용 근거가 없음).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from scripts.logger import get_logger
from scripts.naver.automation.ai_responder import AIResponder

_log = get_logger(__name__)

CACHE_FILE = Path("data/blog_topic_cache.json")
RESEARCH_FILE = Path("data/blog_topic_research_latest.json")
_RESEARCH_MAX_AGE_DAYS = 30

# 건설 실무 블로그 주제 풀 - RESEARCH_FILE이 없거나 30일 넘게 오래됐을 때만 쓰는
# 고정 폴백. 2026-08-17 스냅샷: 건설공무카페 키워드 언급 빈도 + 네이버 검색광고
# 실검색량 + 네이버 지식iN 실제 질문 제목 3중 검증으로 작성. 기존 "AI 연구 소개"류는
# 실제 검색 수요와 무관해(방문자 0) 폐기.
FALLBACK_TOPIC_SEED = [
    # 나라장터 (월 68만 검색, 경쟁 낮음) - 실제 질문 기반
    "나라장터 입찰대리인과 소속회원, 차이가 뭘까",
    "나라장터 입찰 시 법인 공동인증서 꼭 필요할까",
    "나라장터 정량적 제안서 vs 정성적 제안서, 뭐가 다른가",
    "나라장터 공동수급체 등록 방법과 주의사항",
    # 국민연금/건강보험 (합산 월 25만 검색) - "사업장가입자 미납" 반복 질문
    "국민연금 사업장가입자 미납, 어떻게 처리하나",
    "건설업 국민연금 사업장 성립신고 완전정리",
    "일용직 건강보험·국민연금 가입기준 총정리 (2026년 기준)",
    # 하도급지킴이 (월 4.8만 검색, 경쟁 낮음) - 실제 질문 기반
    "하도급지킴이 노무비계좌 오지급, 이럴 땐 이렇게",
    "하도급지킴이 확약서 작성란, 어떻게 써야 하나",
    "하도급지킴이 기성청구 절차 총정리",
    # 키스콘 - "법인은 살아있는데 조회 안 됨" 반복 질문(3회)
    "키스콘 조회가 안 될 때 확인해야 할 것들",
    "키스콘 변경통보 지연 과태료, 얼마나 나올까",
    "키스콘 원도급 등록 방법과 절차",
    # 고용산재 - "미승인 하수급인사업장" 반복 질문(3회)
    "고용산재 보수총액신고서, 미승인 하수급인사업장이 있을 때",
    "고용산재보험료 신고서 작성법 — 일용직 사업장 기준",
    # 퇴직공제/전자카드(EUM)
    "건설근로자 퇴직공제 가입대상, 나도 해당될까",
    "건설e음 전자카드 정보변경, 앱에서 하는 방법",
    "건설e음 전자카드 퇴직공제 임금대장 수정 방법",
    # 안전관리 - "꼭 포함해야 할 요소" 반복 질문(2회)
    "안전관리계획서, 꼭 포함해야 할 요소는 무엇일까",
    "안전관리자 배치기준 — 공사금액별로 다른 이유",
    # 실적신고/입찰(카페 화제성은 높지만 검색량은 낮음 — 니치 보완용)
    "건설업 실적신고 처음인데 어떻게 하나 (2026년 기준)",
    "전문건설업 겸업 시 실적신고 기준",
    # 행정처분/영업정지
    "건설업 등록기준 미달, 영업정지를 피하려면",
]


# ── 캐시 관리 ─────────────────────────────────────────────────────────────


def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"topics": [], "posted": []}


def save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def topic_key(title: str) -> str:
    return hashlib.md5(title.strip().lower().encode()).hexdigest()[:12]


def is_duplicate(title: str, cache: dict) -> bool:
    key = topic_key(title)
    used_keys = {p.get("key") for p in cache.get("posted", [])}
    used_titles = {p.get("title", "").strip().lower() for p in cache.get("posted", [])}
    return key in used_keys or title.strip().lower() in used_titles


# ── 리서치 결과 로드 ─────────────────────────────────────────────────────────


# 이 블로그의 목적은 AI 적산·물량산출·내역서 자동화 프로그램 영업이다(2026-08-20 확인).
# 검색량이 크다고 아무 주제나 쓰면 "방문자는 늘지만 고객이 아닌 사람"이 모인다.
# 실제로 하도급지킴이(월 47,670)·국민연금(249,000) 글로 유입은 생겼지만 제품과
# 연결이 전혀 없었다. 제품과 이어지는 키워드로 좁힌다.
PRODUCT_KEYWORDS = (
    "일위대가",
    "내역서",
    "원가계산",
    "제비율",
    "적산",
    "물량",
    "산출",
    "노무비",
    "재료비",
    "경비",
    "간접공사비",
    "품셈",
    "단가",
    "견적",
    "설계변경",
    "기성",
    "도면",
    "수량",
)


# 제품 키워드가 스쳐 지나갈 뿐 실제로는 무관한 주제를 걸러낸다.
# 예: "하도급지킴이 노무비계좌로 준공금이 잘못 지급된 경우" — '노무비'가 있지만
# 대금 지급 문제이지 적산과 무관하다.
EXCLUDE_KEYWORDS = (
    "하도급지킴이",
    "키스콘",
    "국민연금",
    "건강보험",
    "고용보험",
    "산재",
    "취득신고",
    "상실신고",
    "인센티브",
    "퇴직",
    "실업급여",
    "면허",
    "자격증",
)


def is_product_related(topic: dict) -> bool:
    """제품(적산·물량산출·내역서 자동화)과 연결되는 주제인지.

    행정신고·보험 주제는 검색량이 커도 제외한다. 방문자는 늘지만 적산
    프로그램 고객이 아니라 전환이 되지 않는다(2026-08-20 판단).
    """
    text = f"{topic.get('keyword', '')} {topic.get('question_title', '')}"
    if any(x in text for x in EXCLUDE_KEYWORDS):
        return False
    return any(k in text for k in PRODUCT_KEYWORDS)


def get_researched_topics(product_only: bool = True) -> list[dict]:
    """3중 검증 리서치 결과(30일 이내)를 원본 그대로(질문+설명 포함) 반환.

    실제 발행 시 이 description을 본문 인용 근거로 쓴다 — AI가 주제를
    새로 지어내지 않고 실제 지식iN 질문에 답하는 형태로 작성하기 위함.
    """
    if not RESEARCH_FILE.exists():
        return []
    try:
        data = json.loads(RESEARCH_FILE.read_text(encoding="utf-8"))
        generated_at = datetime.fromisoformat(data["generated_at"])
        age_days = (datetime.now() - generated_at).days
        if age_days <= _RESEARCH_MAX_AGE_DAYS and data.get("topics"):
            topics = data["topics"]
            if product_only:
                filtered = [t for t in topics if is_product_related(t)]
                _log.info(
                    "[topic-seed] 리서치 결과 %d개 중 제품 관련 %d개 사용 (%d일 전)",
                    len(topics),
                    len(filtered),
                    age_days,
                )
                if filtered:
                    return filtered
                _log.warning("[topic-seed] 제품 관련 주제가 없어 전체를 사용합니다")
            return topics
    except Exception as e:
        _log.warning("[topic-seed] 리서치 파일 로드 실패, 폴백 사용: %s", e)
    return []


def get_topic_seed() -> list[str]:
    """참고용 주제 제목 목록. 리서치 결과가 있으면 그 제목들, 없으면 고정 폴백."""
    researched = get_researched_topics()
    if researched:
        return [t["question_title"] for t in researched if t.get("question_title")]
    _log.info("[topic-seed] 고정 폴백 목록 사용 (%d개)", len(FALLBACK_TOPIC_SEED))
    return FALLBACK_TOPIC_SEED


# ── 주제 선정 ─────────────────────────────────────────────────────────────


def generate_topics(cache: dict, count: int, dry_run: bool = False) -> list[dict]:
    """캐시에 없는 건설 실무 주제 count개 생성.

    실검증 리서치 결과(지식iN 실제 질문)가 있으면 AI가 주제를 새로 지어내지
    않고 그 질문들을 그대로 사용한다 — "정확한 정보 인용" 요건 충족. 리서치
    결과가 count에 부족할 때만 나머지를 AI가 보충 생성한다.
    """
    researched = get_researched_topics()
    used_titles = [p.get("title", "") for p in cache.get("posted", [])]

    result: list[dict] = []
    for t in researched:
        title = t.get("question_title", "")
        if title and not is_duplicate(title, cache) and len(result) < count:
            result.append(
                {
                    "topic": title,
                    "keywords": [t["keyword"], "건설실무", "건설업"],
                    "angle": "지식iN 실제 질문에 답하는 실무 가이드",
                    "source_description": t.get("question_description", ""),
                }
            )

    if dry_run:
        print("\n[DRY-RUN] 주제 선정 (리서치 결과 직접 사용, AI 미호출)")
        print(f"  요청 수: {count}개 / 리서치 매칭: {len(result)}개")
        print(f"  기존 캐시 주제 수: {len(used_titles)}개")
        return result[:count]

    remaining = count - len(result)
    if remaining <= 0:
        return result[:count]

    # 리서치 풀이 부족한 나머지만 AI로 보충 생성 (source_description 없음 — 인용 없이 일반 작성)
    topic_seed = get_topic_seed()
    used_str = "\n".join(f"- {t}" for t in used_titles[-50:]) if used_titles else "(없음)"
    prompt = f"""당신은 한국 건설업 실무 블로그 전문 작가입니다.
아래 이미 사용한 주제와 겹치지 않는 건설 실무 관련 블로그 주제 {remaining}개를 생성하세요.

[이미 사용한 주제]
{used_str}

[참고 주제 풀]
{chr(10).join("- " + t for t in topic_seed)}

출력 형식 (JSON 배열, 다른 텍스트 없이):
[
  {{"topic": "주제명", "keywords": ["키워드1", "키워드2", "키워드3"], "angle": "독특한 접근 각도"}},
  ...
]

조건:
- 나라장터, 국민연금·건강보험, 하도급지킴이, 키스콘, 퇴직공제, 전자카드(건설e음),
  고용산재, 안전관리, 실적신고, 입찰, 행정처분 등 건설 실무 관련
- 참고 주제 풀처럼 실검색량이 검증된 키워드를 제목에 포함
- 주제가 서로 겹치지 않게
- 한국 건설업 실무자 대상, 실용적·정보성 주제(체크리스트, 절차 안내, 기준 정리 등)
- 이미 사용한 주제와 유사한 것도 제외"""

    ai = AIResponder()
    r = ai._call(
        "한국 블로그 AI 주제 생성 전문가",
        prompt,
        max_tokens=2000,
    )
    if not r.get("ok"):
        _log.error("주제 생성 실패: %s", r)
        return result

    text = r["text"].strip()
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        _log.error("JSON 파싱 실패: %s", text[:200])
        return result

    try:
        topics = json.loads(text[start:end])
    except Exception as e:
        _log.error("JSON 파싱 오류: %s | %s", e, text[start:end][:200])
        return result

    # 중복 필터 (AI 보충분에는 인용 근거가 없음)
    filtered = [t for t in topics if not is_duplicate(t.get("topic", ""), cache)]
    return (result + filtered)[:count]
