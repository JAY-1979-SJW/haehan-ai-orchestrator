"""스마트스토어 상품 상세설명 AI 자동 작성 모듈 (L3 Connector).

⚠ [LLM 경계] 2026-09-24 앱 런타임 유료 AI 호출 제거(사용자 승인). 이 모듈은 더 이상 AI API 를 부르지 않는다.
register_form.py 의 `write_claude()`(form_runner `description_mode == "claude"`)로 들어오면
`generate()`가 app_ai_disabled + 표준 프롬프트를 돌려준다 → 문구는 Claude Code(MCP)가 작성하고
`finalize()` / mcp_server 의 render_description·save_template 로 마감한다.
입력 표준·섹션 구조·CSS 디자인 시스템(아래)은 그대로 유지 — Claude Code 작성 시 기준.

────────────────────────────────────────────────────────────────────
표준 구현방식 v2 — 신뢰 4대 기둥 기반
────────────────────────────────────────────────────────────────────

■ 콘텐츠 4대 기둥 (Content Pillar)
  P1. 신뢰   — AS 보증, 내구성, 품질 인증, 교환·반품 정책
  P2. 가격   — 동일제품 최저가 근거, 가격 조사 출처, 차액 환불 정책
  P3. 정보   — 정확한 스펙, 원산지, 공식 인증, 성분/소재
  P4. 유통   — 생산지, 총판/공식 수입사, 유통 경로 투명성

■ HTML 섹션 구조 (S1~S12, 고정 순서)
  S1.  Hero          — 대표이미지 + 헤드라인 + 서브카피
  S2.  Trust Badges  — 신뢰 4개 뱃지 (최저가·AS·품질·공식유통)
  S3.  Features      — 핵심 특징 3가지 (아이콘 카드)
  S4.  Price         — 가격경쟁력 (조사 근거 + 최저가 보장)
  S5.  Detail        — 상세 설명 본문 (2~4 문단)
  S6.  Quality       — 품질·내구성·소재 상세
  S7.  Origin        — 원산지 + 유통 경로 (총판/공식수입사)
  S8.  Spec          — 스펙 테이블 (정확한 수치)
  S9.  HowTo         — 사용 방법 (선택)
  S10. AS            — AS·보증 안내
  S11. Notice        — 주의 사항
  S12. Delivery      — 배송·교환·반품

■ 입력 데이터 표준 v2
  필수:     name, category, price, stock
  권장:     features, keywords, target, brand
  신뢰 정보: as_warranty, as_contact, durability, quality_cert
  가격 정보: price_guarantee, price_research, lowest_price_reason
  원산지:    origin, distributor, distribution_channel
  인증:     certifications (list)

■ 디자인 시스템 (CSS)
  - 최대 폭: 800px
  - Primary: #03C75A (네이버 그린)
  - Trust:   #1a5c96 (신뢰 파랑)
  - 섹션 간격: 48px

────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.logger import get_logger

_log = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[4]


# ══════════════════════════════════════════════════════════════════════════════
# 1. 입력 데이터 표준 v2
# ══════════════════════════════════════════════════════════════════════════════

REQUIRED_FIELDS = ["name", "category", "price", "stock"]
RECOMMENDED_FIELDS = ["features", "keywords", "target", "brand"]

TRUST_FIELDS = {
    # AS·품질
    "as_warranty": "보증 기간 (예: 구매일로부터 1년)",
    "as_contact": "AS 연락처 또는 방법",
    "durability": "내구성 설명 (소재, 테스트 기준 등)",
    "quality_cert": "품질 인증 (KC, CE, ISO 등)",
    "certifications": "인증 목록 (list)",
    # 가격
    "price_guarantee": "최저가 보장 정책",
    "price_research": "가격 조사 출처/방법 (어떻게 최저가를 확인했는지)",
    "lowest_price_reason": "왜 저렴한가 (직수입/대량구매/총판계약 등)",
    # 원산지·유통
    "origin": "원산지 (예: 중국, 한국, 독일)",
    "distributor": "유통 경로 (예: 전국 공식 총판, 정식 수입사)",
    "distribution_channel": "공급 경로 설명 (공장→총판→당사 등)",
}

OPTIONAL_FIELDS = ["specs", "notice", "howto", "delivery", "original_price", "self_made", "style"]

DEFAULT_DELIVERY = (
    "평일 오후 2시 이전 주문 → 당일 출고 (주말·공휴일 제외) · "
    "제주·도서산간 지역 추가 배송비 발생 · "
    "교환/반품: 수령 후 7일 이내 (단순 변심 왕복 배송비 구매자 부담) · "
    "불량/오배송: 판매자 전액 부담"
)


def validate_product_data(data: dict) -> list[str]:
    """입력 데이터 유효성 검사. errors와 warnings 모두 반환."""
    errors = []
    for f in REQUIRED_FIELDS:
        if not data.get(f):
            errors.append(f"[필수] {f} 누락")
    if data.get("name") and len(str(data["name"])) > 100:
        errors.append("[오류] name 100자 초과")
    if data.get("price") and int(data["price"]) < 10:
        errors.append("[오류] price 최소 10원")
    # 권장 필드 경고
    missing_rec = [f for f in RECOMMENDED_FIELDS if not data.get(f)]
    if missing_rec:
        errors.append(f"[권장] 누락 시 품질 저하: {missing_rec}")
    # 신뢰 필드 경고
    trust_missing = [k for k in ["as_warranty", "origin", "price_guarantee", "distributor"] if not data.get(k)]
    if trust_missing:
        errors.append(f"[권장] 신뢰 정보 누락 (상세페이지 설득력 저하): {trust_missing}")
    return errors


def build_trust_summary(data: dict) -> dict:
    """신뢰 4대 기둥 요약 dict 생성."""
    return {
        "price": {
            "guarantee": data.get("price_guarantee", "동일 상품 최저가 보장"),
            "research": data.get("price_research", ""),
            "reason": data.get("lowest_price_reason", ""),
        },
        "quality": {
            "warranty": data.get("as_warranty", ""),
            "contact": data.get("as_contact", ""),
            "durability": data.get("durability", ""),
            "cert": data.get("quality_cert", ""),
            "certs": data.get("certifications", []),
        },
        "origin": {
            "country": data.get("origin", ""),
            "distributor": data.get("distributor", ""),
            "channel": data.get("distribution_channel", ""),
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. 디자인 시스템 (CSS)
# ══════════════════════════════════════════════════════════════════════════════

CSS_DESIGN_SYSTEM = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');

/* ─ 루트 ─ */
.pd { font-family: 'Noto Sans KR', -apple-system, sans-serif;
      color: #1a1a1a; max-width: 800px; margin: 0 auto;
      font-size: 15px; line-height: 1.7; word-break: keep-all; }

/* ─ S1. Hero ─ */
.pd-hero { text-align: center; padding: 48px 20px 32px; }
.pd-hero-img { width: 100%; border-radius: 12px; margin-bottom: 28px; }
.pd-headline { font-size: 26px; font-weight: 700; color: #111;
               line-height: 1.4; margin-bottom: 12px; }
.pd-sub { font-size: 15px; color: #555; }

/* ─ S2. Trust Badges ─ */
.pd-trust { display: flex; gap: 12px; flex-wrap: wrap;
            padding: 0 16px 40px; }
.pd-trust-badge { flex: 1; min-width: 160px;
                  background: #f0f6ff; border: 1.5px solid #c0d8f0;
                  border-radius: 10px; padding: 16px;
                  text-align: center; }
.pd-trust-badge.price  { background: #fff8e8; border-color: #f0d080; }
.pd-trust-badge.quality{ background: #f0fff4; border-color: #80d0a0; }
.pd-trust-badge.origin { background: #f8f0ff; border-color: #c0a0e0; }
.pd-trust-badge.as     { background: #f0f6ff; border-color: #80b0e0; }
.pd-trust-icon { font-size: 24px; margin-bottom: 6px; }
.pd-trust-title { font-weight: 700; font-size: 13px; color: #111;
                  margin-bottom: 4px; }
.pd-trust-desc  { font-size: 12px; color: #555; line-height: 1.5; }

/* ─ S3. Features ─ */
.pd-features { display: flex; gap: 16px; flex-wrap: wrap;
               padding: 0 16px 48px; }
.pd-feat { flex: 1; min-width: 200px; background: #f8fdf9;
           border: 1.5px solid #c8f0d8; border-radius: 12px;
           padding: 24px 20px; text-align: center; }
.pd-feat-icon  { font-size: 28px; margin-bottom: 12px; }
.pd-feat-title { font-weight: 700; font-size: 15px; color: #03C75A;
                 margin-bottom: 6px; }
.pd-feat-desc  { font-size: 13px; color: #555; }

/* ─ S4. Price ─ */
.pd-price-box { margin: 0 20px 48px; background: #fffbf0;
                border: 2px solid #f0c040; border-radius: 12px;
                padding: 24px 28px; }
.pd-price-title { font-size: 17px; font-weight: 700; color: #111;
                  margin-bottom: 16px; }
.pd-price-point { display: flex; align-items: flex-start; gap: 10px;
                  margin-bottom: 10px; font-size: 14px; color: #333; }
.pd-price-point::before { content: "✓"; color: #03C75A;
                           font-weight: 700; flex-shrink: 0; }
.pd-price-guarantee { margin-top: 16px; padding: 10px 14px;
                       background: #03C75A; border-radius: 6px;
                       color: #fff; font-size: 13px; font-weight: 700;
                       text-align: center; }

/* ─ S5/S6/S7/S9/S10/S11/S12. 공통 섹션 ─ */
.pd-section { padding: 0 20px 48px; }
.pd-section-title { font-size: 20px; font-weight: 700; color: #111;
                    border-bottom: 2px solid #03C75A;
                    padding-bottom: 10px; margin-bottom: 20px; }
.pd-section p { margin: 0 0 14px; color: #333; }

/* ─ S6. Quality ─ */
.pd-quality-grid { display: grid; grid-template-columns: 1fr 1fr;
                   gap: 16px; }
.pd-quality-item { background: #f9f9f9; border-radius: 8px;
                   padding: 16px; }
.pd-quality-label { font-size: 12px; color: #888; margin-bottom: 4px; }
.pd-quality-value { font-size: 14px; font-weight: 700; color: #111; }

/* ─ S7. Origin ─ */
.pd-origin-box { background: #f5f0ff; border-left: 4px solid #8060c0;
                 border-radius: 0 8px 8px 0; padding: 18px 20px; }
.pd-origin-row { display: flex; gap: 8px; font-size: 14px;
                 margin-bottom: 8px; align-items: baseline; }
.pd-origin-label { color: #666; font-size: 13px; min-width: 80px;
                   flex-shrink: 0; }
.pd-origin-value { color: #111; font-weight: 600; }

/* ─ S8. Spec ─ */
.pd-spec-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.pd-spec-table th { background: #f0faf3; color: #1a5c33; font-weight: 700;
                    width: 32%; padding: 12px 16px;
                    border: 1px solid #d4edda; text-align: left; }
.pd-spec-table td { padding: 12px 16px; border: 1px solid #e0e0e0;
                    color: #333; }

/* ─ S9. HowTo ─ */
.pd-howto-list { list-style: none; padding: 0; margin: 0; }
.pd-howto-list li { display: flex; gap: 14px; align-items: flex-start;
                    margin-bottom: 16px; }
.pd-howto-num { width: 28px; height: 28px; border-radius: 50%;
               background: #03C75A; color: #fff; font-weight: 700;
               font-size: 13px; display: flex; align-items: center;
               justify-content: center; flex-shrink: 0; margin-top: 2px; }

/* ─ S10. AS ─ */
.pd-as-box { background: #e8f4ff; border-radius: 10px;
             padding: 20px 24px; }
.pd-as-row { display: flex; gap: 10px; font-size: 14px;
             margin-bottom: 8px; }
.pd-as-label { color: #1a5c96; font-weight: 700; min-width: 80px; }

/* ─ S11. Notice ─ */
.pd-notice-box { background: #fffbf0; border-left: 4px solid #ffc107;
                 border-radius: 0 8px 8px 0; padding: 18px 20px; }
.pd-notice-box ul { margin: 8px 0 0; padding-left: 18px; }
.pd-notice-box li { font-size: 13px; color: #555; margin-bottom: 6px; }

/* ─ S12. Delivery ─ */
.pd-delivery-box { background: #f5f5f5; border-radius: 10px;
                   padding: 20px 24px; }
.pd-delivery-box ul { margin: 0; padding-left: 16px;
                       font-size: 13px; color: #444; }
.pd-delivery-box li { margin-bottom: 6px; }

/* ─ 구분선 ─ */
.pd-divider { height: 1px; background: #eeeeee;
              margin: 0 20px 48px; }
</style>
""".strip()


