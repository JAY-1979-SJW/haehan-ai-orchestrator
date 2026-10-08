"""스마트스토어 상품 상세페이지 빌더 (L3 Connector).

섹션별 독립 모듈 — 사용자가 필요한 섹션만 선택해 조합.

사용:
    from scripts.naver.smartstore.product.page_builder import ProductPageBuilder

    builder = ProductPageBuilder()

    # 원하는 섹션만 선택
    builder.select(["hero", "trust", "features", "price", "spec", "as", "delivery"])

    # 상품 데이터로 렌더링
    html = builder.render({
        "name":     "프리미엄 LED 무드등",
        "price":    29800,
        "category": "생활/주방 > 조명",
        "features": [
            {"icon": "✋", "title": "터치 제어",    "desc": "버튼 없이 터치 한 번"},
            {"icon": "🎨", "title": "16가지 색상",  "desc": "RGB 풀컬러"},
            {"icon": "🔋", "title": "최대 8시간",   "desc": "USB-C 완충 후"},
        ],
        "price_reasons": [
            {"title": "제조사 직계약",      "desc": "중간 마진 제거"},
            {"title": "전국 총판 계약",     "desc": "대량 발주 단가"},
            {"title": "스마트스토어 직판",  "desc": "오프라인 비용 없음"},
            {"title": "실시간 가격 조사",   "desc": "3개 플랫폼 비교"},
        ],
        "specs": {"크기": "Φ8×12cm", "배터리": "2000mAh", "방수": "IPX4"},
        "as_warranty": "1년",
        "as_contact":  "스마트스토어 문의",
        "origin":      "중국 광저우",
        "distributor": "전국 공식 총판",
    })

    # 파일 저장
    builder.save(html, "data/smartstore/description_preview.html")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import data_dir

ROOT = Path(__file__).resolve().parents[4]


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 레지스트리 — 12개 섹션 메타 정보
# ══════════════════════════════════════════════════════════════════════════════

SECTION_REGISTRY = {
    "hero": {"label": "Hero — 헤드라인", "required": True, "data_keys": ["name", "price", "hero_tag", "sub"]},
    "trust": {"label": "신뢰 뱃지 4개", "required": False, "data_keys": ["trust_badges"]},
    "features": {"label": "핵심 특징 카드", "required": False, "data_keys": ["features"]},
    "price": {"label": "가격 경쟁력", "required": False, "data_keys": ["price_reasons", "price_guarantee"]},
    "detail": {"label": "상품 소개 본문", "required": False, "data_keys": ["detail_paragraphs"]},
    "quality": {"label": "품질·내구성 그리드", "required": False, "data_keys": ["quality_items"]},
    "origin": {
        "label": "원산지·유통 경로",
        "required": False,
        "data_keys": ["origin", "distributor", "distribution_channel"],
    },
    "spec": {"label": "스펙 테이블", "required": False, "data_keys": ["specs"]},
    "howto": {"label": "사용 방법", "required": False, "data_keys": ["howto"]},
    "as": {"label": "AS·보증 안내", "required": False, "data_keys": ["as_warranty", "as_contact"]},
    "notice": {"label": "주의 사항", "required": False, "data_keys": ["notice_items"]},
    "delivery": {"label": "배송·교환·반품", "required": True, "data_keys": ["delivery_items"]},
    "before_after": {
        "label": "제품 사진 · 비포/애프터",
        "required": False,
        "data_keys": ["hero_image", "before_after_pairs", "gallery_images", "before_after_title"],
    },
    "price_compare": {
        "label": "타 판매처 가격 비교",
        "required": False,
        "data_keys": ["price_compare_title", "price_compare_rows", "price_compare_caption"],
    },
    "consult_flow": {
        "label": "상담·시안 흐름 안내",
        "required": False,
        "data_keys": ["consult_title", "consult_lead", "consult_steps", "consult_cta"],
    },
}

DEFAULT_SECTIONS = [
    "hero",
    "before_after",
    "trust",
    "features",
    "price",
    "detail",
    "quality",
    "origin",
    "spec",
    "price_compare",
    "howto",
    "consult_flow",
    "as",
    "notice",
    "delivery",
]


# ══════════════════════════════════════════════════════════════════════════════
# CSS 디자인 시스템 (외부 주입용)
# ══════════════════════════════════════════════════════════════════════════════

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700;900&display=swap');
:root {
  --green:#03C75A;--green-d:#029a46;--green-l:#e8faf0;
  --blue:#1a5c96;--blue-l:#e8f2ff;
  --gold:#e8a020;--gold-l:#fff8e8;
  --purple:#7c4dce;--purple-l:#f5f0ff;
  --t1:#0f0f0f;--t2:#333;--t3:#666;--t4:#999;
  --bd:#e8e8e8;--bg:#fafafa;
  --sh-s:0 2px 8px rgba(0,0,0,.08);
  --sh-m:0 4px 20px rgba(0,0,0,.10);
  --r-s:8px;--r-m:14px;--r-l:20px;
}
*{box-sizing:border-box;margin:0;padding:0;}
.pd{font-family:'Noto Sans KR',-apple-system,sans-serif;color:var(--t1);
    max-width:800px;margin:0 auto;background:#fff;
    font-size:15px;line-height:1.75;word-break:keep-all;overflow:hidden;}
/* Hero */
.pd-hero{position:relative;padding:64px 32px 56px;text-align:center;
  background:linear-gradient(160deg,#0a2e1a 0%,#0f4d2a 45%,#1a6b3a 100%);overflow:hidden;}
.pd-hero::before{content:'';position:absolute;top:-60px;right:-60px;
  width:280px;height:280px;background:rgba(255,255,255,.04);border-radius:50%;}
.pd-hero::after{content:'';position:absolute;bottom:-80px;left:-40px;
  width:240px;height:240px;background:rgba(255,255,255,.03);border-radius:50%;}
.pd-hero-tag{display:inline-block;background:rgba(255,255,255,.15);color:#a8f0c8;
  font-size:12px;font-weight:700;letter-spacing:.08em;padding:5px 14px;
  border-radius:999px;border:1px solid rgba(255,255,255,.2);margin-bottom:22px;}
.pd-headline{font-size:36px;font-weight:900;color:#fff;line-height:1.25;
  margin-bottom:18px;letter-spacing:-.02em;position:relative;z-index:1;}
.pd-sub{font-size:16px;color:rgba(255,255,255,.75);max-width:440px;
  margin:0 auto 28px;font-weight:300;position:relative;z-index:1;}
.pd-hero-price{display:inline-flex;align-items:center;gap:12px;
  background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);
  border-radius:999px;padding:10px 24px;position:relative;z-index:1;}
.pd-hero-price-label{font-size:13px;color:rgba(255,255,255,.65);}
.pd-hero-price-value{font-size:22px;font-weight:900;color:#fff;}
.pd-hero-price-badge{background:var(--gold);color:#fff;font-size:11px;
  font-weight:700;padding:3px 9px;border-radius:999px;}
/* Trust */
.pd-trust{display:grid;grid-template-columns:repeat(4,1fr);gap:0;border-bottom:1px solid var(--bd);}
.pd-trust-badge{padding:20px 12px;text-align:center;border-right:1px solid var(--bd);}
.pd-trust-badge:last-child{border-right:none;}
.pd-trust-icon{font-size:26px;margin-bottom:8px;display:block;}
.pd-trust-title{font-weight:700;font-size:13px;color:var(--t1);margin-bottom:4px;}
.pd-trust-desc{font-size:11px;color:var(--t3);line-height:1.5;}
.pd-trust-badge.price .pd-trust-title{color:var(--gold);}
.pd-trust-badge.as .pd-trust-title{color:var(--blue);}
.pd-trust-badge.quality .pd-trust-title{color:var(--green);}
.pd-trust-badge.origin .pd-trust-title{color:var(--purple);}
/* Features */
.pd-features{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;
  padding:36px 32px;background:var(--bg);border-bottom:1px solid var(--bd);}
.pd-feat{background:#fff;border-radius:var(--r-m);padding:28px 20px;text-align:center;
  box-shadow:var(--sh-s);border:1px solid var(--bd);}
.pd-feat-icon{font-size:36px;margin-bottom:14px;display:block;}
.pd-feat-title{font-weight:700;font-size:15px;color:var(--t1);margin-bottom:8px;}
.pd-feat-desc{font-size:13px;color:var(--t3);line-height:1.6;}
/* 공통 섹션 */
.pd-sec{padding:52px 32px;border-bottom:1px solid var(--bd);}
.pd-sec:last-child{border-bottom:none;}
.pd-sec-eyebrow{font-size:11px;font-weight:700;letter-spacing:.12em;
  text-transform:uppercase;color:var(--green);margin-bottom:6px;}
.pd-sec-title{font-size:22px;font-weight:900;color:var(--t1);
  margin-bottom:24px;letter-spacing:-.02em;}
.pd-sec p{color:var(--t2);margin-bottom:16px;}
/* Price */
.pd-price{background:linear-gradient(135deg,#fffdf5 0%,#fff8e0 100%);
  border-bottom:1px solid #f0e0a0;}
.pd-price-reasons{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:24px;}
.pd-price-reason{background:#fff;border-radius:var(--r-s);padding:14px 16px;
  display:flex;gap:10px;align-items:flex-start;box-shadow:0 1px 4px rgba(0,0,0,.06);}
.pd-price-check{width:20px;height:20px;background:var(--green);border-radius:50%;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
  color:#fff;font-size:11px;font-weight:700;margin-top:1px;}
.pd-price-text{font-size:13px;color:var(--t2);line-height:1.55;}
.pd-price-text strong{display:block;font-size:14px;color:var(--t1);margin-bottom:2px;}
.pd-price-cta{background:linear-gradient(135deg,var(--green) 0%,var(--green-d) 100%);
  border-radius:var(--r-m);padding:18px 24px;display:flex;
  align-items:center;justify-content:space-between;gap:12px;}
.pd-price-cta-text{font-size:15px;font-weight:700;color:#fff;}
.pd-price-cta-badge{background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.35);
  border-radius:999px;padding:6px 16px;font-size:13px;font-weight:700;color:#fff;white-space:nowrap;}
/* Quality */
.pd-quality-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;}
.pd-quality-item{background:var(--bg);border:1px solid var(--bd);
  border-radius:var(--r-s);padding:16px;}
.pd-quality-label{font-size:11px;color:var(--t4);font-weight:700;
  letter-spacing:.05em;text-transform:uppercase;margin-bottom:6px;}
.pd-quality-value{font-size:14px;font-weight:700;color:var(--t1);}
/* Origin */
.pd-origin{background:linear-gradient(135deg,#f7f0ff 0%,#f0ebff 100%);
  border-bottom:1px solid #d8c8f0;}
.pd-origin-card{background:#fff;border-radius:var(--r-m);overflow:hidden;box-shadow:var(--sh-s);}
.pd-origin-header{background:linear-gradient(135deg,var(--purple) 0%,#5c3ab0 100%);
  padding:14px 20px;display:flex;align-items:center;gap:10px;}
.pd-origin-header-icon{font-size:20px;}
.pd-origin-header-title{font-size:15px;font-weight:700;color:#fff;}
.pd-origin-row{display:flex;border-bottom:1px solid var(--bd);font-size:14px;}
.pd-origin-row:last-child{border-bottom:none;}
.pd-origin-label{width:100px;padding:14px 16px;font-weight:700;color:var(--purple);
  font-size:13px;background:#faf7ff;flex-shrink:0;border-right:1px solid var(--bd);}
.pd-origin-value{padding:14px 16px;color:var(--t2);flex:1;}
/* Spec */
.pd-spec-table{width:100%;border-collapse:collapse;font-size:14px;
  border-radius:var(--r-s);overflow:hidden;box-shadow:var(--sh-s);}
.pd-spec-table tr:nth-child(even) td{background:var(--bg);}
.pd-spec-table tr:nth-child(even) th{background:#e4f5ec;}
.pd-spec-table th{background:#edfaf4;color:#0d5c33;font-weight:700;
  width:28%;padding:13px 16px;border-bottom:1px solid #cce8d8;
  text-align:left;font-size:13px;}
.pd-spec-table td{padding:13px 16px;border-bottom:1px solid var(--bd);color:var(--t2);}
.pd-spec-table tr:last-child th,.pd-spec-table tr:last-child td{border-bottom:none;}
/* HowTo */
.pd-howto-list{list-style:none;display:flex;flex-direction:column;gap:0;}
.pd-howto-item{display:flex;gap:0;align-items:stretch;}
.pd-howto-left{display:flex;flex-direction:column;align-items:center;width:48px;flex-shrink:0;}
.pd-howto-num{width:36px;height:36px;border-radius:50%;background:var(--green);
  color:#fff;font-weight:900;font-size:15px;display:flex;align-items:center;
  justify-content:center;box-shadow:0 2px 8px rgba(3,199,90,.3);}
.pd-howto-line{width:2px;background:#d0f0e0;flex:1;margin:4px 0;}
.pd-howto-item:last-child .pd-howto-line{display:none;}
.pd-howto-content{padding:6px 0 24px 16px;flex:1;font-size:14px;color:var(--t2);}
.pd-howto-content strong{display:block;font-size:15px;color:var(--t1);margin-bottom:2px;}
/* AS */
.pd-as{background:var(--blue-l);border-bottom:1px solid #c0d8f0;}
.pd-as-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
.pd-as-item{background:#fff;border-radius:var(--r-s);padding:16px 18px;
  display:flex;gap:12px;align-items:flex-start;box-shadow:0 1px 4px rgba(0,0,0,.06);}
.pd-as-icon{font-size:22px;flex-shrink:0;margin-top:2px;}
.pd-as-label{font-size:12px;color:var(--blue);font-weight:700;margin-bottom:3px;}
.pd-as-value{font-size:13px;color:var(--t2);line-height:1.55;}
/* Notice */
.pd-notice-box{background:#fff9ed;border:1px solid #f0d888;border-radius:var(--r-m);
  padding:20px 22px;display:flex;gap:14px;align-items:flex-start;}
.pd-notice-icon{font-size:24px;flex-shrink:0;margin-top:2px;}
.pd-notice-list{list-style:none;flex:1;}
.pd-notice-list li{font-size:13px;color:var(--t2);padding:6px 0;
  border-bottom:1px solid #f0e8c8;display:flex;gap:8px;align-items:baseline;}
.pd-notice-list li:last-child{border-bottom:none;padding-bottom:0;}
.pd-notice-list li::before{content:"·";color:var(--gold);font-weight:900;
  font-size:16px;flex-shrink:0;}
/* Delivery */
.pd-delivery-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;}
.pd-delivery-item{background:var(--bg);border:1px solid var(--bd);
  border-radius:var(--r-s);padding:14px 16px;display:flex;gap:10px;align-items:flex-start;}
.pd-delivery-emoji{font-size:18px;flex-shrink:0;}
.pd-delivery-label{font-weight:700;color:var(--t1);font-size:13px;margin-bottom:2px;}
.pd-delivery-desc{color:var(--t3);font-size:12px;line-height:1.5;}
/* 구분선 */
.pd-divider{height:8px;background:var(--bg);border-top:1px solid var(--bd);border-bottom:1px solid var(--bd);}
/* 제품 사진 / 비포·애프터 (2026-09-28: 설치상담형 나레이티브 상세페이지 스크립트 통합) */
.pd-photo{width:100%;display:block;border-radius:var(--r-m);margin-bottom:16px;}
.pd-before-after{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:8px;}
.pd-ba-item{text-align:center;}
.pd-ba-item .pd-photo{margin-bottom:6px;}
.pd-ba-caption{font-size:12px;color:var(--t4);margin-bottom:16px;}
.pd-gallery{display:flex;flex-direction:column;gap:16px;margin-top:16px;}
/* 타 판매처 가격 비교 */
.pd-pc-table{width:100%;border-collapse:collapse;margin-bottom:16px;}
.pd-pc-label,.pd-pc-price{padding:10px 12px;border-bottom:1px solid var(--bd);font-size:14px;}
.pd-pc-price{text-align:right;}
.pd-pc-highlight-label,.pd-pc-highlight-price{padding:10px 12px;background:var(--gold-l);font-weight:700;font-size:15px;}
.pd-pc-highlight-price{text-align:right;color:var(--gold);font-size:16px;}
.pd-pc-caption{text-align:center;font-size:13px;color:var(--t3);}
/* 상담·시안 흐름 안내 */
.pd-consult{background:var(--green-l);}
.pd-consult p{text-align:center;}
</style>
""".strip()


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 렌더러 — 각 섹션 독립 함수
# ══════════════════════════════════════════════════════════════════════════════


