"""반딧불 전파사 인스타그램 캡션 생성 — 실제 확인된 사업자 정보만 사용한다.

값을 지어내지 않는다: 대표 경력·자격·연락처·주소는 2026-08-19 세션에서
사용자가 직접 확인해준 값(회사소개서.pdf, 사용자 채팅 입력)만 쓴다.
바뀌면 이 파일의 BIZ 딕셔너리만 고치면 전체 캡션에 반영된다.
"""

from __future__ import annotations

from scripts.instagram.cases import Case

BIZ = {
    "brand": "반딧불 전파사",
    "owner": "신재우 대표",
    "phone": "010-7387-6635",
    "credentials": "전기공사산업기사·소방전기기사 자격 보유, 20년 넘게 전기·통신·소방 현장(경찰청·서울교통공사·각 교육청 등 관급공사 다수)을 직접 뛴 경력",
    "address": "경기도 남양주시 다산동 6143외1필지 다산현대프리미어캠퍼스 2층 에이씨02-043호",
}

_CATEGORY_HASHTAGS = {
    "마그네틱_레일": ["마그네틱조명", "레일조명"],
    "라인_간접_T5": ["라인조명", "간접조명"],
    "매입_스포트": ["매입등", "스포트조명"],
    "펜던트": ["펜던트조명", "식탁등"],
    "홈조명": ["홈조명", "인테리어조명"],
    "시공사례": ["조명시공사례"],
}

_BASE_HASHTAGS = ["인테리어조명", "조명시공", "거실조명", "천장조명", "남양주조명", "다산동", "반딧불전파사"]


def build_caption(case: Case) -> str:
    cat_tags = _CATEGORY_HASHTAGS.get(case.category, [])
    tags = list(dict.fromkeys(cat_tags + _BASE_HASHTAGS))[:15]
    hashtag_line = " ".join(f"#{t}" for t in tags)

    title = case.desc.strip()

    return f"""{title} ✨

안녕하세요, {BIZ["brand"]}입니다.
{BIZ["credentials"]}을 가진 {BIZ["owner"]}가 운영합니다.
현장 경험을 바탕으로 거실·주방 등 신축·리모델링 공간에 어울리는 조명 시공 사례를 소개합니다.

▪ 이런 공간에 잘 어울려요
거실 메인 천장, TV 월 상부 간접조명, 복도·계단 라인 조명
깔끔하게 매립되어 은은한 무드등처럼 활용 가능합니다.

▪ 문의
{BIZ["owner"]} {BIZ["phone"]}

▪ 오시는 곳
{BIZ["address"]}

{hashtag_line}"""
