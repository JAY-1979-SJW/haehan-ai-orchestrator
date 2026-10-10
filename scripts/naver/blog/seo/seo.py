"""블로그 SEO 최적화 — 제목/태그/본문 자동 분석.

기능:
  - 제목 SEO 점수 (길이/키워드/광고성)
  - 태그 추천 (네이버 검색 기준)
  - 본문 키워드 밀도 분석
  - 검색 노출 가능성 점수
"""

from __future__ import annotations

import re
from collections import Counter

from playwright.sync_api import Page

from scripts.common.logger import get_logger

_log = get_logger(__name__)


class BlogSEO:
    """블로그 글 SEO 분석/추천."""

    def __init__(self, page: Page):
        self.page = page

    def analyze_title(self, title: str) -> dict:
        """블로그 제목 SEO 분석."""
        issues = []
        score = 100
        length = len(title)

        if length < 15:
            issues.append(f"제목 짧음 ({length}자) — 20~40자 권장")
            score -= 15
        elif length > 60:
            issues.append(f"제목 너무 김 ({length}자)")
            score -= 10

        # 광고성 단어
        ad_words = ["완벽", "최고", "베스트", "꿀팁", "대박"]
        found = [w for w in ad_words if w in title]
        if found:
            issues.append(f"광고성 단어: {found}")
            score -= len(found) * 3

        # 특수문자 과다
        special = len(re.findall(r"[★☆!?]", title))
        if special > 2:
            issues.append(f"특수문자 과다 ({special}개)")
            score -= 10

        return {"ok": True, "title": title, "length": length, "score": max(0, score), "issues": issues}

    def analyze_body(self, body: str, target_keywords: list[str] | None = None) -> dict:
        """본문 키워드 밀도 + 가독성."""
        text = body
        words = re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", text)
        word_count = len(words)
        char_count = len(text)
        paragraph_count = len([p for p in text.split("\n\n") if p.strip()])

        # 키워드 빈도
        counter = Counter(words)
        top_keywords = counter.most_common(10)

        # 타겟 키워드 밀도
        target_density = {}
        if target_keywords:
            for kw in target_keywords:
                cnt = counter.get(kw, 0) + text.lower().count(kw.lower())
                density = (cnt / word_count * 100) if word_count else 0
                target_density[kw] = {"count": cnt, "density_pct": round(density, 2)}

        # 가독성 점수
        score = 100
        warnings = []
        if char_count < 300:
            warnings.append("본문 짧음 (300자 미만)")
            score -= 20
        if paragraph_count < 3:
            warnings.append("단락 적음 (3개 미만)")
            score -= 10

        return {
            "ok": True,
            "char_count": char_count,
            "word_count": word_count,
            "paragraph_count": paragraph_count,
            "top_keywords": top_keywords,
            "target_density": target_density,
            "readability_score": max(0, score),
            "warnings": warnings,
        }

    def suggest_tags(self, body: str, max_tags: int = 7) -> list[str]:
        """본문에서 태그 자동 추천."""
        words = re.findall(r"[가-힣]{2,8}", body)
        counter = Counter(words)
        # 일반 단어 제외
        stopwords = {"이번", "그리고", "하지만", "그래서", "또한", "그러나", "이것"}
        candidates = [w for w, c in counter.most_common(50) if w not in stopwords and len(w) >= 2]
        return candidates[:max_tags]

    def optimize_post(self, title: str, body: str, target_keywords: list[str] | None = None) -> dict:
        """제목+본문+태그 종합 SEO."""
        t_analysis = self.analyze_title(title)
        b_analysis = self.analyze_body(body, target_keywords)
        tags = self.suggest_tags(body, max_tags=7)
        return {
            "ok": True,
            "title_analysis": t_analysis,
            "body_analysis": b_analysis,
            "suggested_tags": tags,
            "overall_score": (t_analysis["score"] + b_analysis["readability_score"]) // 2,
        }

    # ── 추가: 네이버 자동완성 키워드 ──────────────────────────────────

    def autocomplete(self, prefix: str, max_items: int = 10) -> list[str]:
        """네이버 검색창 자동완성 키워드 추출."""
        import time

        url = f"https://search.naver.com/search.naver?query={prefix}"
        try:
            self.page.goto(url, timeout=12000, wait_until="domcontentloaded")
            time.sleep(1.5)
            # 검색창 클릭으로 자동완성 활성화
            try:
                search_box = self.page.locator('input[name="query"]').first
                search_box.click(timeout=3000)
                time.sleep(0.8)
            except Exception:  # noqa: BLE001 - 블로그 SEO 분석 도구(읽기전용 검색어/AI호출) - 실패 시 빈 목록/기본 dict 반환
                pass
            items = self.page.evaluate(
                """
            (limit) => {
                const out = [];
                document.querySelectorAll('.atcmp_text, [class*="autocomplete"] li, [class*="suggest"] li').forEach((el, i) => {
                    if (i >= limit) return;
                    const t = (el.innerText || '').trim();
                    if (t && t.length > 1 && t.length < 40) out.push(t);
                });
                return out;
            }
            """,
                max_items,
            )
            return items
        except Exception as e:  # noqa: BLE001 - 블로그 SEO 분석 도구(읽기전용 검색어/AI호출) - 실패 시 빈 목록/기본 dict 반환
            _log.debug("[seo] autocomplete 실패: %s", e)
            return []

    # ── 연관 검색어 (검색 결과 페이지에서 추출) ─────────────────────

    def related_keywords(self, query: str) -> list[str]:
        """네이버 검색 결과의 연관검색어 추출."""
        import time

        url = f"https://search.naver.com/search.naver?query={query}"
        try:
            self.page.goto(url, timeout=12000, wait_until="domcontentloaded")
            time.sleep(2)
            related = self.page.evaluate("""
            () => {
                const out = [];
                // 연관검색어 영역
                document.querySelectorAll('[class*="related"] a, .related_srch a, .ksb a, [class*="keyword"] a').forEach(a => {
                    const t = (a.innerText || '').trim();
                    if (t && t.length > 1 && t.length < 30) out.push(t);
                });
                return [...new Set(out)].slice(0, 15);
            }
            """)
            return related
        except Exception as e:  # noqa: BLE001 - 블로그 SEO 분석 도구(읽기전용 검색어/AI호출) - 실패 시 빈 목록/기본 dict 반환
            _log.debug("[seo] related_keywords 실패: %s", e)
            return []

    # ── 발행 시간 추천 (시간대별 트래픽 휴리스틱) ────────────────────

    def best_publish_time(self) -> dict:
        """블로그 글 발행 최적 시간 추천 (한국 평균 트래픽 기준)."""
        from datetime import datetime

        now = datetime.now()
        weekday = now.weekday()  # 0=월, 6=일

        # 한국 블로그 평균 트래픽 패턴 (휴리스틱)
        weekday_hours = {
            0: [9, 12, 18, 22],  # 월 — 출근/점심/퇴근/잠자기 전
            1: [9, 12, 18, 22],  # 화
            2: [9, 12, 18, 22],  # 수
            3: [9, 12, 18, 22],  # 목
            4: [9, 12, 17, 21],  # 금 — 퇴근 빠름
            5: [10, 14, 19, 22],  # 토 — 늦은 아침
            6: [10, 14, 19, 22],  # 일
        }
        recommended = weekday_hours.get(weekday, [9, 18, 22])

        return {
            "ok": True,
            "now": now.isoformat(timespec="seconds"),
            "weekday": ["월", "화", "수", "목", "금", "토", "일"][weekday],
            "recommended_hours": recommended,
            "best_today": min(
                (h for h in recommended if h > now.hour),
                default=recommended[0],
            ),
            "note": "한국 블로그 평균 트래픽 기준 휴리스틱. 본인 블로그 통계와 함께 보세요.",
        }

    # ── 이미지 ALT 텍스트 자동 생성 (AI) ─────────────────────────────

    def generate_image_alt(self, image_context: str, product_name: str = "") -> dict:
        """이미지 ALT 텍스트 자동 생성. SEO + 접근성용."""
        try:
            from scripts.naver.automation.integration.ai_responder import AIResponder

            ai = AIResponder()
            system = "이미지 ALT 텍스트 작성 전문가. SEO와 접근성 모두 고려. 50자 이내."
            user = f"""아래 이미지에 대한 ALT 텍스트를 작성해 주세요.

이미지 컨텍스트: {image_context}
관련 상품/주제: {product_name or "미제공"}

요구사항:
- 50자 이내
- 키워드 자연스럽게 포함
- 시각장애인이 이해 가능
"""
            return ai._call(system, user, max_tokens=150)
        except Exception as e:  # noqa: BLE001 - 블로그 SEO 분석 도구(읽기전용 검색어/AI호출) - 실패 시 빈 목록/기본 dict 반환
            return {"ok": False, "error": str(e)[:80]}

    # ── 중복 키워드 페널티 감지 ───────────────────────────────────────

    def check_keyword_stuffing(self, text: str, threshold_pct: float = 5.0) -> dict:
        """키워드 과다 사용(stuffing) 감지. 5% 이상 페널티 위험."""
        import re

        words = re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", text)
        if not words:
            return {"ok": True, "stuffed": [], "total_words": 0}
        from collections import Counter

        counter = Counter(words)
        total = len(words)
        stuffed = []
        for w, c in counter.items():
            density = c / total * 100
            if density >= threshold_pct and c >= 3:
                stuffed.append({"word": w, "count": c, "density_pct": round(density, 2)})
        stuffed.sort(key=lambda x: -x["density_pct"])
        return {
            "ok": True,
            "total_words": total,
            "stuffed_keywords": stuffed[:10],
            "warning": "키워드 밀도 5%+ → 검색 페널티 위험" if stuffed else None,
        }

    # ── 종합 SEO 최적화 워크플로우 ────────────────────────────────────

    def full_optimize(self, title: str, body: str, target_keywords: list[str] | None = None) -> dict:
        """제목/본문/태그/자동완성/연관검색/시간/키워드밀도 종합 분석."""
        result = self.optimize_post(title, body, target_keywords)

        # 추가 분석
        if target_keywords:
            # 첫 번째 키워드로 자동완성 + 연관검색
            first_kw = target_keywords[0]
            result["autocomplete"] = self.autocomplete(first_kw, max_items=10)
            result["related_keywords"] = self.related_keywords(first_kw)

        result["best_publish_time"] = self.best_publish_time()
        result["keyword_stuffing"] = self.check_keyword_stuffing(body)

        # 종합 점수 재계산 (stuffing 페널티 반영)
        base_score = result["overall_score"]
        stuffing_penalty = len(result["keyword_stuffing"]["stuffed_keywords"]) * 5
        result["final_score"] = max(0, base_score - stuffing_penalty)

        log_critical = None  # noqa: F841
        try:
            from scripts.common.critical_logger import log_critical as _lc

            _lc("OTHER", f"SEO 종합 분석: '{title[:30]}'", score=result["final_score"], mode="seo_full")
        except Exception:  # noqa: BLE001 - 블로그 SEO 분석 도구(읽기전용 검색어/AI호출) - 실패 시 빈 목록/기본 dict 반환
            pass

        return result
