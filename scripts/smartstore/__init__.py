"""스마트스토어 통합 패키지 (별도 모듈화).

기존 코드 보존:
  - scripts/naver/smartstore*.py 는 그대로 둠
  - 이 패키지는 그것들을 통합하는 wrapper

사용:
  from scripts.smartstore import SmartStore
  ss = SmartStore(page)
  ss.products.register({...})
  ss.orders.fetch_new()
  ss.inventory.check_low_stock()
  ss.analytics.collect_today()
  ss.csv.import_csv("products.csv")
  ss.ai.reply_review(review)
  ss.seo.optimize({...})
  ss.competitor.track("키워드")
"""
from __future__ import annotations

from playwright.sync_api import Page


class SmartStore:
    """스마트스토어 통합 진입점 — 모든 기능 하나의 객체로 접근."""

    def __init__(self, page: Page):
        self.page = page
        # lazy holders
        self._store = None
        self._products = None
        self._general = None
        self._bulk = None
        self._orders = None
        self._inventory = None
        self._analytics = None
        self._csv = None
        self._ai = None
        self._seo = None
        self._competitor = None
        self._reviews = None
        self._image = None
        self._scheduler = None
        self._notifier = None
        self._error_recovery = None
        self._session = None

    # ── 핵심 (조회/등록) ────────────────────────────────────────────────

    @property
    def store(self):
        """대시보드/메뉴 조회 (NaverSmartStore)."""
        if self._store is None:
            from scripts.naver.smartstore import NaverSmartStore
            self._store = NaverSmartStore(self.page)
        return self._store

    @property
    def products(self):
        """그룹상품 등록."""
        if self._products is None:
            from scripts.naver.smartstore.product import ProductRegister
            self._products = ProductRegister(self.page)
        return self._products

    @property
    def general(self):
        """일반 상품 등록 (가격/재고)."""
        if self._general is None:
            from scripts.naver.smartstore.general_product import GeneralProductRegister
            self._general = GeneralProductRegister(self.page)
        return self._general

    @property
    def bulk(self):
        """일괄 등록."""
        if self._bulk is None:
            from scripts.naver.smartstore.bulk import BulkRegister
            self._bulk = BulkRegister(self.page)
        return self._bulk

    # ── 자동화 ─────────────────────────────────────────────────────────

    @property
    def orders(self):
        """주문 자동 처리."""
        if self._orders is None:
            from scripts.naver.automation.order_automation import OrderAutomation
            self._orders = OrderAutomation(self.page)
        return self._orders

    @property
    def inventory(self):
        """재고 모니터링."""
        if self._inventory is None:
            from scripts.naver.automation.inventory_monitor import InventoryMonitor
            self._inventory = InventoryMonitor(self.page)
        return self._inventory

    @property
    def analytics(self):
        """매출/방문 분석 대시보드."""
        if self._analytics is None:
            from scripts.naver.automation.analytics_dashboard import AnalyticsDashboard
            self._analytics = AnalyticsDashboard(self.page)
        return self._analytics

    @property
    def csv(self):
        """CSV/Excel 일괄 가져오기."""
        if self._csv is None:
            from scripts.naver.automation.csv_import import CSVImporter
            self._csv = CSVImporter(self.page)
        return self._csv

    @property
    def reviews(self):
        """리뷰 자동 응답."""
        if self._reviews is None:
            from scripts.naver.automation.review_automation import ReviewAutoResponder
            self._reviews = ReviewAutoResponder(self.page)
        return self._reviews

    @property
    def ai(self):
        """AI 기반 응답/생성 (Claude/OpenAI)."""
        if self._ai is None:
            from scripts.naver.automation.ai_responder import AIResponder
            self._ai = AIResponder()
        return self._ai

    @property
    def seo(self):
        """SEO 최적화."""
        if self._seo is None:
            from scripts.naver.automation.seo_optimizer import SEOOptimizer
            self._seo = SEOOptimizer(self.page)
        return self._seo

    @property
    def competitor(self):
        """경쟁사 분석."""
        if self._competitor is None:
            from scripts.naver.automation.competitor_analysis import CompetitorAnalysis
            self._competitor = CompetitorAnalysis(self.page)
        return self._competitor

    @property
    def image(self):
        """이미지 일괄 처리."""
        if self._image is None:
            from scripts.naver.automation.image_processor import ImageProcessor
            self._image = ImageProcessor()
        return self._image

    @property
    def notifier(self):
        """다중 채널 알림."""
        if self._notifier is None:
            from scripts.naver.automation.notification_hub import NotificationHub
            self._notifier = NotificationHub(self.page)
        return self._notifier

    @property
    def error_recovery(self):
        """에러 자동 복구."""
        if self._error_recovery is None:
            from scripts.naver.automation.error_recovery import ErrorRecovery
            self._error_recovery = ErrorRecovery(self.page)
        return self._error_recovery

    @property
    def scheduler(self):
        """정기 실행 스케줄러."""
        if self._scheduler is None:
            from scripts.naver.automation.scheduler import Scheduler
            self._scheduler = Scheduler()
        return self._scheduler

    @property
    def session(self):
        """세션 자동 관리."""
        if self._session is None:
            from scripts.naver.automation.session_manager import SessionManager
            self._session = SessionManager(self.page)
        return self._session


__all__ = ["SmartStore"]
