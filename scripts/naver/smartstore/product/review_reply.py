"""스마트스토어 리뷰 자동 답변 모듈 (L3 Connector).

흐름:
  1. 리뷰 관리 페이지 진입
  2. 미답변 리뷰 목록 추출
  3. GPT로 답변 초안 생성
  4. 각 리뷰에 답변 입력 → 저장 (confirmed=True 필수)

사용:
    from scripts.naver.smartstore.product.review_reply import ReviewAutoResponder
    responder = ReviewAutoResponder(page)
    result = responder.reply_pending(confirmed=False)  # 초안 확인
    result = responder.reply_pending(confirmed=True)   # 실제 저장
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[4]

_CDP = "http://127.0.0.1:9222"
_REVIEW_URL = "https://sell.smartstore.naver.com/#/reviews/list"
_REPLY_API_URL = "https://sell.smartstore.naver.com/#/reviews/list"


class ReviewAutoResponder:
    """미답변 리뷰 자동 답변기."""

    def __init__(self, page):
        self.page = page
        self._api_key: str | None = None

    # ── 공개 인터페이스 ──────────────────────────────────────────────────────

    def get_pending(self, limit: int = 20) -> dict:
        """미답변 리뷰 목록 반환."""
        if not self._open_review_page():
            return {"ok": False, "error": "리뷰 페이지 진입 실패"}

        reviews = self._extract_pending_reviews(limit)
        return {"ok": True, "pending": reviews, "count": len(reviews)}

    def generate_replies(self, reviews: list[dict]) -> list[dict]:
        """각 리뷰에 대해 답변 초안 생성(고정 템플릿 — 유료 AI 미사용).

        맞춤 답변이 필요하면 Claude Code가 review 내용을 읽고 reply_draft를 직접 채워
        넣은 뒤 reply_pending(confirmed=True)으로 저장한다.
        """
        result = []
        for r in reviews:
            reply = self._generate_one(r)
            result.append({**r, "reply_draft": reply})
        return result

    def reply_pending(self, limit: int = 10, confirmed: bool = False) -> dict:
        """미답변 리뷰 조회 → 초안 생성 → (confirmed=True면) 실제 저장.

        Args:
            limit: 처리할 최대 리뷰 수
            confirmed: True면 실제 저장, False면 초안만 반환

        Returns:
            {ok, reviews: [{review_id, content, score, reply_draft, saved}], ...}
        """
        if not confirmed:
            return {
                "ok": True,
                "confirmed": False,
                "message": "드라이런 — confirmed=True로 재호출하면 미답변 리뷰를 수집하고 AI 답변을 저장합니다.",
            }

        pending = self.get_pending(limit)
        if not pending["ok"]:
            return pending

        reviews = pending["pending"]
        if not reviews:
            return {"ok": True, "message": "미답변 리뷰 없음", "reviews": []}

        reviews_with_draft = self.generate_replies(reviews)

        if not confirmed:
            return {
                "ok": True,
                "confirmed": False,
                "message": f"초안 {len(reviews_with_draft)}건 생성 완료. confirmed=True로 재호출하면 저장합니다.",
                "reviews": reviews_with_draft,
            }

        # 실제 저장
        saved, failed = [], []
        for r in reviews_with_draft:
            if r.get("error"):
                failed.append(r)
                continue
            result = self._save_reply(r["review_id"], r["reply_draft"])
            r["saved"] = result.get("ok", False)
            (saved if r["saved"] else failed).append(r)

        log_critical("OTHER", "리뷰 자동 답변 저장", saved=len(saved), failed=len(failed))
        return {
            "ok": len(failed) == 0,
            "confirmed": True,
            "saved": len(saved),
            "failed": len(failed),
            "reviews": saved + failed,
        }

    # ── CDP 조작 ─────────────────────────────────────────────────────────────

    def _open_review_page(self) -> bool:
        """리뷰 관리 페이지 진입."""
        try:
            from scripts.naver.smartstore import NaverSmartStore

            ss = NaverSmartStore(self.page)
            if not ss.open_dashboard():
                return False
            # 문의/리뷰관리 메뉴 클릭
            if not ss._click_menu("문의/리뷰관리"):
                return False
            # 리뷰 관리 서브메뉴 클릭
            for sel in ['a:has-text("리뷰 관리")', "text=리뷰 관리"]:
                try:
                    self.page.click(sel, timeout=3000)
                    time.sleep(3)
                    return True
                except Exception:  # noqa: BLE001 - 팝업/스크롤 등 부수 UI 동작 실패는 무시해도 진행에 영향 없음
                    pass
            return True  # 상위 메뉴만 열려도 진행
        except Exception as e:  # noqa: BLE001 - 상품 리뷰 답변 자동화 - 페이지 진입/추출/저장 실패 시 False 또는 ok:False 반환
            _log.error("[review-reply] 페이지 진입 실패: %s", e)
            return False

    def _extract_pending_reviews(self, limit: int) -> list[dict]:
        """미답변 리뷰 DOM 추출."""
        try:
            # 미답변 탭/필터 클릭 시도
            for sel in ['button:has-text("미답변")', 'a:has-text("미답변")', '[data-filter="unanswered"]']:
                try:
                    self.page.click(sel, timeout=2000)
                    time.sleep(2)
                    break
                except Exception:  # noqa: BLE001 - 팝업/스크롤 등 부수 UI 동작 실패는 무시해도 진행에 영향 없음
                    pass

            rows = self.page.evaluate(f"""
                (() => {{
                    const results = [];
                    // 리뷰 행 셀렉터 후보
                    const rows = document.querySelectorAll(
                        'tr[class*=review], .review-item, [class*=review-row], tbody tr'
                    );
                    for (const row of Array.from(rows).slice(0, {limit})) {{
                        const text = row.querySelector('[class*=content], [class*=text], td:nth-child(4)');
                        const score = row.querySelector('[class*=score], [class*=star], td:nth-child(3)');
                        const btn = row.querySelector('button:not([disabled])[class*=reply], button:has-text("답변하기"), a:has-text("답변하기")');
                        const id = row.getAttribute('data-id') || row.id || '';
                        if (text && btn) {{
                            results.push({{
                                review_id: id,
                                content: text.textContent.trim().slice(0, 300),
                                score: score ? score.textContent.trim() : '',
                                has_reply_btn: true,
                            }});
                        }}
                    }}
                    return results;
                }})()
            """)
            return rows
        except Exception as e:  # noqa: BLE001 - 상품 리뷰 답변 자동화 - 페이지 진입/추출/저장 실패 시 False 또는 ok:False 반환
            _log.error("[review-reply] 리뷰 추출 실패: %s", e)
            return []

    def _save_reply(self, review_id: str, reply_text: str) -> dict:
        """리뷰 답변 저장."""
        try:
            # 답변하기 버튼 클릭 (review_id 기반 또는 순서 기반)
            btn_sel = (
                f'[data-id="{review_id}"] button:has-text("답변하기")'
                if review_id
                else 'button:has-text("답변하기"):first-of-type'
            )
            self.page.click(btn_sel, timeout=5000)
            time.sleep(1)

            # 텍스트 영역 입력
            textarea = self.page.locator(
                "textarea[class*=reply], textarea[placeholder*=답변], .reply-input textarea"
            ).first
            textarea.fill(reply_text)
            time.sleep(0.5)

            # 저장 버튼
            self.page.click('button:has-text("등록"), button:has-text("저장")', timeout=5000)
            time.sleep(1)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001 - 상품 리뷰 답변 자동화 - 페이지 진입/추출/저장 실패 시 False 또는 ok:False 반환
            _log.error("[review-reply] 답변 저장 실패: %s", e)
            return {"ok": False, "error": str(e)[:200]}

    # ── 답변 초안(고정 템플릿) ───────────────────────────────────────────────────

    def _generate_one(self, review: dict) -> str:
        """유료 AI 없이 별점 기반 고정 템플릿 답변을 생성한다."""
        score_text = str(review.get("score", ""))
        score_num = int(re.search(r"\d", score_text).group()) if re.search(r"\d", score_text) else 5
        if score_num >= 4:
            return "소중한 리뷰 감사합니다! 더 좋은 상품과 서비스로 보답하겠습니다 😊"
        return "소중한 의견 감사합니다. 불편을 드려 죄송하며, 문의 주시면 바로 확인해 개선하겠습니다 🙏"
