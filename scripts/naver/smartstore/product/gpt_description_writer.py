"""스마트스토어 상품 상세설명 GPT 자동 작성 모듈 (L3 Connector).

Claude 버전(ai_description_writer.py)과 동일한 S1~S12 HTML 구조를 출력합니다.

기능:
  1. 텍스트 데이터만 제공 → GPT-4o로 상세설명 생성
  2. 이미지 URL/경로 제공 → GPT-4o Vision으로 이미지 분석 후 보강된 설명 생성
  3. 이미지 분석 결과를 상품 데이터에 자동 병합 (색상, 소재, 특징 추출)

사용:
    from scripts.naver.smartstore.product.gpt_description_writer import GptDescriptionWriter

    writer = GptDescriptionWriter()

    # 텍스트만
    result = writer.generate({
        "name": "LED 무드등", "price": 29800, "category": "조명",
        "as_warranty": "1년", "origin": "중국",
    })

    # 이미지 포함 (URL 또는 로컬 경로)
    result = writer.generate(
        {"name": "LED 무드등", "price": 29800, "category": "조명"},
        images=["https://example.com/product.jpg", "C:/images/product2.jpg"],
    )

    if result["ok"]:
        html = result["html"]
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

from scripts.logger import get_logger
from scripts.critical_logger import log_critical

_log = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[4]

# ══════════════════════════════════════════════════════════════════════════════
# 모델 설정
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_MODEL = "gpt-4o-mini"   # 빠름·저렴
QUALITY_MODEL = "gpt-4o"        # 고품질·이미지 분석
API_ENDPOINT  = "https://api.openai.com/v1/chat/completions"
MAX_TOKENS    = 4000

# ══════════════════════════════════════════════════════════════════════════════
# 시스템 프롬프트 (Claude 버전과 동일 기준)
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

IMAGE_ANALYSIS_PROMPT = """이 상품 이미지들을 분석해 아래 항목을 JSON으로 추출해 주세요.
없는 정보는 null로 표기하세요.

{
  "color": "색상",
  "material": "소재/재질",
  "size_estimate": "크기 추정",
  "design_features": ["디자인 특징 1", "디자인 특징 2"],
  "product_condition": "상품 상태(새것/중고)",
  "visible_certifications": ["보이는 인증 마크"],
  "additional_features": ["이미지에서 파악된 추가 특징"],
  "image_quality": "high/medium/low"
}

JSON만 출력하세요."""

USER_PROMPT_TEMPLATE = """다음 상품의 HTML 상세설명을 S1~S12 섹션 구조에 맞게 작성해 주세요.
없는 정보는 (확인 중)으로 표기하세요.

■ 상품명:    {name}
■ 카테고리:  {category}
■ 브랜드:    {brand}
■ 판매가:    {price_str}
■ 타겟:      {target}

핵심 특징 (S3):
{features_str}

가격 경쟁력 (S4):
■ 최저가 보장: {price_guarantee}
■ 가격 근거:   {lowest_price_reason}

품질·내구성 (S6):
■ 내구성: {durability}
■ 인증:   {certifications_str}

원산지·유통 (S7):
■ 원산지:    {origin}
■ 유통경로:  {distributor}

스펙 (S8):
{specs_str}

키워드 (본문 자연 삽입):
{keywords_str}

AS·보증 (S10):
■ 보증기간: {as_warranty}
■ AS방법:   {as_contact}

주의사항 (S11):
{notice_str}

배송·교환·반품 (S12):
{delivery_str}

{image_analysis_section}