def _e(text: Any) -> str:
    """HTML 이스케이프."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_hero(d: dict) -> str:
    tag = _e(d.get("hero_tag", "전국 공식 총판"))
    name = _e(d.get("name", "상품명"))
    sub = _e(d.get("sub", ""))
    price = f"{int(d.get('price', 0)):,}"
    badge = _e(d.get("price_badge", "최저가 보장"))
    return f"""
<div class="pd-hero">
  <div class="pd-hero-tag">🌟 {tag}</div>
  <h1 class="pd-headline">{name}</h1>
  {"" if not sub else f'<p class="pd-sub">{sub}</p>'}
  <div class="pd-hero-price">
    <span class="pd-hero-price-label">판매가</span>
    <span class="pd-hero-price-value">{price}원</span>
    <span class="pd-hero-price-badge">{badge}</span>
  </div>
</div>"""


def render_trust(d: dict) -> str:
    badges = d.get(
        "trust_badges",
        [
            {"cls": "price", "icon": "💰", "title": "최저가 보장", "desc": "차액 200% 환불"},
            {"cls": "as", "icon": "🛡️", "title": "1년 무상 AS", "desc": "불량 시 무상 교환"},
            {"cls": "quality", "icon": "✅", "title": "KC 안전인증", "desc": "국내 안전인증 완료"},
            {"cls": "origin", "icon": "🏭", "title": "공식 총판", "desc": "정식 수입 통관"},
        ],
    )
    items = "\n".join(
        f"""  <div class="pd-trust-badge {_e(b.get("cls", ""))}">
    <span class="pd-trust-icon">{b.get("icon", "")}</span>
    <div class="pd-trust-title">{_e(b.get("title", ""))}</div>
    <div class="pd-trust-desc">{_e(b.get("desc", ""))}</div>
  </div>"""
        for b in badges
    )
    return f'<div class="pd-trust">\n{items}\n</div>'


def render_features(d: dict) -> str:
    feats = d.get("features", [])
    if not feats:
        return ""
    items = "\n".join(
        f"""  <div class="pd-feat">
    <span class="pd-feat-icon">{f.get("icon", "⭐")}</span>
    <div class="pd-feat-title">{_e(f.get("title", ""))}</div>
    <div class="pd-feat-desc">{_e(f.get("desc", ""))}</div>
  </div>"""
        for f in feats
    )
    return f'<div class="pd-features">\n{items}\n</div>'


def render_price(d: dict) -> str:
    reasons = d.get("price_reasons", [])
    guarantee = _e(d.get("price_guarantee", "동일 제품 타 판매처보다 비싸면 차액의 200% 환불"))
    reason_html = "\n".join(
        f"""    <div class="pd-price-reason">
      <div class="pd-price-check">✓</div>
      <div class="pd-price-text"><strong>{_e(r.get("title", ""))}</strong>{_e(r.get("desc", ""))}</div>
    </div>"""
        for r in reasons
    )
    return f"""
