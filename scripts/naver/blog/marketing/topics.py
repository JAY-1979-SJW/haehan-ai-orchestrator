"""주제 선정 - 리서치 결과 로드, 발행 캐시, AI 보충 생성.

scripts/naver/blog/cli/research_blog_topics.py 가 만드는 data/blog_topic_research_latest.json
(카페 빈도 + 네이버 검색광고 실검색량 + 지식iN 실제 질문 3중 검증)을 우선 사용한다.
AI는 주제를 새로 지어내지 않고 실제 질문을 그대로 쓰는 것이 원칙 - 리서치 풀이
부족할 때만 나머지를 AI로 보충 생성한다(이 보충분은 인용 근거가 없음).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.logger import get_logger
from scripts.naver.automation.integration.ai_responder import AIResponder
from scripts.naver.blog.accounts import cache_file_for

_log = get_logger(__name__)

# 2026-08-24: 계정이 skyjwsin 하나뿐일 때 쓰던 고정 경로. 이제 계정별로
# 분리됐지만(accounts.cache_file_for), 이 상수는 blog_id 인자 없이 부르는
# 기존 호출부(load_cache()/save_cache())의 기본 대상으로 계속 쓴다.
CACHE_FILE = Path(cache_file_for())  # 기본 계정(skyjwsin)
RESEARCH_FILE = data_dir() / "blog_topic_research_latest.json"
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


def load_cache(blog_id: str | None = None) -> dict:
    """blog_id 생략 시 기본 계정(skyjwsin) 캐시. 계정별로 파일이 분리돼 있어
    한 계정의 발행 이력이 다른 계정의 중복 검사에 섞이지 않는다."""
    path = Path(cache_file_for(blog_id)) if blog_id else CACHE_FILE
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 이미 게시된 주제 캐시 파일이 없거나 형식이 안 맞으면 무시하고 빈 기본값 사용
            pass
    return {"topics": [], "posted": []}


def save_cache(cache: dict, blog_id: str | None = None) -> None:
    path = Path(cache_file_for(blog_id)) if blog_id else CACHE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def topic_key(title: str) -> str:
    # 중복 판별용 키일 뿐 보안 용도 아님(bandit B324, 2026-09-29 확인).
    return hashlib.md5(title.strip().lower().encode(), usedforsecurity=False).hexdigest()[:12]


def is_duplicate(title: str, cache: dict) -> bool:
    key = topic_key(title)
    used_keys = {p.get("key") for p in cache.get("posted", [])}
    used_titles = {p.get("title", "").strip().lower() for p in cache.get("posted", [])}
    return key in used_keys or title.strip().lower() in used_titles


# ── 리서치 결과 로드 ─────────────────────────────────────────────────────────


# 이 블로그의 목적은 우리 제품 영업이다(2026-08-20 확인).
# 제품은 적산 하나가 아니라 두 축이다:
#   ① AI 적산·물량산출 (09/03번 저장소) — 품셈·일위대가·도면 물량산출
#   ② 통합 공무 플랫폼 (32번 저장소) — 내역서·기성·계약·자재·안전·공정·위험성평가·세무
# 처음엔 적산 키워드만 남겼다가 공무 플랫폼이 커버하는 업무를 통째로 빠뜨렸다.
# 아래 목록은 실제 모듈(contract/estimate/material/naeyeok/progress/risk/
# safety/safety_cost/schedule/tax)과 AI ERP 도구(작업일보·검측·자재발주·
# 안전보건교육일지·근로계약서·신규자등록)에 대응한다.
PRODUCT_KEYWORDS = (
    # ① 적산·물량산출
    "일위대가",
    "적산",
    "물량",
    "산출",
    "품셈",
    "단가",
    "견적",
    "도면",
    "수량",
    "원가계산",
    "제비율",
    "간접공사비",
    "재료비",
    "경비",
    "노무비",
    # ② 공무 플랫폼 — 내역/계약/기성
    "내역서",
    "계약",
    "기성",
    "설계변경",
    "정산",
    "준공",
    "공정",
    # 자재
    "자재",
    "발주",
    "검수",
    "검측",
    "반입",
    # 안전·위험성평가
    "안전관리비",
    "위험성평가",
    "안전보건",
    "산업안전",
    "교육일지",
    # 노무·서류
    "작업일보",
    "근로계약",
    "실명부",
    "출역",
    "노무",
    # 세무
    "세금계산서",
    "부가세",
    "원천세",
)

# 제품 키워드가 스쳐 지나갈 뿐 실제로는 무관한 주제를 걸러낸다.
# 예: "노무비 미수금 받을 수 있을까요" — 대금 체불 문제이지 우리 제품과 무관.
EXCLUDE_KEYWORDS = (
    "미수금",
    "체불",
    "못 받",
    "떼이",
    "소송",
    "고소",
    "실업급여",
    "자격증",
    "면허 취득",
    "취직",
    "구인",
    "구직",
    "연봉",
    "인센티브",
    # 행정신고성 주제 — 제품과 무관(2026-08-23 발견: "키스콘 신고" 글이
    # 이 필터를 통과해 이미 발행됨. "정산"/"계약" 같은 일반 단어에 걸려
    # PRODUCT_KEYWORDS를 통과했었다).
    "하도급지킴이",
    "키스콘",
    "국민연금",
    "건강보험료 사후정산",
    "고용보험",
    "산재보험 신고",
)


def is_product_related(topic: dict) -> bool:
    """우리 제품(적산·물량산출 / 통합 공무 플랫폼)과 연결되는 주제인지.

    검색량이 커도 제품과 무관하면 제외한다. 방문자는 늘지만 고객이 아니라
    전환이 되지 않는다(2026-08-20 판단).
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
    except Exception as e:  # noqa: BLE001 - 블로그 주제 리서치 파일 로드/AI 보충 JSON 파싱 — 파일 로드나 JSON 파싱 실패 시 빈 리스트로 안전 폴백하고 경고/에러 로그 남길 뿐 쓰기 없음
        _log.warning("[topic-seed] 리서치 파일 로드 실패, 폴백 사용: %s", e)
    return []