# ══════════════════════════════════════════════════════════════════════════════
# 3. AI 프롬프트 표준 v2
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """당신은 대한민국 최고 수준의 스마트스토어 상품 카피라이터입니다.

【역할】
단순한 감성 카피가 아닌 "신뢰 기반 정보형" 상세설명을 작성합니다.
고객이 구매 전 궁금해하는 것: 가격이 왜 저렴한가, 품질은 믿을 수 있는가,
원산지와 유통 경로는 어디인가, AS는 되는가를 명확히 답합니다.

【콘텐츠 4대 기둥】
P1. 신뢰  — AS 보증·내구성·품질 인증을 구체적 수치/조건으로 명시
P2. 가격  — "어떻게 최저가인가"를 납득할 수 있는 근거(직수입/총판/대량구매)로 설명
P3. 정보  — 원산지·스펙·인증·소재를 정확하게, 과장 없이
P4. 유통  — 생산지→총판→판매까지 유통 경로를 투명하게 공개

【출력 규칙】
- 순수 HTML만 출력 (마크다운·코드블록 ```html 금지)
- 루트: <div class="pd"> ... </div>
- CSS 클래스: 정해진 pd-* 접두사만 사용, 인라인 스타일 금지
- 허위·과장 광고 금지: 제공된 데이터만 사용, 없는 정보는 (확인 중) 표기
- 중국산이어도 "전국 공식 총판" "정식 수입" 등 유통 신뢰성을 명확히 표기

【섹션 구조】
S1  pd-hero         헤드라인 + 서브카피 (감성적, 20자 이내)
S2  pd-trust        신뢰 뱃지 4개: 최저가보장(price) / AS보증(as) / 품질인증(quality) / 공식유통(origin)
S3  pd-features     핵심 특징 3가지 (아이콘 카드)
S4  pd-price-box    가격경쟁력: 왜 저렴한가(근거) + 최저가 보장 문구
S5  pd-section      상품 소개 본문 (2~3문단, 키워드 자연 삽입)
S6  pd-section      품질·내구성 (pd-quality-grid로 항목 표시)
S7  pd-section      원산지·유통경로 (pd-origin-box 사용)
S8  pd-section      스펙 테이블 (pd-spec-table)
S9  pd-section      사용 방법 (pd-howto-list) — 데이터 없으면 생략
S10 pd-section      AS·보증 안내 (pd-as-box)
S11 pd-section      주의 사항 (pd-notice-box)
S12 pd-section      배송·교환·반품 (pd-delivery-box)
"""