<div class="pd-sec pd-price">
  <div class="pd-sec-eyebrow">Price Advantage</div>
  <div class="pd-sec-title">이 가격이 가능한 이유</div>
  <div class="pd-price-reasons">
{reason_html}
  </div>
  <div class="pd-price-cta">
    <div class="pd-price-cta-text">✓ {guarantee}</div>
    <div class="pd-price-cta-badge">최저가 보장제</div>
  </div>
</div>"""


def render_detail(d: dict) -> str:
    paragraphs = d.get("detail_paragraphs", [])
    if not paragraphs:
        return ""
    body = "\n".join(f"  <p>{_e(p)}</p>" for p in paragraphs)
    return f"""
<div class="pd-sec">
  <div class="pd-sec-eyebrow">About</div>
  <div class="pd-sec-title">상품 소개</div>
{body}
</div>"""


def render_quality(d: dict) -> str:
    items = d.get("quality_items", [])
    if not items:
        return ""
    grid = "\n".join(
        f"""  <div class="pd-quality-item">
    <div class="pd-quality-label">{_e(item.get("label", ""))}</div>
    <div class="pd-quality-value">{_e(item.get("value", ""))}</div>
  </div>"""
        for item in items
    )
    return f"""
<div class="pd-sec">
  <div class="pd-sec-eyebrow">Quality</div>
  <div class="pd-sec-title">품질 · 내구성</div>
  <div class="pd-quality-grid">
{grid}
  </div>
