"""CDP 팝업 통합 관리 모듈 (L4 Browser Engine).

기능:
  1. 팝업 차단 해제 — Chrome 팝업 차단 정책을 CDP permissions API로 해제
  2. 실시간 감지   — 새 탭/창 생성 이벤트 즉시 포착 (on_page 리스너)
  3. 레이어 스캔   — 현재 페이지 모달/레이어/dialog 팝업 스캔
  4. 자동 처리     — 감지된 팝업 종류별 자동 닫기 또는 핸들러 호출

사용:
    from scripts.naver.smartstore.navigation.cdp_popup_manager import CdpPopupManager

    mgr = CdpPopupManager()

    # 1) CDP 컨텍스트 팝업 차단 해제 + 이벤트 감시 등록
    mgr.attach(context)

    # 2) 현재 페이지 레이어 팝업 스캔 후 자동 닫기
    result = mgr.handle_page(page)

    # 3) 전체 현황 조회
    status = mgr.status()

    # 4) 감시 해제
    mgr.detach()

API 엔드포인트:
    POST /api/v1/smartstore/popup/unblock   — 차단 해제
    POST /api/v1/smartstore/popup/scan      — 현재 페이지 스캔
    POST /api/v1/smartstore/popup/handle    — 스캔 + 자동 닫기
    GET  /api/v1/smartstore/popup/status    — 감지 이력 조회
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable
from typing import ClassVar

from scripts.common.logger import get_logger

# ── 백그라운드 폴러 싱글톤 ────────────────────────────────────────────────────
_poller: CdpPopupPoller | None = None

_log = get_logger(__name__)

# ── 팝업 창 판정 기준 URL 패턴 ────────────────────────────────────────────────
POPUP_URL_PATTERNS = [
    "popup",
    "pop_",
    "/pop/",
    "modal",
    "layer",
    "alert",
    "confirm",
    "dialog",
]

# ── 레이어 팝업 셀렉터 (우선순위 순) ─────────────────────────────────────────
# 참고: [class*='alert']는 오탐 많음 — 제거, role=dialog / seller-layer-modal 우선
LAYER_POPUP_SELS = [
    # ── 셀러센터 전용 모달 ────────────────────────────────────────────────────
    ".seller-layer-modal",
    ".seller-notice",
    # ── ARIA 기반 (표준 모달) ─────────────────────────────────────────────────
    "[role='dialog']",
    "[aria-modal='true']",
    # ── Bootstrap 모달 활성 상태 ──────────────────────────────────────────────
    ".modal.fade.in",
    ".modal.in",
    # ── 카테고리 선택 레이어 ──────────────────────────────────────────────────
    ".category-layer",
    "[class*='category-popup']",
    "[class*='categoryLayer']",
    # ── 로그인 만료 / 세션 팝업 ───────────────────────────────────────────────
    ".login-layer",
    "[class*='login-popup']",
    "[class*='session-expire']",
    # ── 이미지 업로드 팝업 ────────────────────────────────────────────────────
    "[class*='image-upload-layer']",
    "[class*='imageUpload'][role='dialog']",
    # ── 스마트에디터 팝업 ─────────────────────────────────────────────────────
    ".se2_dialog",
    "[class*='se-popup']",
    # ── 토스트/스낵바 (show 상태만) ───────────────────────────────────────────
    "[class*='toast'][class*='show']",
    "[class*='snackbar'][class*='show']",
    # ── 기타 레이어 팝업 클래스 ───────────────────────────────────────────────
    "[class*='layer-popup']",
    "[class*='layerPopup']",
    "[class*='pop-wrap']",
]

# ── 인라인 배너 셀렉터 (임시저장 불러오기 등) ────────────────────────────────
BANNER_SELS = [
    ".alert.seller-alert",  # 임시저장 불러오기 배너
    ".seller-alert",
    "[class*='seller-alert']",
]

# 배너 처리 액션 정의: 텍스트 → 클릭할 버튼 텍스트 or 행동
BANNER_ACTIONS = {
    "임시저장 된 내용": "dismiss",  # 불러오기 무시 (닫기)
    "임시저장된 내용": "dismiss",
    "불러오시겠습니까": "dismiss",
}

# ── 오탐 제외 클래스 키워드 ────────────────────────────────────────────────────
EXCLUDE_CLASSES = [
    "navbar",
    "side-nav",
    "dock-nav",
    "backdrop",
    "seller-top-nav",
    "seller-side-bar",
    # alert 배너류 (팝업이 아닌 인라인 안내)
    "alert-info",
    "alert-warning",
    "alert-danger",
    "alert-success",
    "ng-hide",
]

# ── 승인(confirm) 버튼 셀렉터 — 확인/저장 버튼 우선 ─────────────────────────
CONFIRM_BTN_SELS = [
    "button.btn-primary",  # 셀러센터 주요 액션 버튼 (확인, 저장 등)
    "button.btn-ok",
    "button[class*='confirm']",
    "button[class*='ok']",
]

CONFIRM_TEXTS = ["확인", "저장", "완료", "OK", "동의", "적용", "선택"]

# ── 닫기 버튼 셀렉터 — × 닫기 버튼 ──────────────────────────────────────────
CLOSE_BTN_SELS = [
    "button.close",
    "button[aria-label*='닫기']",
    "button[title*='닫기']",
    ".btn-close",
]

CLOSE_TEXTS = ["닫기", "취소", "×", "✕", "X"]

# ── 팝업 처리 레벨 ────────────────────────────────────────────────────────────
# "auto"   — 자동 처리 (단순 완료 팝업, 사용자 개입 불필요)
# "review" — AI 요약 후 알림 패널 대기 (사용자 확인 후 처리)
# "confirm"— 바로 확인 버튼 클릭
# "close"  — × 닫기 버튼 클릭

POPUP_LEVEL_MAP = [
    # ── 자동 처리 (단순 완료) ─────────────────────────────────────────────
    ("임시저장 완료", "auto"),
    ("저장 완료", "auto"),
    ("등록 완료", "auto"),
    ("수정 완료", "auto"),
    ("처리 완료", "auto"),
    ("발송 완료", "auto"),
    ("설정 완료", "auto"),
    ("업로드 완료", "auto"),
    ("변경 완료", "auto"),
    ("삭제 완료", "auto"),
    # ── 사용자 검토 필요 (AI 요약 → 알림 패널) ───────────────────────────
    ("공지사항", "review"),
    ("공지", "review"),
    ("약관", "review"),
    ("정책", "review"),
    ("업데이트", "review"),
    ("변경 예정", "review"),
    ("중요", "review"),
    ("주의", "review"),
    ("경고", "review"),
    ("제한", "review"),
    ("정지", "review"),
    ("삭제하시겠습니까", "review"),  # 삭제 확인은 사용자가 직접
    ("진행하시겠습니까", "review"),
    # ── 오류 계열 → 닫기 후 알림 ────────────────────────────────────────
    ("오류", "review"),
    ("실패", "review"),
    ("error", "review"),
    ("denied", "review"),
]

# 하위 호환 (기존 코드 참조)
POPUP_ACTION_MAP = [(k, "confirm" if v == "auto" else "close") for k, v in POPUP_LEVEL_MAP]


class PopupEvent:
    """감지된 팝업 이벤트 기록."""

    def __init__(self, kind: str, detail: dict):
        self.kind = kind  # "new_tab" | "new_window" | "layer" | "dialog"
        self.detail = detail
        self.ts = time.strftime("%H:%M:%S")
        self.handled = False

    def to_dict(self) -> dict:
        return {"kind": self.kind, "ts": self.ts, "handled": self.handled, **self.detail}


class CdpPopupManager:
    """CDP 컨텍스트 수준 팝업 통합 관리자."""

    def __init__(self):
        self._context = None
        self._events: list[PopupEvent] = []
        self._lock = threading.Lock()
        self._watching = False
        self._custom_handler: Callable | None = None

    # ══════════════════════════════════════════════════════════════════════════
    # 1. CDP 팝업 차단 해제
    # ══════════════════════════════════════════════════════════════════════════

    def unblock(self, context, origin: str = "*") -> dict:
        """Chrome 팝업 차단 정책 해제.

        Args:
            context: Playwright BrowserContext
            origin:  대상 오리진 ("*" = 모두, 또는 "https://sell.smartstore.naver.com")

        Returns:
            {"ok": bool, "origin": str, "method": str}
        """
        methods_tried = []

        # ── 방법 1: grant_permissions (Playwright 표준) ────────────────────
        try:
            context.grant_permissions(
                ["notifications"],
                origin=origin if origin != "*" else None,
            )
            methods_tried.append("grant_permissions:notifications")
        except Exception as e:  # noqa: BLE001 - 팝업/배너 감지·해제 — Playwright 요소 조회 실패 종류가 다양해 일괄 로그 후 계속 진행, 실제 업무 액션(결제·DB쓰기) 아닌 UI 노이즈 제거 전용(2026-09-28 검토)
            _log.debug("[popup-mgr] grant_permissions 실패: %s", e)

        # ── 방법 2: CDP Browser.setPermission ─────────────────────────────
        try:
            cdp = context.new_cdp_session(context.pages[0])
            cdp.send(
                "Browser.setPermission",
                {
                    "permission": {"name": "notifications"},
                    "setting": "granted",
                    "origin": origin if origin != "*" else "https://sell.smartstore.naver.com",
                },
            )
            methods_tried.append("cdp:Browser.setPermission:notifications")
            cdp.detach()
        except Exception as e:  # noqa: BLE001 - 팝업/배너 감지·해제 — Playwright 요소 조회 실패 종류가 다양해 일괄 로그 후 계속 진행, 실제 업무 액션(결제·DB쓰기) 아닌 UI 노이즈 제거 전용(2026-09-28 검토)
            _log.debug("[popup-mgr] CDP setPermission 실패: %s", e)

        # ── 방법 3: JS로 window.open 차단 우회 주입 ──────────────────────
        try:
            context.add_init_script("""
            (() => {
                // window.open 차단 시 자동 재시도
                const _orig = window.open.bind(window);
                window.open = function(url, name, features) {
                    try {
                        const w = _orig(url, name, features);
                        if (!w) {
                            // 차단됨 — 동일 탭에서 열기
                            console.warn('[popup-mgr] window.open blocked, fallback:', url);
                            window.location.href = url;
                        }
                        return w;
                    } catch(e) {
                        console.warn('[popup-mgr] window.open error:', e, url);
                        return null;
                    }
                };
            })();
            """)
            methods_tried.append("js:window.open_override")
        except Exception as e:  # noqa: BLE001 - 팝업/배너 감지·해제 — Playwright 요소 조회 실패 종류가 다양해 일괄 로그 후 계속 진행, 실제 업무 액션(결제·DB쓰기) 아닌 UI 노이즈 제거 전용(2026-09-28 검토)
            _log.debug("[popup-mgr] JS 주입 실패: %s", e)

        _log.info("[popup-mgr] 팝업 차단 해제: origin=%s methods=%s", origin, methods_tried)
        return {"ok": True, "origin": origin, "methods": methods_tried}

    # ══════════════════════════════════════════════════════════════════════════
    # 2. 실시간 감시 등록
    # ══════════════════════════════════════════════════════════════════════════

    def attach(self, context, on_popup: Callable | None = None) -> dict:
        """CDP 컨텍스트에 팝업 감시 리스너 등록.

        Args:
            context:   Playwright BrowserContext
            on_popup:  팝업 감지 시 호출할 콜백 (선택) — (PopupEvent) -> None
        """
        self._context = context
        self._custom_handler = on_popup
        self._watching = True

        # 새 페이지(탭/창) 생성 이벤트
        context.on("page", self._on_new_page)

        # 차단 해제
        unblock_result = self.unblock(context)

        _log.info("[popup-mgr] 감시 등록 완료")
        return {"ok": True, "watching": True, "unblock": unblock_result}

    def detach(self) -> dict:
        """감시 리스너 해제."""
        if self._context and self._watching:
            with contextlib.suppress(Exception):
                self._context.remove_listener("page", self._on_new_page)
        self._watching = False
        _log.info("[popup-mgr] 감시 해제")
        return {"ok": True, "watching": False}

    def _on_new_page(self, page) -> None:
        """새 탭/창 생성 시 호출 (이벤트 핸들러)."""
        url = page.url or "(blank)"
        kind = "new_window" if _is_popup_url(url) else "new_tab"
        ev = PopupEvent(kind, {"url": url})

        with self._lock:
            self._events.append(ev)

        _log.info("[popup-mgr] 새 %s 감지: %s", kind, url[:80])

        # 자동 처리: 팝업 창이면 내용 확인 후 닫기
        if kind == "new_window":
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
                content = page.inner_text("body", timeout=3000)[:200]
                ev.detail["content"] = content
                _log.info("[popup-mgr] 팝업 창 내용: %s", content[:80])
                # 팝업 창은 자동으로 닫지 않음 — 사용자 확인 후 닫기
                ev.handled = False
            except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
                pass
        elif kind == "new_tab":
            ev.handled = True  # 새 일반 탭은 자동 처리 없음

        # 커스텀 핸들러 호출
        if self._custom_handler:
            try:
                self._custom_handler(ev)
            except Exception as e:  # noqa: BLE001 - 팝업/배너 감지·해제 — Playwright 요소 조회 실패 종류가 다양해 일괄 로그 후 계속 진행, 실제 업무 액션(결제·DB쓰기) 아닌 UI 노이즈 제거 전용(2026-09-28 검토)
                _log.debug("[popup-mgr] 커스텀 핸들러 오류: %s", e)

    # ══════════════════════════════════════════════════════════════════════════
    # 3. 레이어 팝업 스캔 + 처리
    # ══════════════════════════════════════════════════════════════════════════

    def scan_page(self, page) -> dict:
        """현재 페이지의 모든 레이어 팝업 스캔 (중복 제거 포함).

        Returns:
            {"found": int, "popups": [{"selector", "text", "has_close_btn"}]}
        """
        found = []
        seen_outer_html_keys: set[str] = set()

        for sel in LAYER_POPUP_SELS:
            try:
                els = page.locator(sel)
                n = els.count()
                for i in range(min(n, 5)):
                    el = els.nth(i)
                    try:
                        entry = _scan_one_popup(page, sel, i, el, seen_outer_html_keys)
                        if entry is not None:
                            found.append(entry)
                    except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
                        pass
            except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
                pass

        return {"found": len(found), "popups": found}

    # ── 보류 팝업 큐 (사용자 확인 대기) ──────────────────────────────────────
    # {id: {popup_data, page_ref, action_fn}}
    # ClassVar 명시(2026-09-29 defect_index): CdpPopupManager() 가 여러 곳(최소 9곳)에서
    # 그때그때 새로 생성되는데 이 딕셔너리는 클래스 속성이라 그 인스턴스들이 전부 같은
    # 큐를 공유한다 — 실제 사용자에게는 브라우저 팝업이 항상 하나뿐이라 현재는 문제없이
    # 동작 중으로 보이나, 인스턴스별로 독립돼야 하는지는 별도 확인 필요(동작은 바꾸지 않고
    # 현재 상태를 타입으로만 명시 — RUF012).
    _pending: ClassVar[dict] = {}

    def handle_page(self, page, auto_confirm: bool = True) -> dict:
        """현재 페이지 팝업 스캔 + 자동 처리.

        팝업 텍스트를 분석해 적절한 버튼(확인/닫기)을 자동 클릭합니다.

        Returns:
            {"closed": int, "page_clean": bool, "popups_before": int,
             "approved": [...], "dismissed": [...]}
        """
        # ── 0. 인라인 배너 처리 ──────────────────────────────────────────────
        banner_closed = self._handle_banners(page)

        before = self.scan_page(page)
        closed = banner_closed
        approved: list[str] = []
        dismissed: list[str] = []

        for popup in before["popups"]:
            ok = self._process_popup(page, popup, auto_confirm, approved, dismissed)
            if ok:
                closed += 1
                time.sleep(0.8)

        # backdrop/dim 잔여 정리
        _cleanup_backdrop(page)
        time.sleep(1.2)

        after = self.scan_page(page)

        # 이벤트 — 팝업별 전체 내용 보존
        ev = PopupEvent(
            "layer",
            {
                "before": before["found"],
                "closed": closed,
                "after": after["found"],
                "approved": [a["text"] for a in approved],  # 알림 패널용 요약
                "dismissed": [d["text"] for d in dismissed],
                "popups": approved + dismissed,  # 전체 상세 내용
                "page_clean": after["found"] == 0,
            },
        )
        ev.handled = True
        with self._lock:
            self._events.append(ev)

        _log.info("[popup-mgr] 레이어 처리: before=%d closed=%d after=%d", before["found"], closed, after["found"])
        return {
            "closed": closed,
            "page_clean": after["found"] == 0,
            "popups_before": before["found"],
            "popups_after": after["found"],
            "approved": [a["text"] for a in approved],
            "dismissed": [d["text"] for d in dismissed],
            "popups": approved + dismissed,  # 전체 내용 포함
            "detail": before["popups"],
        }

    def _process_popup(self, page, popup: dict, auto_confirm: bool, approved: list, dismissed: list) -> bool:
        """팝업 1개 처리. 닫힘/승인 성공 여부 반환(보류·실패는 False)."""
        sel = popup["selector"]
        text = popup.get("text", "")
        full_text = popup.get("full_text", text)
        buttons = popup.get("buttons", [])
        links = popup.get("links", [])
        ok = False

        level = _classify_popup(text)

        _log.info("[popup-mgr] 팝업 감지 — level=%s text='%s' buttons=%s", level, text[:60], buttons)
        if links:
            _log.info("[popup-mgr] 팝업 링크: %s", links[:3])

        try:
            modal = page.locator(sel).first
            if not modal.count():
                return ok

            if level == "review":
                self._queue_review_popup(text, full_text, buttons, links, level)
                # 팝업은 닫지 않음 — 사용자 결정 대기
                return ok

            if level == "auto" and auto_confirm:
                ok = _click_confirm_in(modal, page)
                if ok:
                    approved.append(_popup_record(text, full_text, buttons, links, "confirm"))
                    _log.info("[popup-mgr] 팝업 자동 승인: '%s'", text[:40])

            if not ok:
                ok = _click_close_in(modal)
                if ok:
                    dismissed.append(_popup_record(text, full_text, buttons, links, "close"))
                    _log.info("[popup-mgr] 팝업 닫기: '%s'", text[:40])

            # ESC fallback
            if not ok:
                page.keyboard.press("Escape")
                time.sleep(0.3)
                ok = True
                dismissed.append(_popup_record(text, full_text, buttons, links, "esc"))
        except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
            pass
        return ok

    def _queue_review_popup(self, text: str, full_text: str, buttons: list, links: list, level: str) -> None:
        """사용자 확인 필요 → AI 요약 후 보류 큐 등록."""
        pending_id = f"{time.strftime('%H%M%S')}-{len(self._pending)}"
        summary = _summarize_popup(full_text)
        pending_item = {
            "id": pending_id,
            "text": text,
            "full_text": full_text,
            "summary": summary,
            "buttons": buttons,
            "links": links,
            "level": level,
            "ts": time.strftime("%H:%M:%S"),
            "status": "pending",  # pending | approved | dismissed
        }
        self._pending[pending_id] = pending_item

        # 알림 이벤트에 보류 팝업 기록
        ev = PopupEvent(
            "review",
            {
                "pending_id": pending_id,
                "text": text,
                "summary": summary,
                "full_text": full_text,
                "buttons": buttons,
                "links": links,
            },
        )
        ev.handled = False  # 아직 미처리
        with self._lock:
            self._events.append(ev)

        _log.info("[popup-mgr] 팝업 보류 — id=%s summary='%s'", pending_id, summary[:60])

    # ══════════════════════════════════════════════════════════════════════════
    # 3-B. 인라인 배너 처리
    # ══════════════════════════════════════════════════════════════════════════

    def scan_banners(self, page) -> dict:
        """임시저장 불러오기 등 인라인 배너 스캔."""
        found = []
        for sel in BANNER_SELS:
            try:
                els = page.locator(sel)
                for i in range(min(els.count(), 3)):
                    el = els.nth(i)
                    if not el.is_visible(timeout=300):
                        continue
                    text = el.inner_text(timeout=500)[:100].strip()
                    action = next(
                        (v for k, v in BANNER_ACTIONS.items() if k in text),
                        None,
                    )
                    if action:
                        found.append({"selector": sel, "index": i, "text": text, "action": action})
            except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
                pass
        return {"found": len(found), "banners": found}

    def _handle_banners(self, page) -> int:
        """인라인 배너 처리. 닫은 수 반환."""
        result = self.scan_banners(page)
        closed = 0

        for banner in result["banners"]:
            action = banner.get("action", "dismiss")

            if action == "dismiss":
                if _dismiss_banner(page, banner):
                    closed += 1
                    time.sleep(0.3)

            elif action == "load" and _load_banner(page, banner):
                closed += 1
                _log.info("[popup-mgr] 배너 불러오기 클릭: %s", banner["text"][:40])
                time.sleep(1)

        return closed

    # ══════════════════════════════════════════════════════════════════════════
    # 4. 상태 조회
    # ══════════════════════════════════════════════════════════════════════════

    def status(self) -> dict:
        """감지 이력 및 현재 감시 상태 반환."""
        with self._lock:
            events = [e.to_dict() for e in self._events[-50:]]  # 최근 50개
        return {
            "watching": self._watching,
            "total_events": len(self._events),
            "recent_events": events,
            "new_tab_count": sum(1 for e in self._events if e.kind == "new_tab"),
            "new_window_count": sum(1 for e in self._events if e.kind == "new_window"),
            "layer_count": sum(1 for e in self._events if e.kind == "layer"),
        }

    def clear_events(self) -> None:
        with self._lock:
            self._events.clear()


# ── 편의 함수 (모듈 레벨) ────────────────────────────────────────────────────

_default_mgr = CdpPopupManager()


def get_manager() -> CdpPopupManager:
    """프로세스 공유 기본 매니저 반환."""
    return _default_mgr


def quick_handle(page, context=None) -> dict:
    """페이지 팝업 즉시 처리 (매니저 없이 one-shot 사용).

    Args:
        page:    Playwright Page
        context: BrowserContext (제공 시 차단 해제도 수행)
    """
    mgr = CdpPopupManager()
    if context:
        mgr.unblock(context)
    return mgr.handle_page(page)


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────


def _is_popup_url(url: str) -> bool:
    u = url.lower()
    return any(p in u for p in POPUP_URL_PATTERNS)


def _has_close_button(modal_el) -> bool:
    for sel in CLOSE_BTN_SELS:
        try:
            btn = modal_el.locator(sel).first
            if btn.count() > 0 and btn.is_visible(timeout=100):
                return True
        except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
            pass
    return False


def _clean_popup_text(raw: str) -> str:
    """팝업 inner_text에서 × 닫기 심볼·과도한 공백·버튼 텍스트를 제거해 핵심 메시지만 반환."""
    import re

    # × / ✕ / X 단독 줄 제거
    lines = [ln.strip() for ln in raw.splitlines()]
    # 닫기 심볼 / 버튼 텍스트 단독 줄 제거
    skip = {"×", "✕", "X", "닫기", "확인", "취소", "OK", "완료", "저장"}
    lines = [ln for ln in lines if ln and ln not in skip]
    text = " ".join(lines)
    # 연속 공백 제거
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text[:80]


def _summarize_popup(full_text: str) -> str:
    """팝업 전문을 알림 패널용 짧은 요약으로 정제(잠재 NameError 방지용 정의)."""
    return _clean_popup_text(full_text or "")


def _classify_popup(text: str) -> str:
    """팝업 텍스트로 처리 레벨 결정.

    Returns:
        "auto"   — 자동 처리 (단순 완료)
        "review" — AI 요약 후 사용자 확인 대기
        "close"  — × 닫기
    """
    t = text.lower()
    for keyword, level in POPUP_LEVEL_MAP:
        if keyword.lower() in t:
            return level
    # 기본: 내용 길면 review, 짧으면 auto
    return "review" if len(text) > 30 else "auto"


def _popup_record(text: str, full_text: str, buttons: list, links: list, action: str) -> dict:
    return {
        "text": text,
        "full_text": full_text,
        "buttons": buttons,
        "links": links,
        "action": action,
    }


def _popup_dedup_key(page, sel: str, i: int) -> str:
    # 중복 제거: outerHTML 앞 80자를 키로 사용
    try:
        return page.evaluate(f"document.querySelectorAll('{sel}')[{i}]?.outerHTML?.slice(0,80) || ''") or ""
    except Exception:  # noqa: BLE001 - 팝업/배너 감지·해제 — Playwright 요소 조회 실패 종류가 다양해 일괄 로그 후 계속 진행, 실제 업무 액션(결제·DB쓰기) 아닌 UI 노이즈 제거 전용(2026-09-28 검토)
        return f"{sel}:{i}"


def _popup_buttons(el) -> list[str]:
    buttons: list[str] = []
    try:
        btns = el.locator("button, a.btn, .btn").all()
        buttons = [b.inner_text(timeout=200).strip() for b in btns if b.inner_text(timeout=200).strip()]
    except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
        pass
    return buttons


def _popup_links(page, sel: str, i: int) -> list[str]:
    links: list[str] = []
    try:
        hrefs = (
            page.evaluate(
                f"[...document.querySelectorAll('{sel}')[{i}]"
                f"?.querySelectorAll('a[href]') || []]"
                f".map(a => ({{text: a.textContent.trim().slice(0,40), href: a.href.slice(0,100)}}))"
            )
            or []
        )
        links = [f"{ln['text']} → {ln['href']}" for ln in hrefs if ln.get("href")]
    except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
        pass
    return links


def _scan_one_popup(page, sel: str, i: int, el, seen_outer_html_keys: set) -> dict | None:
    """팝업 요소 1개 스캔. 숨김/제외/중복이면 None. 예외는 호출부에서 처리."""
    if not el.is_visible(timeout=500):
        return None
    # 닫힘 애니메이션 중인 요소 제외 (opacity/display 확인)
    opacity = page.evaluate(
        f"(() => {{ const e = document.querySelectorAll('{sel}')[{i}]; "
        f"if (!e) return '0'; "
        f"const s = window.getComputedStyle(e); "
        f"return s.opacity + '|' + s.display; }})() || '0|none'"
    )
    if opacity.startswith("0|") or "|none" in opacity:
        return None
    cls = el.get_attribute("class") or ""
    if any(x in cls for x in EXCLUDE_CLASSES):
        return None

    key = _popup_dedup_key(page, sel, i)
    if key in seen_outer_html_keys:
        return None
    seen_outer_html_keys.add(key)

    # 전체 내용 추출 (잘림 없음)
    full_text = ""
    with contextlib.suppress(Exception):
        full_text = el.inner_text(timeout=500).strip()
    clean_text = _clean_popup_text(full_text)

    buttons = _popup_buttons(el)
    links = _popup_links(page, sel, i)  # 링크 목록 (공지 URL 등)
    has_close = _has_close_button(el)
    return {
        "selector": sel,
        "index": i,
        "text": clean_text,  # 정제된 요약
        "full_text": full_text,  # 전체 원문
        "buttons": buttons,
        "links": links,
        "has_close_btn": has_close,
    }


def _dismiss_banner(page, banner: dict) -> bool:
    """배너 dismiss: 닫기 버튼 → JS 제거 → ESC 순서로 시도. 성공 시 True."""
    sel = banner["selector"]
    idx = banner["index"]
    dismissed = False

    # 1) 배너 내 ×/닫기 버튼
    try:
        el = page.locator(sel).nth(idx)
        if _click_close_in(el):
            dismissed = True
    except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
        pass

    # 2) JS로 배너 요소 직접 제거 (닫기 버튼 없는 경우)
    if not dismissed:
        try:
            page.evaluate(f"""
            (() => {{
                const els = document.querySelectorAll('{sel}');
                const el = els[{idx}];
                if (el) {{
                    el.style.display = 'none';
                    el.setAttribute('aria-hidden', 'true');
                }}
            }})();
            """)
            dismissed = True
            _log.info("[popup-mgr] 배너 JS 제거: %s", banner["text"][:40])
        except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
            pass

    # 3) ESC
    if not dismissed:
        try:
            page.keyboard.press("Escape")
            dismissed = True
        except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
            pass
    return dismissed


def _load_banner(page, banner: dict) -> bool:
    """배너의 불러오기 링크 클릭. 클릭했으면 True."""
    try:
        el = page.locator(banner["selector"]).nth(banner["index"])
        link = el.locator("a.link-area, a[href]").first
        if link.count() > 0:
            link.click(timeout=2000)
            return True
    except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
        pass
    return False


def _click_visible(locate, vis_timeout: int, log_fmt: str, key: str) -> bool:
    """locate() 결과의 첫 요소가 보이면 클릭. 성공 True, 실패/예외 False."""
    try:
        btn = locate().first
        if btn.count() > 0 and btn.is_visible(timeout=vis_timeout):
            btn.click(timeout=2000)
            time.sleep(0.4)
            _log.info(log_fmt, key)
            return True
    except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
        pass
    return False


def _click_confirm_in(modal_el, page=None) -> bool:
    """모달 내 확인/승인 버튼 클릭. 성공 시 True.

    우선순위:
      1. button.btn-primary (셀러센터 주요 액션 버튼)
      2. CONFIRM_BTN_SELS 기반 셀렉터
      3. 텍스트 기반 (확인, 완료 등)
    """
    # 1. btn-primary 먼저
    for sel in CONFIRM_BTN_SELS:
        if _click_visible(lambda sel=sel: modal_el.locator(sel), 300, "[popup-mgr] 승인 버튼 클릭: %s", sel):
            return True

    # 2. 텍스트 기반 확인 버튼
    for txt in CONFIRM_TEXTS:
        if _click_visible(
            lambda txt=txt: modal_el.get_by_text(txt, exact=True), 200, "[popup-mgr] 텍스트 승인: '%s'", txt
        ):
            return True

    # 3. 페이지 전체에서 텍스트 검색 (모달이 복잡한 경우)
    if page:
        for txt in CONFIRM_TEXTS:
            if _click_visible(
                lambda txt=txt: page.get_by_text(txt, exact=True), 200, "[popup-mgr] 페이지 텍스트 승인: '%s'", txt
            ):
                return True

    return False


def _click_close_in(modal_el) -> bool:
    """모달 내부 닫기(×) 버튼 클릭. 성공 시 True."""
    for sel in CLOSE_BTN_SELS:
        try:
            btn = modal_el.locator(sel).first
            if btn.count() > 0 and btn.is_visible(timeout=200):
                btn.click(timeout=2000)
                time.sleep(0.4)
                _log.info("[popup-mgr] 닫기 버튼 클릭: %s", sel)
                return True
        except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
            pass
    for txt in CLOSE_TEXTS:
        try:
            btn = modal_el.get_by_text(txt, exact=True).first
            if btn.count() > 0 and btn.is_visible(timeout=200):
                btn.click(timeout=2000)
                time.sleep(0.4)
                _log.info("[popup-mgr] 텍스트 닫기: '%s'", txt)
                return True
        except Exception:  # noqa: BLE001 - 여러 셀렉터/방법을 순차 시도하는 best-effort 패턴 — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
            pass
    return False


def _cleanup_backdrop(page) -> None:
    with contextlib.suppress(Exception):
        page.evaluate("""
        () => {
            const sels = [
                '.seller-backdrop', '.modal-backdrop', '.dimmed',
                '.dim', '[class*="dimm"]', '[class*="backdrop"]',
            ];
            sels.forEach(s => {
                document.querySelectorAll(s).forEach(el => {
                    const st = window.getComputedStyle(el);
                    if (st.display !== 'none' && st.opacity !== '0') {
                        el.style.display = 'none';
                    }
                });
            });
            document.body.style.overflow = '';
            document.body.style.paddingRight = '';
        }
        """)


# ══════════════════════════════════════════════════════════════════════════════
# 백그라운드 CDP 폴러 — 상시 팝업 감지
# ══════════════════════════════════════════════════════════════════════════════


class CdpPopupPoller:
    """백그라운드 스레드에서 CDP를 주기적으로 폴링해 팝업을 자동 처리.

    서버 lifespan에서 시작/정지:
        poller = CdpPopupPoller(interval=5)
        poller.start()
        ...
        poller.stop()
    """

    def __init__(self, interval: int = 5, cdp_url: str = "http://127.0.0.1:9222"):
        self.interval = interval
        self.cdp_url = cdp_url
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._mgr = get_manager()
        self.poll_count = 0
        self.error_streak = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, name="CdpPopupPoller", daemon=True)
        self._thread.start()
        _log.info("[poller] 백그라운드 팝업 폴러 시작 (interval=%ds)", self.interval)

    def stop(self) -> None:
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=10)
        _log.info("[poller] 폴러 정지")

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _loop(self) -> None:
        while not self._stop_evt.wait(self.interval):
            try:
                self._tick()
                self.error_streak = 0
            except Exception as e:  # noqa: BLE001 - 팝업/배너 감지·해제 — Playwright 요소 조회 실패 종류가 다양해 일괄 로그 후 계속 진행, 실제 업무 액션(결제·DB쓰기) 아닌 UI 노이즈 제거 전용(2026-09-28 검토)
                self.error_streak += 1
                _log.debug("[poller] tick 오류 (streak=%d): %s", self.error_streak, e)
                if self.error_streak >= 10:
                    _log.warning("[poller] 오류 10회 연속 — CDP 미연결 상태로 판단, 대기")
                    self._stop_evt.wait(30)  # 30초 추가 대기
                    self.error_streak = 0

    def _tick(self) -> None:
        # 영속 브라우저 스레드에서 캐시된 CDP 연결을 재사용한다.
        # 과거: 매 틱 `with sync_playwright()` → 5초마다 새 node 드라이버 프로세스 +
        # Windows conhost 콘솔 창이 깜빡이는 "상시 터미널" 문제. 이제 단일 영속 연결을
        # 재사용하므로 틱당 드라이버 생성 0건. 단일 스레드 직렬화로 CDP 충돌도 예방.
        from scripts.browser.cdp.connection import run_on_browser_thread

        run_on_browser_thread(self._tick_work, timeout=60)
        self.poll_count += 1

    def _tick_work(self) -> None:
        from scripts.browser.cdp.connection import _connect_browser

        _browser, ctx = _connect_browser()  # 캐시된 영속 (browser, context)
        pages = ctx.pages

        # 탭 수 변화 감지
        current_urls = {p.url for p in pages}
        with self._mgr._lock:
            prev_urls = getattr(self._mgr, "_prev_urls", set())
            new_urls = current_urls - prev_urls
            self._mgr._prev_urls = current_urls  # type: ignore[attr-defined]

        # 새 탭/창 감지
        for url in new_urls:
            kind = "new_window" if _is_popup_url(url) else "new_tab"
            ev = PopupEvent(kind, {"url": url, "source": "poller"})
            ev.handled = True
            with self._mgr._lock:
                self._mgr._events.append(ev)
            _log.info("[poller] 새 %s 감지: %s", kind, url[:80])

        # smartstore 탭 팝업/배너 자동 처리
        ss_page = next((p for p in pages if "products/create" in p.url), None) or next(
            (p for p in pages if "smartstore.naver.com" in p.url), None
        )
        if ss_page:
            mgr = CdpPopupManager()

            # 배너 스캔
            banners = mgr.scan_banners(ss_page)
            if banners["found"] > 0:
                n = mgr._handle_banners(ss_page)
                _log.info("[poller] 배너 자동 처리: %d건", n)
                if n > 0:
                    ev = PopupEvent("banner", {"closed": n, "source": "poller"})
                    ev.handled = True
                    with self._mgr._lock:
                        self._mgr._events.append(ev)

            # 모달 스캔
            modals = mgr.scan_page(ss_page)
            if modals["found"] > 0:
                result = mgr.handle_page(ss_page, auto_confirm=True)
                _log.info(
                    "[poller] 모달 자동 처리: closed=%d approved=%s clean=%s",
                    result["closed"],
                    result.get("approved"),
                    result["page_clean"],
                )
                # 공유 매니저에 이벤트 기록
                if result["closed"] > 0:
                    ev = PopupEvent(
                        "layer",
                        {
                            "closed": result["closed"],
                            "approved": result.get("approved", []),
                            "dismissed": result.get("dismissed", []),
                            "popups": result.get("popups", []),  # 전체 내용
                            "page_clean": result["page_clean"],
                            "source": "poller",
                        },
                    )
                    ev.handled = True
                    with self._mgr._lock:
                        self._mgr._events.append(ev)


def start_poller(interval: int = 5) -> CdpPopupPoller:
    """전역 폴러 시작. 이미 실행 중이면 기존 인스턴스 반환."""
    global _poller
    if _poller and _poller.running:
        return _poller
    _poller = CdpPopupPoller(interval=interval)
    _poller.start()
    return _poller


def stop_poller() -> None:
    """전역 폴러 정지."""
    global _poller
    if _poller:
        _poller.stop()
        _poller = None


def poller_status() -> dict:
    """전역 폴러 상태 반환."""
    global _poller
    if not _poller:
        return {"running": False, "poll_count": 0, "interval": 0}
    return {
        "running": _poller.running,
        "poll_count": _poller.poll_count,
        "interval": _poller.interval,
        "error_streak": _poller.error_streak,
    }
