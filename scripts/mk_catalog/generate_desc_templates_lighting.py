"""조명 5종 상세설명 샘플 템플릿 일괄 생성.

실행:
    python scripts/mk_catalog/generate_desc_templates_lighting.py
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# .env 로드 (ANTHROPIC_API_KEY, OPENAI_API_KEY)
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001 - .env 로드 실패 무시(선택적 설정 로딩), 템플릿 빌더 렌더링 실패한 개별 상품은 건너뛰고 다음 상품으로 계속 진행
    pass

TMPL_DIR = ROOT / "data" / "smartstore" / "desc_templates"
TMPL_DIR.mkdir(parents=True, exist_ok=True)

# ── 5종 샘플 데이터 ───────────────────────────────────────────────────────────

SAMPLES: list[dict[str, Any]] = [
    {
        "meta": {"name": "무드등_감성표준", "category": "조명", "source": "ai"},
        "sections": ["hero", "trust", "features", "price", "detail", "quality", "spec", "as", "delivery"],
        "data": {
            "name": "루나 무드등 — 10단계 밝기 조절 수면 조명",
            "price": 29800,
            "stock": 100,
            "category": "가구/인테리어>조명>무드등/취침등",
            "hero_tag": "전국 공식 총판",
            "sub": "감성 인테리어의 완성, 취침 전 눈의 피로를 줄여주는 따뜻한 빛",
            "trust_badges": [
                {"cls": "quality", "icon": "✅", "title": "KC 안전인증", "desc": "국내 전기용품 안전인증"},
                {"cls": "as", "icon": "🛡️", "title": "1년 무상 AS", "desc": "불량 시 무상 교환"},
                {"cls": "price", "icon": "🚀", "title": "당일 발송", "desc": "오후 2시 이전 주문"},
                {"cls": "origin", "icon": "🏭", "title": "국내 재고", "desc": "정품 공식 총판"},
            ],
            "features": [
                {"icon": "🌙", "title": "10단계 밝기", "desc": "터치 한 번으로 취향에 맞는 밝기 설정"},
                {"icon": "🔋", "title": "USB 충전", "desc": "보조배터리·콘센트 모두 사용 가능"},
                {"icon": "🌡️", "title": "웜화이트 3000K", "desc": "눈에 편안한 따뜻한 색온도"},
                {"icon": "⏱️", "title": "타이머 기능", "desc": "30·60·90분 자동 소등 설정"},
            ],
            "price_reasons": [
                {"title": "공장 직배송", "desc": "유통 단계를 최소화해 원가 절감"},
                {"title": "대량 구매 계약", "desc": "연간 MOQ 계약으로 단가 최적화"},
            ],
            "price_guarantee": "타사 동일 사양 대비 최저가 보장",
            "detail_paragraphs": [
                "수면 전 강한 빛은 멜라토닌 분비를 방해합니다. 루나 무드등의 3000K 웜화이트는 자연스러운 수면 유도에 최적화된 색온도로, 독서·명상·취침 전 릴렉스 타임을 더욱 편안하게 만들어 줍니다.",
                "10단계 밝기 조절로 낮에는 집중 독서등으로, 밤에는 은은한 수면등으로 활용하세요. USB-C 충전 방식으로 콘센트 위치에 구애받지 않고 침대 협탁, 책상, 거실 어디서나 자유롭게 사용할 수 있습니다.",
            ],
            "quality_items": [
                {"label": "LED 칩 등급", "value": "CRI 90 이상 — 자연광에 가까운 연색성"},
                {"label": "소음", "value": "무소음 설계 — 취침 시 소음 제로"},
                {"label": "발열 관리", "value": "과열 방지 회로 — 연속 12시간 안전"},
                {"label": "소재", "value": "ABS + 실리콘 복합 소재, 낙하 충격 완화"},
            ],
            "specs": {
                "색온도": "3000K (웜화이트)",
                "밝기 단계": "10단계",
                "충전": "USB-C 5V/1A",
                "배터리": "2000mAh 내장",
                "사용 시간": "최대 12시간 (최저 밝기 기준)",
                "크기": "φ80 × H120mm",
                "무게": "185g",
                "인증": "KC 전기용품 안전인증",
            },
            "as_warranty": "구매일로부터 1년",
            "as_contact": "스마트스토어 문의 채널 (평일 09:00–18:00)",
            "delivery_items": [
                {"emoji": "📦", "label": "배송비", "desc": "5만 원 이상 무료 (미만 3,000원)"},
                {"emoji": "🚀", "label": "출고 기준", "desc": "평일 오후 2시 이전 결제 → 당일 출고"},
                {"emoji": "⏱️", "label": "배송 기간", "desc": "출고 후 1–3 영업일 수령"},
                {"emoji": "🔄", "label": "단순 변심", "desc": "수령 후 7일 이내 (왕복 배송비 구매자 부담)"},
                {"emoji": "✅", "label": "제품 불량", "desc": "수령 후 30일 이내 무료 교환/환불"},
            ],
        },
    },
    {
        "meta": {"name": "취침등_수면건강", "category": "조명", "source": "ai"},
        "sections": ["hero", "trust", "features", "detail", "quality", "notice", "as", "delivery"],
        "data": {
            "name": "슬립라이트 아기 취침등 — 블루라이트 차단 수면 전용",
            "price": 19900,
            "stock": 200,
            "category": "가구/인테리어>조명>무드등/취침등",
            "hero_tag": "수면 전문 브랜드",
            "sub": "아이와 어른 모두를 위한 숙면 파트너, 블루라이트 99% 차단",
            "trust_badges": [
                {"cls": "quality", "icon": "💙", "title": "블루라이트 차단", "desc": "99% 필터링 인증"},
                {"cls": "quality", "icon": "👶", "title": "영유아 KC 인증", "desc": "유해물질 無 검증"},
                {"cls": "as", "icon": "🛡️", "title": "피부 안전 소재", "desc": "BPA-Free 인증"},
                {"cls": "as", "icon": "✅", "title": "1년 무상 AS", "desc": "불량 무상 교환"},
            ],
            "features": [
                {"icon": "👶", "title": "영유아 안전", "desc": "유해물질 無 — 아이 방 24시간 사용 안심"},
                {"icon": "💙", "title": "블루라이트 차단", "desc": "멜라토닌 방해 파장 99% 필터링"},
                {"icon": "🌈", "title": "7가지 색상", "desc": "취향·기분에 따라 색상 변경 가능"},
                {"icon": "🤫", "title": "무소음 센서", "desc": "소리 감지 자동 점등 — 아이 울음에 즉시 반응"},
            ],
            "detail_paragraphs": [
                "일반 LED 조명의 블루라이트(400–500nm 파장)는 수면 호르몬 멜라토닌 분비를 억제합니다. 슬립라이트는 특수 필터로 이 파장을 99% 차단해, 취침 전 사용해도 수면 리듬을 방해하지 않습니다.",
                "소리 감지 센서가 탑재되어 아이가 울거나 소리를 내면 자동으로 부드럽게 점등됩니다. 부모가 핸드폰을 찾을 필요 없이, 아이 방을 편안하게 밝혀줍니다.",
            ],
            "quality_items": [
                {"label": "소재 안전성", "value": "BPA-Free ABS — 입에 닿아도 안전"},
                {"label": "발열 관리", "value": "표면 온도 38°C 이하 유지"},
                {"label": "눈부심 방지", "value": "확산 커버로 직접 광원 노출 차단"},
                {"label": "내충격", "value": "1m 낙하 테스트 통과"},
            ],
            "notice_items": [
                "직접 광원을 눈에 가까이 대고 응시하지 마세요.",
                "물이나 습기가 많은 곳(욕실 등)에서의 사용을 삼가주세요.",
                "분해·개조 시 KC 인증이 무효화됩니다.",
            ],
            "as_warranty": "구매일로부터 1년 (배터리 6개월)",
            "as_contact": "스마트스토어 문의 채널",
            "delivery_items": [
                {"emoji": "📦", "label": "배송비", "desc": "3만 원 이상 무료"},
                {"emoji": "🚀", "label": "출고 기준", "desc": "출고 후 1–2 영업일 수령"},
                {"emoji": "✅", "label": "불량 교환", "desc": "수령 후 30일 이내 무료"},
            ],
        },
    },
    {
        "meta": {"name": "LED스탠드_스펙중심", "category": "조명", "source": "ai"},
        "sections": ["hero", "trust", "features", "spec", "howto", "as", "delivery"],
        "data": {
            "name": "루멘 프로 LED 스탠드 — 공부방·사무용 눈 보호 조명",
            "price": 49800,
            "stock": 80,
            "category": "가구/인테리어>조명>스탠드조명",
            "hero_tag": "안과 의사 추천",
            "sub": "플리커·블루라이트 동시 차단, 집중력을 높이는 공간 조명",
            "trust_badges": [
                {"cls": "quality", "icon": "👁️", "title": "플리커프리", "desc": "IEEE PAR 1789 기준"},
                {"cls": "quality", "icon": "💙", "title": "블루라이트 차단", "desc": "눈 보호 인증"},
                {"cls": "price", "icon": "🏥", "title": "안과 의사 추천", "desc": "눈 건강 검증"},
                {"cls": "as", "icon": "🛡️", "title": "3년 무상 AS", "desc": "LED 모듈 포함"},
            ],
            "features": [
                {"icon": "📐", "title": "5단계 각도", "desc": "헤드 각도 0–135° 자유 조절"},
                {"icon": "🎨", "title": "색온도 3단계", "desc": "웜/중간/쿨 화이트 — 용도별 최적 빛"},
                {"icon": "🔆", "title": "5단계 밝기", "desc": "600lm 최대 밝기 — A4 용지 전체 균일 조도"},
                {"icon": "⚡", "title": "USB-A 충전포트", "desc": "스탠드 본체에서 스마트폰 동시 충전"},
            ],
            "specs": {
                "최대 밝기": "600 lm",
                "색온도": "3000K / 4000K / 6000K",
                "밝기 단계": "5단계",
                "연색지수(CRI)": "Ra 95 이상",
                "플리커": "플리커프리 (IEEE PAR 1789 기준)",
                "전력 소비": "12W",
                "USB 충전": "USB-A 5V/2A 출력",
                "암 길이": "40cm (관절형)",
                "무게": "820g",
                "인증": "KC, CE, RoHS",
            },
            "howto": [
                {"step": 1, "title": "설치", "desc": "클램프 또는 스탠드 베이스 중 선택해 책상에 고정"},
                {"step": 2, "title": "전원 연결", "desc": "USB-C 어댑터(포함) 또는 PC USB 포트에 연결"},
                {"step": 3, "title": "밝기 설정", "desc": "터치 버튼 짧게 누르면 밝기 단계 변경"},
                {"step": 4, "title": "색온도 변경", "desc": "터치 버튼 길게 누르면 색온도 단계 변경"},
                {"step": 5, "title": "각도 조절", "desc": "암 관절을 원하는 위치로 구부려 고정"},
            ],
            "as_warranty": "3년 (LED 모듈 포함)",
            "as_contact": "스마트스토어 문의 / 전화 상담 가능",
            "delivery_items": [
                {"emoji": "📦", "label": "배송비", "desc": "무료배송"},
                {"emoji": "🚀", "label": "출고 기준", "desc": "출고 후 1–3 영업일 수령"},
                {"emoji": "✅", "label": "불량 교환", "desc": "수령 후 30일 이내 무료"},
                {"emoji": "🔄", "label": "단순 변심", "desc": "수령 후 7일 이내 (왕복 배송비 구매자 부담)"},
            ],
        },
    },
    {
        "meta": {"name": "포인트조명_인테리어", "category": "조명", "source": "ai"},
        "sections": ["hero", "features", "price", "detail", "quality", "origin", "spec", "delivery"],
        "data": {
            "name": "무선 포인트 조명 — 카페 감성 벽조명 인테리어 스팟",
            "price": 35000,
            "stock": 150,
            "category": "가구/인테리어>조명>포인트/간접조명",
            "hero_tag": "인테리어 셀러 픽",
            "sub": "공사 없이 붙이는 무선 스팟 조명, 집이 카페가 되는 순간",
            "features": [
                {"icon": "🔌", "title": "무선·무타공", "desc": "3M 접착 마운트 — 벽 공사 불필요"},
                {"icon": "🎨", "title": "색온도 2종", "desc": "웜화이트 / 내추럴 화이트 선택"},
                {"icon": "🔋", "title": "배터리 내장", "desc": "1회 충전으로 최대 8시간 사용"},
                {"icon": "📱", "title": "앱 연동", "desc": "스마트폰으로 밝기·타이머 원격 제어"},
            ],
            "price_reasons": [
                {"title": "디자이너 직접 기획", "desc": "에이전시 비용 절감"},
                {"title": "MOQ 대량 생산", "desc": "단가 최적화"},
            ],
            "price_guarantee": "동일 디자인·스펙 최저가 도전",
            "detail_paragraphs": [
                "인테리어 공사 없이 원하는 곳 어디든 부착할 수 있는 무선 스팟 조명입니다. 3M 초강력 접착 마운트로 타일·콘크리트·목재 모든 벽면에 적용 가능하며, 필요 시 깔끔하게 제거도 됩니다.",
                "홈 카페, 아트월, 액자 조명, 선반 포인트 등 다양한 용도로 연출해 보세요. 앱 하나로 여러 개를 동시에 제어할 수 있어 분위기 연출이 한층 쉬워집니다.",
            ],
            "quality_items": [
                {"label": "바디 소재", "value": "항공 알루미늄 — 방열·내구성 우수"},
                {"label": "방수 등급", "value": "IP44 — 욕실·야외 처마 아래 사용 가능"},
                {"label": "충전 옵션", "value": "Qi 무선 충전 패드 별도 판매"},
                {"label": "마운트 강도", "value": "3M — 1.5kg 하중 지지 (조명 무게의 5배)"},
            ],
            "origin": "한국 기획 / 중국 생산",
            "distributor": "비전아이(주)",
            "distribution_channel": "제조사 → 국내 공식 총판 → 소비자 직배송",
            "specs": {
                "색온도": "2700K / 4000K",
                "밝기": "300 lm",
                "배터리": "3000mAh",
                "사용 시간": "최대 8시간",
                "방수등급": "IP44",
                "크기": "φ60 × H90mm",
                "무게": "210g",
            },
            "delivery_items": [
                {"emoji": "📦", "label": "배송비", "desc": "4만 원 이상 무료 (미만 3,000원)"},
                {"emoji": "🚀", "label": "출고 기준", "desc": "출고 후 1–2 영업일 수령"},
                {"emoji": "✅", "label": "불량 교환", "desc": "수령 후 30일 이내 무료"},
            ],
        },
    },
    {
        "meta": {"name": "천장등_시공편의", "category": "조명", "source": "ai"},
        "sections": ["hero", "trust", "features", "spec", "howto", "as", "notice", "delivery"],
        "data": {
            "name": "슬림 LED 천장등 50W — 방등 교체용 직부등",
            "price": 38000,
            "stock": 60,
            "category": "가구/인테리어>조명>천장등/방등",
            "hero_tag": "셀프 시공 가능",
            "sub": "10분 셀프 교체, 전기료 50% 절감 — 리모컨 포함 완제품",
            "trust_badges": [
                {"cls": "quality", "icon": "✅", "title": "KC 안전인증", "desc": "전기용품 안전인증"},
                {"cls": "price", "icon": "⚡", "title": "전기료 50% 절감", "desc": "50W로 100W 밝기"},
                {"cls": "origin", "icon": "📡", "title": "리모컨 포함", "desc": "별도 구매 불필요"},
                {"cls": "as", "icon": "🛡️", "title": "5년 무상 AS", "desc": "LED 모듈 포함"},
            ],
            "features": [
                {"icon": "⚡", "title": "50W 고효율", "desc": "형광등 100W 밝기를 50W로 — 전기료 절반"},
                {"icon": "🔧", "title": "10분 셀프 교체", "desc": "기존 천장 배선 그대로 — 전기 지식 불필요"},
                {"icon": "📡", "title": "리모컨 포함", "desc": "밝기 3단계 + 색온도 3단계 원격 조절"},
                {"icon": "🌡️", "title": "색온도 3종", "desc": "주광/중간/전구색 — 공간 분위기 맞춤"},
            ],
            "specs": {
                "소비전력": "50W",
                "광속": "4500 lm",
                "색온도": "3000K / 4000K / 6500K",
                "연색지수": "Ra 85",
                "설치 방식": "직부 (천장 직접 부착)",
                "호환 천장": "일반 원형 천장 소켓 (E26 변환 어댑터 포함)",
                "제품 크기": "φ400 × H65mm",
                "무게": "1.2kg",
                "수명": "약 30,000시간",
                "인증": "KC 안전인증",
            },
            "howto": [
                {"step": 1, "title": "차단기 내리기", "desc": "반드시 해당 방 차단기를 내리세요"},
                {"step": 2, "title": "기존 등 분리", "desc": "기존 천장등 고정 나사 제거 후 전선 분리"},
                {"step": 3, "title": "전선 연결", "desc": "흰색-흰색, 검정-검정 연결 (커넥터 포함)"},
                {"step": 4, "title": "본체 고정", "desc": "천장 나사 2개로 고정 후 커버 장착"},
                {"step": 5, "title": "리모컨 페어링", "desc": "전원 ON 후 리모컨 페어링 버튼 3초 누름"},
            ],
            "notice_items": [
                "반드시 차단기를 내린 후 시공하세요. 감전 위험이 있습니다.",
                "최대 부하 60W 이하 회로에만 설치 가능합니다.",
                "직접 시공이 어려운 경우 전기 기사에게 의뢰하세요.",
                "습기가 많은 욕실·주방 직상부에는 사용하지 마세요.",
            ],
            "as_warranty": "5년 (LED 모듈·드라이버 포함)",
            "as_contact": "스마트스토어 문의 채널 (A/S 기사 방문 연결 가능)",
            "delivery_items": [
                {"emoji": "📦", "label": "배송비", "desc": "무료배송"},
                {"emoji": "🚀", "label": "출고 기준", "desc": "출고 후 1–3 영업일 수령"},
                {"emoji": "✅", "label": "설치 불량", "desc": "수령 후 30일 이내 무료 교환"},
                {"emoji": "🔄", "label": "단순 변심", "desc": "수령 후 7일 이내 (왕복 배송비 구매자 부담)"},
            ],
        },
    },
]


def generate_all() -> None:
    """2026-09-24: gpt_description_writer(GPT) 삭제됨 — 섹션 빌더만 사용.

    맞춤 문구가 필요하면 Claude Code가 이 스크립트의 SAMPLES 데이터를 직접 읽고
    작성한 뒤 save_template(MCP)로 저장한다.
    """
    from scripts.naver.smartstore.product.page_builder import ProductPageBuilder

    total = len(SAMPLES)

    for i, sample in enumerate(SAMPLES, 1):
        meta = sample["meta"]
        sections = sample["sections"]
        data = sample["data"]
        print(f"\n[{i}/{total}] {meta['name']} 생성 중...", flush=True)

        html = None
        source = "builder"

        try:
            builder = ProductPageBuilder()
            builder.select(sections)
            html = builder.render(data)
            print(f"  → 빌더 생성 완료 ({len(html):,}자)")
        except Exception as e:  # noqa: BLE001 - .env 로드 실패 무시(선택적 설정 로딩), 템플릿 빌더 렌더링 실패한 개별 상품은 건너뛰고 다음 상품으로 계속 진행
            print(f"  ✗ 빌더 실패: {e}")
            continue

        meta["source"] = source
        safe = re.sub(r"[^\w가-힣]", "_", meta["name"])[:40]
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        tid = f"{safe}_{ts}"

        payload = {
            "id": tid,
            "name": meta["name"],
            "category": meta["category"],
            "sections": sections,
            "data": data,
            "html": html,
            "source": meta["source"],
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "created_by": "generate_script",
        }
        out = TMPL_DIR / f"{tid}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✓ 저장 완료 → {out.name}  (HTML {len(html):,}자)")

    print(f"\n완료: {TMPL_DIR}")


if __name__ == "__main__":
    generate_all()
