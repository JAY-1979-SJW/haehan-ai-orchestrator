"""ProductPageBuilder 실행 — 샘플 상품으로 미리보기 생성."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.naver.smartstore.product.page_builder import ProductPageBuilder

# ── 상품 데이터 ──────────────────────────────────────────────────────────────
product = {
    # Hero
    "hero_tag":  "2024 베스트셀러 · 전국 공식 총판",
    "name":      "손끝 하나로 완성되는\n감성 조명 공간",
    "sub":       "터치 한 번으로 16가지 색감 — 오늘 밤, 당신의 방을 바꿔드립니다",
    "price":     29800,
    "price_badge": "최저가 보장",

    # Trust badges
    "trust_badges": [
        {"cls": "price",   "icon": "💰", "title": "최저가 보장",  "desc": "차액 200% 환불\n가격 조사 후 설정"},
        {"cls": "as",      "icon": "🛡️", "title": "1년 무상 AS",  "desc": "불량 시 무상 교환\n24시간 내 답변"},
        {"cls": "quality", "icon": "✅", "title": "KC 안전인증",   "desc": "국내 전기용품\n안전인증 완료"},
        {"cls": "origin",  "icon": "🏭", "title": "공식 총판",    "desc": "정식 수입 통관\n공식 유통 경로"},
    ],

    # Features
    "features": [
        {"icon": "✋", "title": "직관적 터치 제어", "desc": "버튼 없이 터치 한 번으로\n전원·밝기·색상 즉시 조절"},
        {"icon": "🎨", "title": "16가지 감성 색상", "desc": "웜화이트부터 딥블루까지\n무드에 맞게 선택"},
        {"icon": "🔋", "title": "최대 8시간 사용",  "desc": "USB-C 완충 후 8시간\n코드 없이 자유 배치"},
    ],

    # Price
    "price_reasons": [
        {"title": "제조사 직계약",     "desc": "중간 유통 마진 완전 제거, 공장 출고가 직적용"},
        {"title": "전국 공식 총판",    "desc": "연간 대량 발주로 최저 단가 확보"},
        {"title": "스마트스토어 직판", "desc": "오프라인 매장비·인건비 없는 온라인 직판"},
        {"title": "실시간 가격 조사",  "desc": "네이버쇼핑·쿠팡·11번가 동일 모델 비교 후 최저가 설정"},
    ],
    "price_guarantee": "동일 제품 타 판매처보다 비싸면 차액의 200% 환불",

    # Detail
    "detail_paragraphs": [
        "LED 터치 무드등은 침실, 거실, 서재 어디서나 손끝 하나로 분위기를 바꾸는 스마트 조명입니다. "
        "16가지 색상과 3단계 밝기 조절로 독서등부터 수면등, 파티 무드까지 하나의 무드등으로 해결할 수 있습니다.",
        "USB-C 충전 방식으로 스마트폰 충전기 그대로 사용 가능하며, 완충 시 최대 8시간 연속 사용이 가능합니다. "
        "전선 없이 책상 위, 선반, 침대 협탁 어디든 자유롭게 배치할 수 있어 LED 조명 인테리어 활용도가 높습니다.",
        "터치 감도는 0.1초 반응으로 지연 없이 작동합니다. 전원 OFF 전 마지막 설정값을 자동 저장하여 "
        "다음 사용 시 침실 조명 재설정이 필요 없습니다.",
    ],

    # Quality
    "quality_items": [
        {"label": "소재",      "value": "고강도 ABS + 실리콘 갓"},
        {"label": "LED 수명",  "value": "50,000시간 이상"},
        {"label": "낙하 테스트","value": "1m 3회 이상 무파손"},
        {"label": "터치 내구성","value": "10만 회 반복 테스트"},
        {"label": "발열",      "value": "장시간 사용 시 미온"},
        {"label": "방수 등급", "value": "IPX4 (생활방수)"},
    ],

    # Origin
    "origin":               "중국 광저우 (조명 전문 OEM 공장 · 10년 이상 생산 이력)",
    "distributor":          "국내 전국 공식 총판 (정식 관세 납부 · 통관 완료)",
    "distribution_channel": "제조사 → 공식 수입사 → 당사 직판 (3단계 최단 경로)",
    "certifications":       ["KC-R-2024-XXXXX", "RoHS"],
    "origin_reason":        "동급 품질 기준 한국·독일산 대비 40~60% 저렴한 생산단가 — 그 차이를 소비자 가격에 반영",

    # Spec
    "specs": {
        "모델명":    "LT-TOUCH-16C",
        "크기":      "Φ 8cm × 높이 12cm",
        "무게":      "약 180g",
        "색상 수":   "16가지 (RGB 풀컬러)",
        "밝기 조절": "3단계 (30% / 60% / 100%)",
        "배터리":    "리튬이온 2,000mAh",
        "충전 방식": "USB-C (5V / 1A, 케이블 포함)",
        "충전 시간": "약 2.5시간",
        "연속 사용": "최대 8시간 (30% 밝기 기준)",
        "소재":      "고강도 ABS + 실리콘",
        "방수 등급": "IPX4 (생활방수)",
        "인증":      "KC · RoHS",
        "원산지":    "중국 (China)",
    },

    # HowTo
    "howto": [
        {"title": "충전",    "desc": "USB-C 케이블로 완충 후 사용 (충전 중 동시 사용 가능)"},
        {"title": "전원",    "desc": "상단 터치 패널을 1초 길게 누르면 전원 ON / OFF"},
        {"title": "색상",    "desc": "짧게 터치 → 16가지 색상 순서 변경"},
        {"title": "밝기",    "desc": "2번 연속 터치 → 밝기 단계 변경 (30% → 60% → 100%)"},
        {"title": "설정 저장","desc": "원하는 색상·밝기 설정 후 1초 길게 누르면 저장"},
    ],

    # AS
    "as_warranty":  "구매일로부터 1년 (배터리 소모 제외)",
    "as_exchange":  "불량·파손 수령 후 7일 이내 → 판매자 부담 교환",
    "as_contact":   "스마트스토어 문의 → 영업일 24시간 내 답변",
    "as_scope":     "정상 사용 중 발생한 제품 결함 (충격·침수·개조 제외)",

    # Notice
    "notice_items": [
        "직사광선·고온다습한 환경에서 장시간 방치하지 마세요 (변색·성능 저하 원인)",
        "충전 중 이불·쿠션 위에 올려두지 마세요 (발열로 인한 화재 위험)",
        "어린이가 혼자 충전하지 않도록 주의해 주세요",
        "배터리 방전 상태로 장기 보관 시 수명 단축 (3개월마다 50% 충전 권장)",
        "제품 임의 분해·개조 시 보증 미적용",
        "IPX4는 생활방수 수준 — 수중 사용 절대 금지",
    ],

    # Delivery
    "delivery_items": [
        {"emoji": "📦", "label": "배송비",    "desc": "무료 (CJ대한통운 · 롯데택배)"},
        {"emoji": "🚀", "label": "출고 기준", "desc": "평일 오후 2시 이전 결제 → 당일 출고"},
        {"emoji": "⏱️", "label": "배송 기간", "desc": "출고 후 1~3 영업일 수령 (주말·공휴일 제외)"},
        {"emoji": "🏝️", "label": "도서산간",  "desc": "제주·도서산간 추가 배송비 3,000원"},
        {"emoji": "🔄", "label": "교환·반품", "desc": "수령 후 7일 이내 (단순 변심 왕복 배송비 구매자 부담)"},
        {"emoji": "✅", "label": "불량·오배송","desc": "판매자 전액 부담 교환·반품 처리"},
    ],
}

# ── 빌더 실행 ────────────────────────────────────────────────────────────────
builder = ProductPageBuilder()

# 사용자가 원하는 섹션만 선택 (이것만 바꾸면 됨)
builder.select([
    "hero",
    "trust",
    "features",
    "price",
    "detail",
    "quality",
    "origin",
    "spec",
    "howto",
    "as",
    "notice",
    "delivery",
])

print("선택된 섹션:", builder.sections)
html = builder.render(product)
path = builder.save(html)
print(f"저장 완료: {path}")
print(f"HTML 크기: {len(html):,}자")