<div class="pd">로 시작하는 순수 HTML만 출력하세요.""".strip()


# ══════════════════════════════════════════════════════════════════════════════
# GptDescriptionWriter
# ══════════════════════════════════════════════════════════════════════════════

class GptDescriptionWriter:
    """GPT-4o 기반 상품 상세설명 생성기 (Vision 지원)."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model     = model
        self._api_key: str | None = None

    # ── 공개 인터페이스 ──────────────────────────────────────────────────────

    def generate(self, product: dict, images: list[str] | None = None) -> dict:
        """상품 데이터 + 이미지(선택)로 HTML 상세설명 생성.

        Args:
            product: 상품 데이터 dict
            images:  이미지 URL 목록 또는 로컬 경로 목록 (선택)

        Returns:
            {"ok": bool, "html": str, "model": str,
             "image_analysis": dict|None, "warnings": list}
        """
        from scripts.naver.smartstore.product.ai_description_writer import validate_product_data
        errs = validate_product_data(product)
        hard  = [e for e in errs if e.startswith("[필수]") or e.startswith("[오류]")]
        warns = [e for e in errs if not e.startswith("[필수]") and not e.startswith("[오류]")]
        if hard:
            return {"ok": False, "errors": hard}

        api_key = self._get_api_key()
        if not api_key:
            return {"ok": False, "error": "OPENAI_API_KEY 미설정",
                    "hint": ".env 파일에 OPENAI_API_KEY=sk-... 추가 필요"}

        # 이미지 분석
        image_analysis: dict | None = None
        if images:
            use_model = QUALITY_MODEL  # 이미지가 있으면 항상 vision 모델
            image_analysis = self._analyze_images(api_key, images)
            if image_analysis:
                product = self._merge_image_analysis(product, image_analysis)
                _log.info("[gpt-desc] 이미지 분석 완료: %s", list(image_analysis.keys()))
        else:
            use_model = self.model

        # HTML 생성
        system = SYSTEM_PROMPT
        user   = self._build_user_prompt(product, image_analysis)
        result = self._call_gpt(api_key, system, user, use_model, images)
        if not result["ok"]:
            return result

        html = self._finalize_html(result["text"])
        log_critical("OTHER", "GPT 상세설명 생성",
                     product=product.get("name", "")[:30],
                     model=use_model, chars=len(html), images=len(images or []))
        _log.info("[gpt-desc] 생성 완료: %d자 / 이미지 %d장", len(html), len(images or []))

        return {
            "ok": True,
            "html": html,
            "model": use_model,
            "image_analysis": image_analysis,
            "warnings": warns,
        }

    # ── 이미지 분석 ──────────────────────────────────────────────────────────

    def _analyze_images(self, api_key: str, images: list[str]) -> dict | None:
        """GPT-4o Vision으로 이미지 분석, JSON 반환."""
        content: list[dict] = [{"type": "text", "text": IMAGE_ANALYSIS_PROMPT}]

        for img in images[:4]:  # 최대 4장
            try:
                img_content = self._load_image_content(img)
                if img_content:
                    content.append(img_content)
            except Exception as e:
                _log.debug("[gpt-desc] 이미지 로드 실패 (%s): %s", img[:40], e)

        if len(content) == 1:  # 이미지 없으면 분석 스킵
            return None

        result = self._call_gpt(api_key, "", "", QUALITY_MODEL,
                                _content_override=content)
        if not result["ok"]:
            _log.warning("[gpt-desc] 이미지 분석 실패: %s", result.get("error"))
            return None

        try:
            text = result["text"]
            # JSON 블록 추출
            m = re.search(r"\{[\s\S]+\}", text)
            if m:
                return json.loads(m.group())
        except Exception:
            pass
        return None

    def _load_image_content(self, img: str) -> dict | None:
        """이미지를 GPT content 형식으로 변환."""
        if img.startswith("http://") or img.startswith("https://"):
            return {
                "type": "image_url",
                "image_url": {"url": img, "detail": "low"},
            }

        # 로컬 파일 → base64
        p = Path(img)
        if not p.exists():
            return None
        ext   = p.suffix.lower().lstrip(".")
        mime  = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png",
                 "gif": "gif", "webp": "webp"}.get(ext, "jpeg")
        data  = base64.b64encode(p.read_bytes()).decode()
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/{mime};base64,{data}",
                "detail": "low",
            },
        }

    def _merge_image_analysis(self, product: dict, analysis: dict) -> dict:
        """이미지 분석 결과를 상품 데이터에 병합 (기존 값 우선)."""
        merged = dict(product)
        if analysis.get("color") and not merged.get("color"):
            merged["color"] = analysis["color"]
        if analysis.get("material") and not merged.get("material"):
            merged["material"] = analysis["material"]
        if analysis.get("design_features"):
            existing = merged.get("features", [])
            for feat in analysis["design_features"]:
                if not any(feat in str(f) for f in existing):
                    existing.append({"icon": "🎨", "title": feat, "desc": "(이미지 확인)"})
            merged["features"] = existing[:6]
        if analysis.get("visible_certifications"):
            existing = merged.get("certifications", [])
            merged["certifications"] = list(set(existing + analysis["visible_certifications"]))
        return merged

    # ── 프롬프트 빌드 ─────────────────────────────────────────────────────────

    def _build_user_prompt(self, p: dict, image_analysis: dict | None) -> str:
        features = p.get("features", [])
        features_str = "\n".join(
            f"- {f.get('icon','•')} {f.get('title','')}: {f.get('desc','')}"
            for f in features
        ) if features else "(없음)"

        specs = p.get("specs", {})
        specs_str = "\n".join(f"- {k}: {v}" for k, v in specs.items()) if specs else "(없음)"

        image_section = ""
        if image_analysis:
            image_section = (
                "\n이미지 분석 결과 (참고):\n"
                + json.dumps(image_analysis, ensure_ascii=False, indent=2)
            )

        return USER_PROMPT_TEMPLATE.format(
            name              = p.get("name", ""),
            category          = p.get("category", ""),
            brand             = p.get("brand", ""),
            price_str         = f"{int(p.get('price', 0)):,}원",
            target            = p.get("target", ""),
            features_str      = features_str,
            price_guarantee   = p.get("price_guarantee", "동일 제품 최저가 보장"),
            lowest_price_reason = p.get("lowest_price_reason", ""),
            durability        = p.get("durability", ""),
            certifications_str = ", ".join(p.get("certifications", [])) or "",
            origin            = p.get("origin", ""),
            distributor       = p.get("distributor", ""),
            specs_str         = specs_str,
            keywords_str      = ", ".join(p.get("keywords", [])),
            as_warranty       = p.get("as_warranty", "1년"),
            as_contact        = p.get("as_contact", "스마트스토어 문의"),
            notice_str        = "\n".join(f"- {n}" for n in p.get("notice", [])) or "(없음)",
            delivery_str      = p.get("delivery", "평일 오후 2시 이전 주문 → 당일 출고"),
            image_analysis_section = image_section,
        )

    # ── GPT API 호출 ─────────────────────────────────────────────────────────

    def _call_gpt(self, api_key: str, system: str, user: str, model: str,
                  images: list[str] | None = None,
                  _content_override: list | None = None) -> dict:
        """OpenAI Chat Completions API 호출."""
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})

        if _content_override:
            messages.append({"role": "user", "content": _content_override})
        elif images:
            content: list[dict] = [{"type": "text", "text": user}]
            for img in images[:4]:
                try:
                    img_c = self._load_image_content(img)
                    if img_c:
                        content.append(img_c)
                except Exception:
                    pass
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": user})

        payload = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": MAX_TOKENS,
            "temperature": 0.7,
        }).encode("utf-8")

        req = urllib.request.Request(
            API_ENDPOINT,
            data    = payload,
            method  = "POST",
            headers = {
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            _log.info("[gpt-desc] tokens: prompt=%s completion=%s",
                      usage.get("prompt_tokens"), usage.get("completion_tokens"))
            return {"ok": True, "text": text}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:200]
            return {"ok": False, "error": f"HTTP {e.code}: {body}"}
        except Exception as e:
            return {"ok": False, "error": str(e)[:120]}

    def _finalize_html(self, text: str) -> str:
        """GPT 응답에서 순수 HTML만 추출."""
        # ```html ... ``` 블록 제거
        text = re.sub(r"```html?\s*", "", text)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
        # <div class="pd"> 시작 지점만 추출
        m = re.search(r'<div[^>]*class="[^"]*\bpd\b[^"]*"', text)
        if m:
            text = text[m.start():]
        return text.strip()

    def _get_api_key(self) -> str | None:
        if self._api_key:
            return self._api_key
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            try:
                from dotenv import load_dotenv
                load_dotenv(ROOT / ".env")
                key = os.environ.get("OPENAI_API_KEY", "")
            except Exception:
                pass
        self._api_key = key or None
        return self._api_key


# ── 편의 함수 ─────────────────────────────────────────────────────────────────

def generate_with_gpt(product: dict, images: list[str] | None = None,
                      model: str = DEFAULT_MODEL) -> dict:
    """모듈 레벨 편의 함수."""
    return GptDescriptionWriter(model=model).generate(product, images=images)