</div>"""


def render_origin(d: dict) -> str:
    rows = []
    if d.get("origin"):
        rows.append({"label": "생산지", "value": d["origin"]})
    if d.get("distributor"):
        rows.append({"label": "수입·유통", "value": d["distributor"]})
    if d.get("distribution_channel"):
        rows.append({"label": "공급 경로", "value": d["distribution_channel"]})
    if d.get("certifications"):
        rows.append({"label": "인증", "value": ", ".join(d["certifications"])})
    if d.get("origin_reason"):
        rows.append({"label": "원산지 이유", "value": d["origin_reason"]})
    if not rows:
        return ""
    row_html = "\n".join(
        f"""    <div class="pd-origin-row">
      <div class="pd-origin-label">{_e(r["label"])}</div>
      <div class="pd-origin-value">{_e(r["value"])}</div>
    </div>"""
        for r in rows
    )
    header_title = _e(d.get("origin_header", "공급망 투명 공개 — 숨기는 것 없이 모두 알려드립니다"))
    return f"""
<div class="pd-sec pd-origin">
  <div class="pd-sec-eyebrow">Transparency</div>
  <div class="pd-sec-title">원산지 · 유통 경로</div>
  <div class="pd-origin-card">
    <div class="pd-origin-header">
      <span class="pd-origin-header-icon">🏭</span>
      <span class="pd-origin-header-title">{header_title}</span>
    </div>
{row_html}
  </div>