FEW_SHOT_EXAMPLE = """
【S4 가격경쟁력 예시】
<div class="pd-price-box">
  <div class="pd-price-title">💰 왜 이 가격이 가능한가?</div>
  <div class="pd-price-point">제조사 직계약 — 중간 유통 마진 제거</div>
  <div class="pd-price-point">전국 공식 총판 계약 — 대량 구매 단가 적용</div>
  <div class="pd-price-point">국내 최대 판매량 — 물류비 최적화</div>
  <div class="pd-price-guarantee">✓ 동일 제품 타 판매처 대비 최저가 보장 · 차액 200% 환불</div>
</div>

【S7 원산지·유통 예시】
<div class="pd-section">
  <div class="pd-section-title">원산지 · 유통 경로</div>
  <div class="pd-origin-box">
    <div class="pd-origin-row">
      <span class="pd-origin-label">생산지</span>
      <span class="pd-origin-value">중국 광저우 (OEM 전문 공장)</span>
    </div>
    <div class="pd-origin-row">
      <span class="pd-origin-label">수입/유통</span>
      <span class="pd-origin-value">전국 공식 총판 (국내 정식 통관 완료)</span>
    </div>
    <div class="pd-origin-row">
      <span class="pd-origin-label">공급 경로</span>
      <span class="pd-origin-value">제조사 → 공식 수입사 → 당사 (3단계 최단 경로)</span>
    </div>
    <div class="pd-origin-row">
      <span class="pd-origin-label">KC 인증</span>
      <span class="pd-origin-value">KC-R-판매자코드-2024 (전기용품 안전인증 완료)</span>
    </div>
  </div>
</div>

【S10 AS 예시】
<div class="pd-section">
  <div class="pd-section-title">A/S · 보증 안내</div>
  <div class="pd-as-box">
    <div class="pd-as-row"><span class="pd-as-label">보증기간</span>구매일로부터 1년</div>
    <div class="pd-as-row"><span class="pd-as-label">AS 방법</span>스마트스토어 문의 접수 → 24시간 내 답변</div>
    <div class="pd-as-row"><span class="pd-as-label">교환 조건</span>제품 불량·파손 시 수령 후 7일 이내 무상 교환</div>
    <div class="pd-as-row"><span class="pd-as-label">소비자 보호</span>전자상거래법 기준 준수</div>
  </div>
</div>
"""

