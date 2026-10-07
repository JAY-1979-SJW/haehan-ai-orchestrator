from __future__ import annotations

import re
from datetime import date, datetime

from .models import NoticeAnalysis, NoticeDocument

DATE_RE = re.compile(r"(20\d{2})[.\-/년 ]\s*(\d{1,2})[.\-/월 ]\s*(\d{1,2})")

BUSINESS_KEYWORDS = {
    "CAD/도면 자동화": ["cad", "도면", "bim", "물량", "수량", "견적", "내역", "설계", "시공"],
    "소방·안전": ["소방", "화재", "안전", "검측", "시설물", "재난", "방재"],
    "AI·SW": ["ai", "인공지능", "소프트웨어", "데이터", "자동화", "클라우드", "ax", "디지털"],
    "스마트도시·공공실증": ["스마트도시", "실증", "구매", "공공", "지자체", "공공기관", "수요처"],
    "건설·국토교통": ["건설", "국토", "교통", "현장", "시공", "유지관리", "공사"],
}

DOCUMENT_KEYWORDS = [
    "사업계획서",
    "신청서",
    "참가신청서",
    "개인정보",
    "사업자등록증",
    "법인등기부등본",
    "국세",
    "지방세",
    "4대보험",
    "발표자료",
    "IR",
    "확약서",
    "동의서",
    "견적서",
]

RISK_PATTERNS = {
    "법인 필수 가능성 확인 필요": ["법인", "법인사업자"],
    "개인사업자 가능 여부 확인 필요": ["개인사업자", "예비창업자"],
    "기술자료 제출 범위 확인 필요": ["기술자료", "소스코드", "알고리즘", "지식재산", "성과물", "귀속"],
    "자부담·민간부담금 확인 필요": ["자부담", "민간부담", "부담금", "현금", "현물"],
    "실증기관·수요처 매칭 조건 확인 필요": ["실증기관", "수요처", "구매기관", "수요기업", "컨소시엄"],
}


def analyze_document(document: NoticeDocument, today: date | None = None) -> NoticeAnalysis:
    today = today or date.today()
    text = document.combined_text.lower()
    raw_text = document.combined_text

    deadline = document.candidate.deadline or _find_deadline(raw_text)
    posted_at = document.candidate.posted_at or _find_first_date(raw_text)

    business_fit = _business_fit(text)
    required_docs = _extract_required_documents(raw_text)
    risks = _extract_risks(text)
    eligibility = _eligibility_flags(text)
    urgency = _urgency(deadline, today)
    score = _score(text, business_fit, required_docs, risks, urgency)

    actions = _immediate_actions(deadline, eligibility, risks, score)
    summary = _summary(document, business_fit, deadline, score)

    return NoticeAnalysis(
        title=document.candidate.title,
        source=document.candidate.source,
        url=document.candidate.url,
        posted_at=posted_at,
        deadline=deadline,
        fit_score=score,
        urgency=urgency,
        action_required=score >= 70 or urgency in {"긴급", "임박"},
        summary=summary,
        business_fit=business_fit,
        required_documents=required_docs,
        eligibility_flags=eligibility,
        risks=risks,
        immediate_actions=actions,
        attachments=[item.to_dict() for item in document.attachments],
    )


def _business_fit(text: str) -> list[str]:
    hits: list[str] = []
    for label, keywords in BUSINESS_KEYWORDS.items():
        if any(keyword.lower() in text for keyword in keywords):
            hits.append(label)
    return hits


def _extract_required_documents(text: str) -> list[str]:
    found: list[str] = []
    for keyword in DOCUMENT_KEYWORDS:
        if keyword.lower() in text.lower() and keyword not in found:
            found.append(keyword)
    return found


def _extract_risks(text: str) -> list[str]:
    risks: list[str] = []
    for label, keywords in RISK_PATTERNS.items():
        if any(keyword.lower() in text for keyword in keywords):
            risks.append(label)
    if "hwp" in text or ".hwp" in text:
        risks.append("HWP 원본 서식 작성 필요 가능성")
    return risks