</div>"""


def render_spec(d: dict) -> str:
    specs = d.get("specs", {})
    if not specs:
        return ""
    rows = "\n".join(f"    <tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>" for k, v in specs.items())
    return f"""
<div class="pd-sec">
  <div class="pd-sec-eyebrow">Specifications</div>
  <div class="pd-sec-title">상품 스펙</div>
  <table class="pd-spec-table">
{rows}
  </table>
</div>"""


def render_howto(d: dict) -> str:
    steps = d.get("howto", [])
    if not steps:
        return ""
    items = "\n".join(
        f"""  <li class="pd-howto-item">
    <div class="pd-howto-left">
      <div class="pd-howto-num">{i + 1}</div>
      <div class="pd-howto-line"></div>
    </div>
    <div class="pd-howto-content">
      <strong>{_e(s.get("title", ""))}</strong>{_e(s.get("desc", ""))}
    </div>
  </li>"""
        for i, s in enumerate(steps)
    )
    return f"""
<div class="pd-sec">
  <div class="pd-sec-eyebrow">How to Use</div>
  <div class="pd-sec-title">이용 방법</div>
  <ul class="pd-howto-list">
{items}
  </ul>
</div>"""


def render_as(d: dict) -> str:
    items = d.get("as_items", [])
    if not items:
        # 기본 항목 구성
        items = []
        if d.get("as_warranty"):
            items.append({"icon": "📅", "label": "보증 기간", "value": d["as_warranty"]})
        if d.get("as_exchange"):
            items.append({"icon": "🔄", "label": "무상 교환", "value": d["as_exchange"]})
        if d.get("as_contact"):
            items.append({"icon": "💬", "label": "AS 방법", "value": d["as_contact"]})
        if d.get("as_scope"):
            items.append({"icon": "⚖️", "label": "AS 범위", "value": d["as_scope"]})
        if not items:
            items = [
                {"icon": "📅", "label": "보증 기간", "value": "구매일로부터 1년"},
                {"icon": "🔄", "label": "무상 교환", "value": "불량 수령 7일 이내"},
                {"icon": "💬", "label": "AS 방법", "value": "스마트스토어 문의"},
                {"icon": "⚖️", "label": "소비자 보호", "value": "전자상거래법 준수"},
            ]
    grid = "\n".join(
        f"""  <div class="pd-as-item">
    <span class="pd-as-icon">{item.get("icon", "📋")}</span>
    <div>
      <div class="pd-as-label">{_e(item.get("label", ""))}</div>
      <div class="pd-as-value">{_e(item.get("value", ""))}</div>
    </div>
  </div>"""
        for item in items
    )
    return f"""
