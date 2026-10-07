from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class NoticeSiteProfile:
    key: str
    name: str
    home_url: str
    notice_url: str
    target_url_contains: str
    priority_keywords: tuple[str, ...]
    memo: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["priority_keywords"] = list(self.priority_keywords)
        return data


DAILY_BRIEFING_NOTICE_SITES: tuple[NoticeSiteProfile, ...] = (
    NoticeSiteProfile(
        key="kstartup",
        name="K-Startup 창업지원포털 모집중",
        home_url="https://www.k-startup.go.kr/web",
        notice_url="https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do",
        target_url_contains="k-startup.go.kr",
        priority_keywords=("스마트도시", "실증", "구매", "창업기업", "AI", "R&D", "사업화", "오픈이노베이션"),
        memo="창업지원사업 공고와 첨부 공고문 확인 우선",
    ),
    NoticeSiteProfile(
        key="molit",
        name="국토교통부 공지·공고",
        home_url="https://www.molit.go.kr",
        notice_url="https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
        target_url_contains="molit.go.kr",
        priority_keywords=("스마트건설", "BIM", "건설", "국토교통", "공고", "입찰", "고시", "행정예고"),
        memo="국토교통·건설·스마트건설 정책/공고 확인",
    ),
    NoticeSiteProfile(
        key="kaia",
        name="국토교통과학기술진흥원 KAIA",
        home_url="https://www.kaia.re.kr/main.jsp",
        notice_url="https://www.kaia.re.kr/portal/bbs/list/B0000011.do",
        target_url_contains="kaia.re.kr",
        priority_keywords=("국토교통", "R&D", "스마트건설", "AI", "디지털트윈", "기술개발", "공고"),
        memo="국토교통 R&D와 스마트건설 과제 확인",
    ),
    NoticeSiteProfile(
        key="nfa",
        name="소방청 공지·입찰·입법예고",
        home_url="https://www.nfa.go.kr/nfa/",
        notice_url="https://www.nfa.go.kr/nfa/news/notice/notice/",
        target_url_contains="nfa.go.kr",
        priority_keywords=("소방", "입찰", "공고", "입법예고", "행정예고", "소방시설", "소방산업"),
        memo="소방 법령/정책/입찰/공지사항 확인",
    ),
    NoticeSiteProfile(
        key="pps",
        name="조달청 공지·입찰·혁신제품",
        home_url="https://www.pps.go.kr",
        notice_url="https://www.pps.go.kr/kor/bbs/list.do?key=00642",
        target_url_contains="pps.go.kr",
        priority_keywords=("조달", "혁신제품", "입찰", "공공조달", "품질보증", "나라장터"),
        memo="조달 제도, 혁신제품, 품질보증조달물품 확인",
    ),
    NoticeSiteProfile(
        key="nipa",
        name="정보통신산업진흥원 NIPA",
        home_url="https://www.nipa.kr",
        notice_url="https://www.nipa.kr/home/2-2",
        target_url_contains="nipa.kr",
        priority_keywords=("AI", "SW", "클라우드", "디지털", "스마트", "지원사업", "공고"),
        memo="AI·SW·디지털 지원사업 확인",
    ),
)


def get_daily_briefing_sites() -> list[dict]:
    return [site.to_dict() for site in DAILY_BRIEFING_NOTICE_SITES]


def get_site_profile(key: str) -> NoticeSiteProfile | None:
    normalized = (key or "").strip().lower()
    for site in DAILY_BRIEFING_NOTICE_SITES:
        if site.key == normalized:
            return site
    return None