USER_PROMPT_TEMPLATE = """
다음 상품의 HTML 상세설명을 S1~S12 섹션 구조에 맞게 작성해 주세요.
없는 정보는 (확인 중)으로 표기하고, 있는 정보는 과장 없이 정확하게 작성하세요.

═══════════════ 기본 정보 ═══════════════
■ 상품명:    {name}
■ 카테고리:  {category}
■ 브랜드:    {brand}
■ 판매가:    {price_str}
■ 타겟:      {target}

═══════════════ 핵심 특징 (S3) ═══════════════
{features_str}

═══════════════ 가격 경쟁력 (S4) ═══════════════
■ 최저가 보장 정책: {price_guarantee}
■ 가격 조사 근거:   {price_research}
■ 왜 저렴한가:      {lowest_price_reason}

═══════════════ 품질·내구성 (S6) ═══════════════
■ 내구성:    {durability}
■ 품질 인증: {quality_cert}
■ 보유 인증: {certifications_str}

═══════════════ 원산지·유통 (S7) ═══════════════
■ 원산지:      {origin}
■ 유통 경로:   {distributor}
■ 공급 경로:   {distribution_channel}

═══════════════ 스펙 (S8) ═══════════════
{specs_str}

═══════════════ SEO 키워드 (본문 자연 삽입) ═══════════════
{keywords_str}

═══════════════ 사용 방법 (S9, 없으면 생략) ═══════════════
{howto_str}

═══════════════ AS·보증 (S10) ═══════════════
■ 보증기간: {as_warranty}
■ AS 연락처: {as_contact}

═══════════════ 주의 사항 (S11) ═══════════════
{notice_str}

═══════════════ 배송·교환·반품 (S12) ═══════════════
{delivery_str}

CSS는 외부 로드됩니다. <div class="pd">로 시작하는 순수 HTML만 출력하세요.
""".strip()