<div class="pd-sec pd-as">
  <div class="pd-sec-eyebrow">After Service</div>
  <div class="pd-sec-title">A/S · 보증 안내</div>
  <div class="pd-as-grid">
{grid}
  </div>
</div>"""


def render_notice(d: dict) -> str:
    items = d.get("notice_items", [])
    if not items:
        return ""
    li_html = "\n".join(f"      <li>{_e(item)}</li>" for item in items)
    return f"""
<div class="pd-sec">
  <div class="pd-sec-eyebrow">Notice</div>
  <div class="pd-sec-title">주의 사항</div>
  <div class="pd-notice-box">
    <span class="pd-notice-icon">⚠️</span>
    <ul class="pd-notice-list">
{li_html}
    </ul>
  </div>
</div>"""


def render_before_after(d: dict) -> str:
    """제품 사진 + 비포/애프터 비교 + 갤러리(설치상담형 나레이티브 상세페이지에서 이관, 2026-09-28).

    data 키:
        hero_image: {"url", "alt"} — 대표 사진 1장(선택)
        before_after_pairs: [{"before_url","before_alt","before_caption",
                               "after_url","after_alt","after_caption"}, ...]
        gallery_images: [{"url","alt"}, ...] — 후속 라이프스타일 이미지들
        before_after_title: 섹션 제목(기본값 있음)
    """
    parts = []
    hero = d.get("hero_image")
    if hero and hero.get("url"):
        parts.append(f'<img class="pd-photo" src="{_e(hero["url"])}" alt="{_e(hero.get("alt", ""))}" />')
    for pair in d.get("before_after_pairs", []):
        parts.append(f"""<div class="pd-before-after">
  <div class="pd-ba-item">
    <img class="pd-photo" src="{_e(pair["before_url"])}" alt="{_e(pair.get("before_alt", ""))}" />
    <div class="pd-ba-caption">{_e(pair.get("before_caption", "BEFORE"))}</div>
  </div>
  <div class="pd-ba-item">
    <img class="pd-photo" src="{_e(pair["after_url"])}" alt="{_e(pair.get("after_alt", ""))}" />
    <div class="pd-ba-caption">{_e(pair.get("after_caption", "AFTER"))}</div>
  </div>