def classify_account(topic_text: str) -> str | None:
    """주제 텍스트로 어느 계정에 발행할지 자동 판정.

    지금은 skyjwsin(건설) 쪽만 검증된 키워드(PRODUCT_KEYWORDS)가 있다.
    skyjwshin(조명)은 아직 리서치가 없어서(accounts.py 참조) 키워드를
    지어내지 않는다 — 기준서 원칙(수치·근거 없는 것은 만들지 않는다)과
    같은 이유. 매칭이 안 되면 None을 반환해 **사람이 판단**하게 한다.
    자동 오분류로 엉뚱한 계정에 발행되는 것보다 이게 안전하다.
    """
    text = topic_text or ""
    if any(k in text for k in PRODUCT_KEYWORDS) and not any(k in text for k in EXCLUDE_KEYWORDS):
        return "skyjwsin"
    return None


def get_topic_seed() -> list[str]:
    """참고용 주제 제목 목록. 리서치 결과가 있으면 그 제목들, 없으면 고정 폴백."""
    researched = get_researched_topics()
    if researched:
        return [t["question_title"] for t in researched if t.get("question_title")]
    _log.info("[topic-seed] 고정 폴백 목록 사용 (%d개)", len(FALLBACK_TOPIC_SEED))
    return FALLBACK_TOPIC_SEED


# ── 주제 선정 ─────────────────────────────────────────────────────────────


def _fill_with_fallback_seed(result: list[dict], count: int, cache: dict) -> int:
    """리서치 결과가 부족할 때 고정/리서치 폴백 주제로 보충(외부 호출 없음).

    dry-run 뿐 아니라 AI 보충 호출이 실패했을 때 real-run 에서도 쓴다 —
    AI 호출 실패로 주제 선정 자체가 실패하는 것(2026-10 c4 실행 기록)을
    막기 위함. get_topic_seed()는 이미 로드된 로컬 데이터만 사용하므로
    외부 호출 0 제약을 깨지 않는다.

    반환값은 새로 보충한 개수.
    """
    existing = {r["topic"] for r in result}
    added = 0
    for title in get_topic_seed():
        if len(result) >= count:
            break
        if title and title not in existing and not is_duplicate(title, cache):
            result.append(
                {
                    "topic": title,
                    "keywords": ["건설실무", "건설업"],
                    "angle": "고정 폴백 주제(리서치 결과 부족)",
                    "source_description": "",
                }
            )
            existing.add(title)
            added += 1
    return added


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
        matched = len(result)
        if len(result) < count:
            # 리서치 결과가 부족해도 real-run 과 같은 주제-선정 경로를 타야
            # dry-run 이 리허설로서 의미가 있다 — AI 호출 없는 고정 폴백만 보충.
            added = _fill_with_fallback_seed(result, count, cache)
            print(f"  폴백 보충: {added}개")
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
        _log.error("주제 생성 실패, 고정/리서치 폴백으로 보충: %s", r)
        _fill_with_fallback_seed(result, count, cache)
        return result[:count]

    text = r["text"].strip()
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        _log.error("JSON 파싱 실패, 고정/리서치 폴백으로 보충: %s", text[:200])
        _fill_with_fallback_seed(result, count, cache)
        return result[:count]

    try:
        topics = json.loads(text[start:end])
    except Exception as e:  # noqa: BLE001 - 블로그 주제 리서치 파일 로드/AI 보충 JSON 파싱 — 파일 로드나 JSON 파싱 실패 시 빈 리스트로 안전 폴백하고 경고/에러 로그 남길 뿐 쓰기 없음
        _log.error("JSON 파싱 오류, 고정/리서치 폴백으로 보충: %s | %s", e, text[start:end][:200])
        _fill_with_fallback_seed(result, count, cache)
        return result[:count]

    # 중복 필터 (AI 보충분에는 인용 근거가 없음)
    filtered = [t for t in topics if not is_duplicate(t.get("topic", ""), cache)]
    return (result + filtered)[:count]