# ══════════════════════════════════════════════════════════════════════════════
# 4. AI 생성 엔진
# ══════════════════════════════════════════════════════════════════════════════

# 앱 런타임 유료 AI 호출 제거(2026-09-24) — 모델 없음. 문구는 Claude Code(MCP)가 작성.
DEFAULT_MODEL = "none"


class AIDescriptionWriter:
    """신뢰 4대 기둥 기반 상세설명 AI 자동 작성기."""

    def __init__(self, page=None, model: str = DEFAULT_MODEL):
        self.page = page
        self.model = model

    # ── 공개 인터페이스 ──────────────────────────────────────────────────────

    def generate(self, product: dict) -> dict:
        """표준 프롬프트로 HTML 상세설명 생성."""
        errs = validate_product_data(product)
        hard = [e for e in errs if e.startswith("[필수]") or e.startswith("[오류]")]
        warns = [e for e in errs if not e.startswith("[필수]") and not e.startswith("[오류]")]
        if hard:
            return {"ok": False, "errors": hard}

        # 앱 런타임 유료 AI 호출 제거(2026-09-24, 사용자 승인). 앱 안에서 문구를 생성하지 않는다.
        # 표준 프롬프트는 돌려주어 Claude Code(MCP)가 문구를 쓰고 finalize()/render_description 으로 마감한다.
        _log.info("[ai-desc] 앱 AI 비활성 — 프롬프트만 반환 / 경고: %s", warns)
        return {
            "ok": False,
            "error": "app_ai_disabled",
            "hint": "앱 런타임 AI 없음 — 상세설명 문구는 Claude Code(MCP)가 작성해 render_description/save_template 로 저장",
            "prompt": {
                "system": SYSTEM_PROMPT + "\n\n" + FEW_SHOT_EXAMPLE,
                "user": self._build_user_prompt(product),
            },
            "warnings": warns,
        }

    def finalize(self, text: str) -> str:
        """외부(Claude Code)에서 작성한 본문을 표준 HTML(CSS 포함)로 마감."""
        return self._finalize_html(text)

    def write(self, product: dict, image_paths: list[str] | None = None) -> dict:
        """생성 + SmartEditor 자동 입력."""
        gen = self.generate(product)
        if not gen["ok"]:
            return gen

        html = gen["html"]
        if self.page is None:
            return {"ok": True, "html": html, "inserted": False, "note": "page 없음 — HTML만 반환"}

        from scripts.naver.smartstore.product.description_editor import SmartEditorSession

        ed = SmartEditorSession(self.page)

        if "#/editor" not in self.page.url:
            if not ed.open(from_register_form=True):
                return {"ok": False, "html": html, "inserted": False, "error": "SmartEditor 진입 실패"}
            time.sleep(2)

        r_html = ed.block.insert_html(html)
        if not r_html["ok"]:
            _log.warning("[ai-desc] HTML 삽입 실패 — 텍스트 fallback")
            ed.write_text(self._html_to_plain(html))

        img_results = []
        for path in image_paths or []:
            img_results.append({"path": path, **ed.block.insert_image_file(path)})

        return {
            "ok": True,
            "html": html,
            "inserted": True,
            "images": img_results,
            "model": gen["model"],
            "warnings": gen.get("warnings", []),
        }

    def preview(self, product: dict) -> str:
        """HTML 미리보기 파일 저장 → 경로 반환."""
        gen = self.generate(product)
        if not gen["ok"]:
            return ""
        out = data_dir() / "smartstore" / "description_preview.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        full = (
            f"<!DOCTYPE html><html lang='ko'><head>"
            f"<meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            f"{CSS_DESIGN_SYSTEM}</head><body>{gen['html']}</body></html>"
        )
        out.write_text(full, encoding="utf-8")
        _log.info("[ai-desc] 미리보기: %s", out)
        return str(out)

    # ── 프롬프트 빌더 ────────────────────────────────────────────────────────

    def _build_user_prompt(self, p: dict) -> str:
        def _list(items, prefix="  "):
            if not items:
                return f"{prefix}(미제공)"
            if isinstance(items, list):
                return "\n".join(f"{prefix}{i + 1}. {v}" for i, v in enumerate(items))
            return f"{prefix}{items}"

        def _dict(d, prefix="  "):
            if not d:
                return f"{prefix}(미제공)"
            return "\n".join(f"{prefix}- {k}: {v}" for k, v in d.items())

        price_str = f"{int(p.get('price', 0)):,}원"
        if p.get("original_price"):
            price_str += f" (정가 {int(p['original_price']):,}원)"

        return USER_PROMPT_TEMPLATE.format(
            name=p.get("name", ""),
            category=p.get("category", ""),
            brand=p.get("brand", "(미제공)"),
            price_str=price_str,
            target=p.get("target", "합리적인 소비를 원하는 고객"),
            features_str=_list(p.get("features", [])),
            price_guarantee=p.get("price_guarantee", "동일 상품 최저가 보장 · 차액 200% 환불"),
            price_research=p.get("price_research", "(미제공 — 일반적 근거로 작성)"),
            lowest_price_reason=p.get("lowest_price_reason", "(미제공 — 일반적 근거로 작성)"),
            durability=p.get("durability", "(미제공)"),
            quality_cert=p.get("quality_cert", "(미제공)"),
            certifications_str=", ".join(p.get("certifications", [])) or "(미제공)",
            origin=p.get("origin", "(미제공)"),
            distributor=p.get("distributor", "(미제공)"),
            distribution_channel=p.get("distribution_channel", "(미제공)"),
            specs_str=_dict(p.get("specs", {})),
            keywords_str=", ".join(p.get("keywords", [])) or "(미제공)",
            howto_str=_list(p.get("howto", [])) if p.get("howto") else "  (없음 — S9 생략)",
            as_warranty=p.get("as_warranty", "(미제공)"),
            as_contact=p.get("as_contact", "스마트스토어 문의"),
            notice_str=p.get("notice", "직사광선·고온다습 피해 보관, 어린이 손 닿지 않는 곳"),
            delivery_str=p.get("delivery", DEFAULT_DELIVERY),
        )

    # ── HTML 후처리 ──────────────────────────────────────────────────────────

    def _finalize_html(self, raw: str) -> str:
        text = re.sub(r"```html\s*", "", raw)
        text = re.sub(r"```\s*", "", text).strip()
        if '<div class="pd"' in text and not text.startswith('<div class="pd"'):
            text = text[text.index('<div class="pd"') :]
        elif "<div" not in text:
            text = f'<div class="pd">{text}</div>'
        return CSS_DESIGN_SYSTEM + "\n" + text

    def _html_to_plain(self, html: str) -> str:
        text = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s{2,}", "\n", text).strip()


# ══════════════════════════════════════════════════════════════════════════════
# 편의 함수
# ══════════════════════════════════════════════════════════════════════════════


def generate_description(product: dict, model: str = DEFAULT_MODEL) -> dict:
    """page 없이 HTML만 생성."""
    return AIDescriptionWriter(page=None, model=model).generate(product)


def write_description(page, product: dict, image_paths: list[str] | None = None, model: str = DEFAULT_MODEL) -> dict:
    """SmartEditor 자동 입력 원샷."""
    return AIDescriptionWriter(page=page, model=model).write(product, image_paths=image_paths)


def preview_description(product: dict, model: str = DEFAULT_MODEL) -> str:
    """HTML 미리보기 파일 경로 반환."""
    return AIDescriptionWriter(page=None, model=model).preview(product)