</div>""")
    gallery = d.get("gallery_images", [])
    if gallery:
        items = "\n".join(
            f'  <img class="pd-photo" src="{_e(g["url"])}" alt="{_e(g.get("alt", ""))}" />' for g in gallery
        )
        parts.append(f'<div class="pd-gallery">\n{items}\n</div>')
    if not parts:
        return ""
    body = "\n".join(parts)
    title = _e(d.get("before_after_title", "설치 전후, 공간은 얼마나 달라질까요?"))
    return f"""
<div class="pd-sec">
  <div class="pd-sec-eyebrow">Before &amp; After</div>
  <div class="pd-sec-title">{title}</div>
{body}
</div>"""


def render_price_compare(d: dict) -> str:
    """타 판매처 가격 비교표(설치상담형 나레이티브 상세페이지에서 이관, 2026-09-28).

    data 키:
        price_compare_rows: [{"label","price","highlight": bool}, ...]
        price_compare_title / price_compare_caption: 제목/하단 설명(기본값 있음)
    """
    rows = d.get("price_compare_rows", [])
    if not rows:
        return ""
    row_html = []
    for r in rows:
        label, price = _e(r.get("label", "")), _e(r.get("price", ""))
        if r.get("highlight"):
            row_html.append(
                f'<tr><td class="pd-pc-highlight-label">{label}</td><td class="pd-pc-highlight-price">{price}</td></tr>'
            )
        else:
            row_html.append(f'<tr><td class="pd-pc-label">{label}</td><td class="pd-pc-price">{price}</td></tr>')
    caption = d.get("price_compare_caption", "합리적인 제품 가격과 필요한 시공비를 투명하게 안내합니다.")
    title = _e(d.get("price_compare_title", "온라인 가격도 충분히 비교해 보세요"))
    return f"""
<div class="pd-sec">
  <div class="pd-sec-eyebrow">Price Compare</div>
  <div class="pd-sec-title">{title}</div>
  <table class="pd-pc-table">{"".join(row_html)}</table>
  <p class="pd-pc-caption">{_e(caption)}</p>
</div>"""


def render_consult_flow(d: dict) -> str:
    """상담·시안 요청 흐름 안내(설치상담형 나레이티브 상세페이지에서 이관, 2026-09-28).

    data 키:
        consult_steps: ["공간 사진 전송", "검토", "시안 제작", ...] — 화살표로 연결해 렌더링
        consult_title / consult_lead / consult_cta: 제목/도입 문구/마무리 문구(선택)
    """
    steps = d.get("consult_steps", [])
    if not steps:
        return ""
    parts = []
    lead = d.get("consult_lead")
    if lead:
        parts.append(f"<p>{_e(lead)}</p>")
    parts.append("<p style='font-weight:700;'>" + " → ".join(_e(s) for s in steps) + "</p>")
    cta = d.get("consult_cta")
    if cta:
        parts.append(f"<p style='font-weight:700;'>{_e(cta)}</p>")
    body = "\n".join(parts)
    title = _e(d.get("consult_title", "먼저 상담받고 시안부터 확인하세요"))
    return f"""
<div class="pd-sec pd-consult">
  <div class="pd-sec-eyebrow">Consultation</div>
  <div class="pd-sec-title">{title}</div>
{body}
</div>"""


def render_delivery(d: dict) -> str:
    items = d.get(
        "delivery_items",
        [
            {"emoji": "📦", "label": "배송비", "desc": "무료 (CJ대한통운 · 롯데택배)"},
            {"emoji": "🚀", "label": "출고 기준", "desc": "평일 오후 2시 이전 결제 → 당일 출고"},
            {"emoji": "⏱️", "label": "배송 기간", "desc": "출고 후 1~3 영업일 수령"},
            {"emoji": "🏝️", "label": "도서산간", "desc": "제주·도서산간 추가 3,000원"},
            {"emoji": "🔄", "label": "교환·반품", "desc": "수령 후 7일 이내 (단순 변심 왕복 배송비 구매자 부담)"},
            {"emoji": "✅", "label": "불량·오배송", "desc": "판매자 전액 부담 처리"},
        ],
    )
    grid = "\n".join(
        f"""  <div class="pd-delivery-item">
    <span class="pd-delivery-emoji">{item.get("emoji", "📦")}</span>
    <div>
      <div class="pd-delivery-label">{_e(item.get("label", ""))}</div>
      <div class="pd-delivery-desc">{_e(item.get("desc", ""))}</div>
    </div>
  </div>"""
        for item in items
    )
    return f"""