def _eligibility_flags(text: str) -> dict[str, str]:
    flags: dict[str, str] = {}
    flags["개인사업자"] = "가능 문구 확인" if "개인사업자" in text else "미확인"
    flags["법인 필수"] = "법인 관련 문구 있음 - 필수 여부 확인" if "법인" in text else "미확인"
    flags["창업연수"] = "창업연수 제한 가능성 있음" if "7년" in text or "3년" in text or "창업" in text else "미확인"
    flags["기술공개 위험"] = "기술자료/성과물/귀속 문구 확인 필요" if any(k in text for k in ["기술자료", "소스코드", "알고리즘", "귀속", "성과물"]) else "낮음 또는 미확인"
    return flags


def _find_first_date(text: str) -> str | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    y, m, d = match.groups()
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def _find_deadline(text: str) -> str | None:
    deadline_markers = ["마감", "신청기간", "접수기간", "신청기한", "접수마감", "까지"]
    candidates: list[tuple[int, str]] = []
    for match in DATE_RE.finditer(text):
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 80)
        window = text[start:end]
        score = sum(1 for marker in deadline_markers if marker in window)
        y, m, d = match.groups()
        candidates.append((score, f"{int(y):04d}-{int(m):02d}-{int(d):02d}"))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][1]


def _urgency(deadline: str | None, today: date) -> str:
    if not deadline:
        return "마감 미확인"
    try:
        d_day = (datetime.strptime(deadline, "%Y-%m-%d").date() - today).days
    except ValueError:
        return "마감 미확인"
    if d_day < 0:
        return "마감 지남"
    if d_day <= 3:
        return "긴급"
    if d_day <= 7:
        return "임박"
    if d_day <= 21:
        return "검토 필요"
    return "여유"


def _score(text: str, business_fit: list[str], required_docs: list[str], risks: list[str], urgency: str) -> int:
    score = 20 + len(business_fit) * 12
    if required_docs:
        score += 8
    if "실증" in text and "구매" in text:
        score += 12
    if "스마트도시" in text:
        score += 10
    if urgency in {"긴급", "임박", "검토 필요"}:
        score += 8
    if any("기술자료" in risk or "소스코드" in risk for risk in risks):
        score -= 8
    return max(0, min(100, score))


def _summary(document: NoticeDocument, business_fit: list[str], deadline: str | None, score: int) -> str:
    fit = ", ".join(business_fit) if business_fit else "직접 적합 항목 미확인"
    return (
        f"첨부파일 {len(document.attachments)}개를 분석했습니다. "
        f"대표님 사업 관점 적합 항목은 {fit}이며, "
        f"마감은 {deadline or '미확인'}입니다. "
        f"현재 적합도는 {score}/100입니다."
    )


def _immediate_actions(deadline: str | None, eligibility: dict[str, str], risks: list[str], score: int) -> list[str]:
    actions = ["공고 원문과 첨부 공고문에서 신청자격 원문 확인"]
    if eligibility.get("개인사업자") != "가능 문구 확인":
        actions.append("개인사업자 신청 가능 여부를 공고문/문의처로 확인")
    if any("법인" in risk for risk in risks) or "법인" in eligibility.get("법인 필수", ""):
        actions.append("법인 필수 여부와 협약 전 법인전환 가능 여부 확인")
    if any("기술자료" in risk for risk in risks):
        actions.append("사업계획서에는 핵심 알고리즘·소스코드 대신 결과물/효과 중심으로 작성")
    if deadline:
        actions.append(f"마감일 {deadline} 기준 제출서류 역산 일정 작성")
    if score >= 70:
        actions.append("CAD 자동물량 산출을 스마트도시 시설물·소방·건설 데이터 자동화 1장 소개서로 정리")
    return actions
