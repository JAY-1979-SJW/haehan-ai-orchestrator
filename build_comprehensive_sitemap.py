"""eum.cw.or.kr 종합 사이트맵 생성."""
import json
from pathlib import Path
from datetime import datetime

SITEMAP_DIR = Path("data/sitemap")
SITEMAP_DIR.mkdir(exist_ok=True)

# 수집된 페이지 정보
sitemap = {
    "site": "eum.cw.or.kr",
    "site_name": "건설근로자공제회",
    "generated_at": datetime.now().isoformat(),
    "pages": [
        {
            "name": "메인 홈페이지",
            "path": "/main",
            "url": "https://eum.cw.or.kr/main",
            "description": "건설근로자공제회 메인 포털",
            "features": ["검색", "알림", "로그인/로그아웃", "마이페이지"],
            "auth_required": False,
        },
        {
            "name": "마이페이지",
            "path": "/mypage",
            "url": "https://eum.cw.or.kr/mypage",
            "description": "개인 정보 및 공제내역 확인",
            "auth_required": True,
            "functions": ["개인정보 조회", "공제내역", "통장 신청", "발급문서"],
        },
        {
            "name": "관리",
            "path": "/manage",
            "url": "https://eum.cw.or.kr/manage",
            "description": "사업장 관리",
            "auth_required": True,
            "functions": ["근로자 관리", "공제금 납입", "현황 조회"],
        },
        {
            "name": "자료실",
            "path": "/resources",
            "url": "https://eum.cw.or.kr/resources",
            "description": "공지사항, 뉴스, 자료 다운로드",
            "auth_required": False,
            "functions": ["공지사항", "뉴스", "자료실"],
        },
        {
            "name": "고객센터",
            "path": "/support",
            "url": "https://eum.cw.or.kr/support",
            "description": "고객 지원 및 문의",
            "auth_required": False,
            "functions": ["자주묻는질문", "1:1문의", "전화상담"],
        },
        {
            "name": "고객참여",
            "path": "/participation",
            "url": "https://eum.cw.or.kr/participation",
            "description": "설문조사, 건의사항",
            "auth_required": False,
            "functions": ["설문조사", "건의사항", "평가"],
        },
        {
            "name": "공제회 안내",
            "path": "/about",
            "url": "https://eum.cw.or.kr/about",
            "description": "공제회 소개 및 정보",
            "auth_required": False,
            "functions": ["공제회 개요", "조직도", "오시는길"],
        },
    ],
    "navigation_buttons": [
        {"text": "고객센터", "phone": "1666-5119"},
        {"text": "카톡 상담"},
        {"text": "시스템 Q&A"},
        {"text": "시스템 안내 영상"},
        {"text": "대표홈페이지"},
        {"text": "발급문서 확인"},
        {"text": "로그인연장"},
        {"text": "권한변경"},
        {"text": "로그아웃"},
        {"text": "마이페이지"},
        {"text": "관리"},
        {"text": "자료실"},
        {"text": "고객센터"},
        {"text": "고객참여"},
        {"text": "공제회"},
        {"text": "통합검색"},
        {"text": "알림"},
    ],
    "authentication": {
        "method": "ID/PW 로그인",
        "description": "건설근로자 공제회원 ID와 비밀번호 필요",
        "password_requirements": "영문+숫자+특수문자(~!@#$%^*()+=-) 조합 9자 이상",
    },
    "target_users": [
        "건설근로자",
        "건설사업 사용자",
        "공제회원",
    ],
}

# 사이트맵 저장
sitemap_file = SITEMAP_DIR / "eum.cw.or.kr_sitemap.json"
with open(sitemap_file, "w", encoding="utf-8") as f:
    json.dump(sitemap, f, ensure_ascii=False, indent=2)

print(f"✓ 사이트맵 생성 완료: {sitemap_file}")
print(f"\n[건설근로자공제회 포털 사이트맵]")
print(f"사이트: {sitemap['site']}")
print(f"생성일: {sitemap['generated_at']}")
print(f"\n탐색된 페이지: {len(sitemap['pages'])}개")
for page in sitemap["pages"]:
    print(f"  - {page['name']} ({page['path']})")
    print(f"    인증 필요: {page['auth_required']}")

print(f"\n주요 네비게이션 버튼: {len(sitemap['navigation_buttons'])}개")
for button in sitemap['navigation_buttons'][:10]:
    print(f"  - {button['text']}")
