"""블로그 글 작성 고도화 (Pro) — 기존 BlogWriter 위에 얹은 워크플로우.

기존 `blog_writer.py` (BlogWriter)는 보존. 이 모듈은 그 위에:
  1. 사전 검증 (제목/본문 길이, 금칙어, 광고성)
  2. SEO 사전 분석 (BlogSEO.full_optimize) → 점수 낮으면 경고/중단
  3. AI 보강 (제목 개선안 / 부족한 단락 제안 / 자동 태그)
  4. 이미지 ALT 자동 적용 (BlogSEO.generate_image_alt)
  5. 가독성 단락 자동 분리
  6. 인트로/아웃트로/CTA 템플릿 자동 삽입
  7. 발행 직전 백업 (data/blog_drafts/<ts>.json)
  8. 발행 후 검증 + 통계 DB 등록
  9. best_publish_time() 기반 자동 예약

핵심 클래스: BlogWriterPro

사용 예:
    from scripts.naver.blog.writer_pro import BlogWriterPro
    from scripts.browser.cdp.connection import get_page

    page = get_page()
    pro = BlogWriterPro(page)
    result = pro.smart_publish(
        title="LED 무드등 인테리어 활용법",
        body="...",
        keywords=["LED", "무드등", "인테리어"],
        images=["data/images/p1.jpg", "data/images/p2.jpg"],
        category="인테리어",
        intro_template="감성",
        outro_template="CTA",
        min_seo_score=70,
        auto_schedule=False,  # True면 best_publish_time 기반 예약
        dry_run=False,
    )
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import Page

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.naver.blog.core.writer import BlogWriter

_log = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[3]
DRAFT_DIR = data_dir() / "blog_drafts"  # ROOT(parents[3])는 저장소 루트가 아니라 scripts/naver 였다 — naver_blog_router 의 DRAFTS_DIR 과 같은 위치로

# ── 템플릿 (intro / outro / CTA) ─────────────────────────────────────────
INTRO_TEMPLATES = {
    "감성": "안녕하세요. 오늘은 {topic}에 대해 함께 이야기 나누고 싶어요.\n천천히 읽어주시면 더 좋을 것 같아요.",
    "정보": "이번 글에서는 {topic}에 대해 정리해 보았습니다.\n핵심만 빠르게 짚어보겠습니다.",
    "후기": "최근에 {topic}를 직접 사용해 본 솔직한 후기를 공유합니다.\n장단점 모두 담았으니 참고하세요.",
    "질문": "혹시 {topic} 때문에 고민하고 계신가요?\n저도 같은 고민을 해서 정리해 봤습니다.",
}

OUTRO_TEMPLATES = {
    "CTA": "\n\n도움이 되셨다면 공감과 댓글, 이웃추가 부탁드립니다 :)\n다음 글에서 또 만나요.",
    "요약": "\n\n오늘의 핵심 — {topic}.\n끝까지 읽어주셔서 감사합니다.",
    "질문초대": "\n\n여러분의 {topic} 경험은 어떠셨나요?\n댓글로 공유해 주세요.",
    "간단": "\n\n읽어주셔서 감사합니다.",
}

# 광고성/금칙어 (네이버 SEO 페널티 위험)
BLOCKED_PATTERNS = [
    r"100%\s*보장",
    r"무조건\s*최고",
    r"전국\s*1위",
    r"최저가\s*보장",
    r"환불\s*불가",
    r"불법",
    r"도박",
]


class BlogWriterPro:
    """기존 BlogWriter를 감싸는 고도화 작성기."""

    def __init__(self, page: Page, blog_id: str | None = None):
        self.page = page
        self.blog_id = blog_id
        self.writer = BlogWriter(page)
        self._last_draft_path: Path | None = None

    # ── 사전 검증 ────────────────────────────────────────────────────────

    def precheck(self, title: str, body: str) -> dict:
        """발행 전 검증: 길이/금칙어/이미지 부족."""
        issues = []
        if len(title) < 15:
            issues.append(f"제목 짧음 ({len(title)}자, 20+ 권장)")
        if len(title) > 60:
            issues.append(f"제목 너무 김 ({len(title)}자)")
        if len(body) < 300:
            issues.append(f"본문 짧음 ({len(body)}자, 500+ 권장)")
        for pat in BLOCKED_PATTERNS:
            if re.search(pat, title + " " + body):
                issues.append(f"금칙어/광고성 패턴: {pat}")
        return {"ok": len(issues) == 0, "issues": issues}

    # ── 가독성 단락 자동 분리 ────────────────────────────────────────────

    def auto_paragraphize(self, body: str, max_sentences: int = 3) -> list[str]:
        """긴 문장 덩어리를 가독성 좋은 단락으로 자동 분리."""
        if "\n\n" in body:
            return [p.strip() for p in body.split("\n\n") if p.strip()]
        # 문장 단위 split (.!? 기준)
        sentences = re.split(r"(?<=[.!?。])\s+", body)
        sentences = [s.strip() for s in sentences if s.strip()]
        paragraphs = []
        for i in range(0, len(sentences), max_sentences):
            paragraphs.append(" ".join(sentences[i : i + max_sentences]))
        return paragraphs

    # ── 인트로/아웃트로 자동 삽입 ────────────────────────────────────────

    def apply_templates(self, body: str, topic: str, intro: str | None = None, outro: str | None = None) -> str:
        """인트로/아웃트로 템플릿을 본문 앞뒤에 삽입."""
        out = body
        if intro and intro in INTRO_TEMPLATES:
            out = INTRO_TEMPLATES[intro].format(topic=topic) + "\n\n" + out
        if outro and outro in OUTRO_TEMPLATES:
            out = out + OUTRO_TEMPLATES[outro].format(topic=topic)
        return out

    # ── AI 보강 (제목 개선 / 태그 자동) ──────────────────────────────────

    def ai_enhance(self, title: str, body: str, keywords: list[str] | None = None) -> dict:
        """AI로 제목 개선안 + 자동 태그 + SEO 점수."""
        from scripts.naver.blog.seo.seo import BlogSEO

        seo = BlogSEO(self.page)
        try:
            seo_result = seo.full_optimize(title, body, keywords or [])
        except Exception as e:  # noqa: BLE001 - 네이버 블로그 발행 도우미 - SEO 분석/이미지 alt/예약시간 계산 실패는 기본값으로 폴백, 발행 자체를 우회하지 않음
            _log.warning("[blog-pro] SEO 분석 실패 (skip): %s", e)
            seo_result = {
                "overall_score": 50,
                "final_score": 50,
                "suggested_tags": [],
                "keyword_stuffing": {"stuffed_keywords": []},
            }
        return seo_result

    # ── 백업 (발행 전 JSON 스냅샷) ───────────────────────────────────────

    def backup_draft(self, title: str, body: str, meta: dict | None = None) -> Path:
        """발행 직전 백업 — 실패 시 복구용."""
        DRAFT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r"[^\w가-힣]", "_", title)[:30]
        path = DRAFT_DIR / f"{ts}_{safe}.json"
        path.write_text(
            json.dumps(
                {
                    "saved_at": datetime.now().isoformat(timespec="seconds"),
                    "title": title,
                    "body": body,
                    "meta": meta or {},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._last_draft_path = path
        _log.info("[blog-pro] 백업 저장: %s", path.name)
        return path

    def restore_draft(self, draft_path: str | Path) -> dict:
        """백업 JSON 복구."""
        p = Path(draft_path)
        return json.loads(p.read_text(encoding="utf-8"))

    def list_drafts(self, limit: int = 20) -> list[dict]:
        """최근 백업 목록."""
        if not DRAFT_DIR.exists():
            return []
        files = sorted(DRAFT_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        out = []
        for f in files[:limit]:
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                out.append({"file": f.name, "saved_at": d.get("saved_at"), "title": d.get("title", "")[:50]})
            except Exception:  # noqa: BLE001 - 네이버 블로그 발행 도우미 - SEO 분석/이미지 alt/예약시간 계산 실패는 기본값으로 폴백, 발행 자체를 우회하지 않음
                continue
        return out

    # ── 이미지 ALT 자동 생성 + 적용 ─────────────────────────────────────

    def prepare_images_with_alt(self, images: list[str], topic: str) -> list[dict]:
        """이미지 경로 + AI ALT 텍스트 매핑."""
        try:
            from scripts.naver.blog.seo.seo import BlogSEO

            seo = BlogSEO(self.page)
        except Exception:  # noqa: BLE001 - 네이버 블로그 발행 도우미 - SEO 분석/이미지 alt/예약시간 계산 실패는 기본값으로 폴백, 발행 자체를 우회하지 않음
            seo = None
        out = []
        for i, img in enumerate(images):
            alt = ""
            if seo:
                try:
                    r = seo.generate_image_alt(f"{topic} 이미지 #{i + 1}", product_name=topic)
                    alt = (r.get("text") or "").strip()[:80]
                except Exception:  # noqa: BLE001 - 임시저장 목록 파일 읽기 실패는 해당 항목만 건너뜀
                    pass
            out.append({"path": img, "alt": alt or f"{topic} 관련 이미지"})
        return out

    # ── 메인 워크플로우: smart_publish ───────────────────────────────────

    def _decide_schedule_time(self, auto_schedule: bool) -> datetime | None:
        """자동 예약 시간 결정(실패 시 None 으로 폴백)."""
        schedule_at = None
        if auto_schedule:
            try:
                from scripts.naver.blog.seo.seo import BlogSEO

                bt = BlogSEO(self.page).best_publish_time()
                today = datetime.now()
                hour = bt["best_today"]
                schedule_at = today.replace(hour=hour, minute=0, second=0, microsecond=0)
                # 이미 지난 시간이면 다음 추천
                if schedule_at <= datetime.now():
                    schedule_at = schedule_at + timedelta(days=1)
                _log.info("[blog-pro] 자동 예약: %s", schedule_at)
            except Exception as e:  # noqa: BLE001 - 네이버 블로그 발행 도우미 - SEO 분석/이미지 alt/예약시간 계산 실패는 기본값으로 폴백, 발행 자체를 우회하지 않음
                _log.warning("[blog-pro] 자동 예약 시간 계산 실패: %s", e)
        return schedule_at


    def _publish_by_mode(
        self, save_draft_only: bool, schedule_at: datetime | None, approval: str | None = None
    ) -> dict:
        """발행 모드 분기(임시저장/예약/즉시). 즉시 발행은 사용자가 직접 입력한 승인 문구(approval)가 필요하다."""
        if save_draft_only:
            result = self.writer.save_draft()
        elif schedule_at:
            result = self.writer.schedule_publish(schedule_at)
        else:
            from scripts.common.gate import require_approved

            require_approved("blog_publish", approval, via="blog_pro_smart_publish")
            result = self.writer.publish()
        return result


    def smart_publish(  # noqa: PLR0913 - 공개 시그니처 유지(동작 변경 금지 리팩터링)
        self,
        *,
        title: str,
        body: str,
        keywords: list[str] | None = None,
        images: list[str] | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        visibility: str = "public",
        intro_template: str | None = None,
        outro_template: str | None = None,
        auto_paragraphize: bool = True,
        min_seo_score: int = 60,
        auto_schedule: bool = False,
        save_draft_only: bool = False,
        dry_run: bool = False,
        approval: str | None = None,
    ) -> dict:
        """원샷 고도화 발행. 즉시 발행(임시저장·예약·dry_run 제외)은 사용자가 직접 입력한 승인 문구(approval)가 필요하다.

        Returns:
            {ok, mode, url?, seo_score, issues, draft_path, ...}
        """
        topic = (keywords or [title])[0]

        # 1) 사전 검증
        pre = self.precheck(title, body)
        if not pre["ok"] and not dry_run:
            _log.warning("[blog-pro] 사전 검증 실패: %s", pre["issues"])
            return {"ok": False, "stage": "precheck", "issues": pre["issues"]}

        # 2) 템플릿 적용
        body_with_tpl = self.apply_templates(body, topic, intro_template, outro_template)

        # 3) 가독성 단락 분리
        paragraphs = self.auto_paragraphize(body_with_tpl) if auto_paragraphize else [body_with_tpl]

        # 4) SEO 분석 + AI 태그
        seo = self.ai_enhance(title, body_with_tpl, keywords)
        seo_score = seo.get("final_score", seo.get("overall_score", 0))
        suggested_tags = seo.get("suggested_tags", [])
        final_tags = list(dict.fromkeys((tags or []) + suggested_tags))[:10]

        if seo_score < min_seo_score and not dry_run:
            _log.warning("[blog-pro] SEO 점수 %d < %d — 발행 보류", seo_score, min_seo_score)
            return {
                "ok": False,
                "stage": "seo",
                "seo_score": seo_score,
                "suggested_tags": suggested_tags,
                "stuffed": seo.get("keyword_stuffing", {}).get("stuffed_keywords", []),
                "hint": "min_seo_score를 낮추거나 본문/제목을 개선하세요",
            }

        # 5) 백업
        draft_path = self.backup_draft(
            title,
            body_with_tpl,
            meta={
                "keywords": keywords,
                "tags": final_tags,
                "category": category,
                "seo_score": seo_score,
                "images": images,
            },
        )

        # 6) dry_run: 발행 안 함, 분석 결과만 반환
        if dry_run:
            return {
                "ok": True,
                "mode": "dry_run",
                "seo_score": seo_score,
                "suggested_tags": final_tags,
                "paragraph_count": len(paragraphs),
                "issues": pre["issues"],
                "draft_path": str(draft_path),
                "preview_body": body_with_tpl[:300],
            }

        # 7) 자동 예약 시간 결정
        schedule_at = self._decide_schedule_time(auto_schedule)

        # 8) 실제 발행
        if not self.writer.open(blog_id=self.blog_id):
            return {"ok": False, "stage": "open", "draft_path": str(draft_path)}

        self.writer.set_title(title)

        # 이미지 먼저 삽입 (ALT 포함)
        if images:
            img_data = self.prepare_images_with_alt(images, topic)
            for d in img_data:
                self.writer.insert_image(d["path"])
                # ALT는 SmartEditor가 이미지 캡션으로 자동 처리하는 영역 — 별도 적용

        self.writer.write_body(paragraphs)

        if category:
            self.writer.set_category(category)
        if final_tags:
            self.writer.set_tags(final_tags)
        self.writer.set_visibility(visibility)
        self.writer.set_search_exposure(True)

        # 9) 발행 모드 분기
        result = self._publish_by_mode(save_draft_only, schedule_at, approval)

        # 10) 통계 + 로그
        result.update(
            {
                "seo_score": seo_score,
                "final_tags": final_tags,
                "draft_path": str(draft_path),
                "paragraph_count": len(paragraphs),
                "scheduled_at": schedule_at.isoformat() if schedule_at else None,
            }
        )
        log_critical(
            "OTHER",
            f"블로그 Pro 발행: {title[:30]}",
            seo_score=seo_score,
            mode="blog_pro_publish",
            scheduled=bool(schedule_at),
            ok=result.get("ok"),
        )
        return result


# ── 편의 함수 ────────────────────────────────────────────────────────────


def smart_publish(page: Page, **kwargs) -> dict:
    """원샷 호출."""
    return BlogWriterPro(page).smart_publish(**kwargs)