<div class="pd-sec">
  <div class="pd-sec-eyebrow">Delivery</div>
  <div class="pd-sec-title">배송 · 교환 · 반품</div>
  <div class="pd-delivery-grid">
{grid}
  </div>
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 렌더러 맵
# ══════════════════════════════════════════════════════════════════════════════

RENDERERS = {
    "hero": render_hero,
    "trust": render_trust,
    "features": render_features,
    "price": render_price,
    "detail": render_detail,
    "quality": render_quality,
    "origin": render_origin,
    "spec": render_spec,
    "howto": render_howto,
    "as": render_as,
    "notice": render_notice,
    "delivery": render_delivery,
    "before_after": render_before_after,
    "price_compare": render_price_compare,
    "consult_flow": render_consult_flow,
}

DIVIDER = '\n<div class="pd-divider"></div>\n'


# ══════════════════════════════════════════════════════════════════════════════
# ProductPageBuilder — 메인 클래스
# ══════════════════════════════════════════════════════════════════════════════


class ProductPageBuilder:
    """섹션을 선택해 상품 상세페이지를 조합하는 빌더.

    사용:
        builder = ProductPageBuilder()
        builder.select(["hero", "trust", "features", "spec", "delivery"])
        html = builder.render(product_data)
        builder.save(html)
    """

    def __init__(self):
        self._sections: list[str] = list(DEFAULT_SECTIONS)

    # ── 섹션 선택 ────────────────────────────────────────────────────────────

    def select(self, sections: list[str]) -> ProductPageBuilder:
        """렌더링할 섹션 목록 지정 (순서 유지)."""
        unknown = [s for s in sections if s not in SECTION_REGISTRY]
        if unknown:
            raise ValueError(f"알 수 없는 섹션: {unknown}. 허용: {list(SECTION_REGISTRY)}")
        # 필수 섹션은 항상 포함
        required = [k for k, v in SECTION_REGISTRY.items() if v["required"]]
        merged = list(sections)
        for r in required:
            if r not in merged:
                merged.insert(0 if r == "hero" else len(merged), r)
        self._sections = merged
        return self

    def add(self, section: str) -> ProductPageBuilder:
        """섹션 추가."""
        if section not in self._sections:
            self._sections.append(section)
        return self

    def remove(self, section: str) -> ProductPageBuilder:
        """섹션 제거 (필수 섹션은 제거 불가)."""
        meta = SECTION_REGISTRY.get(section, {})
        if meta.get("required"):
            raise ValueError(f"{section}은 필수 섹션이라 제거할 수 없습니다")
        self._sections = [s for s in self._sections if s != section]
        return self

    def reset(self) -> ProductPageBuilder:
        """기본 섹션으로 초기화."""
        self._sections = list(DEFAULT_SECTIONS)
        return self

    @property
    def sections(self) -> list[str]:
        return list(self._sections)

    # ── 렌더링 ───────────────────────────────────────────────────────────────

    def render(self, data: dict) -> str:
        """선택된 섹션으로 HTML 조합."""
        parts = []
        for i, key in enumerate(self._sections):
            renderer = RENDERERS.get(key)
            if not renderer:
                continue
            html = renderer(data).strip()
            if not html:
                continue
            parts.append(html)
            # 마지막 섹션 제외 구분선 삽입
            if i < len(self._sections) - 1:
                parts.append(DIVIDER)

        body = "\n".join(parts)
        return f'{CSS}\n<div class="pd">\n{body}\n</div>'

    def save(self, html: str, path: str | None = None) -> str:
        """HTML을 파일로 저장 (브라우저 미리보기용 래퍼 포함)."""
        out = Path(path) if path else data_dir() / "smartstore" / "description_preview.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        full = (
            "<!DOCTYPE html><html lang='ko'><head>"
            "<meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>상품 상세 미리보기</title>"
            "<style>body{background:#ebebeb;padding:0;margin:0;}</style>"
            f"</head><body>{html}</body></html>"
        )
        out.write_text(full, encoding="utf-8")
        return str(out)

    # ── 편의 메서드 ──────────────────────────────────────────────────────────

    @staticmethod
    def available_sections() -> dict:
        """사용 가능한 섹션 목록."""
        return {k: v["label"] for k, v in SECTION_REGISTRY.items()}

    @staticmethod
    def render_section(key: str, data: dict) -> str:
        """단일 섹션 렌더링."""
        renderer = RENDERERS.get(key)
        if not renderer:
            raise ValueError(f"알 수 없는 섹션: {key}")
        return renderer(data)
