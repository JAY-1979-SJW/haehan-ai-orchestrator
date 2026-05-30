"""page_helper 공개 API — 책임별 leaf 모듈 aggregator.

popup/nav/interact/watch/inspect 기능이 각 leaf 에 구현돼 있다.
이 모듈은 공개 API 를 묶어 단일 진입점으로 제공한다.
[docs/module_separation_standard.md]
"""
from __future__ import annotations

from .page_helper_common import (  # noqa: F401
    _CRITICAL_SITE_PATTERNS, _AUTO_POPUP_HANDLE, _ERROR_SELECTORS,
    _GOV_FALLBACK_TLD, _find_frame,
    _safe_auto_popup, _safe_auto_login_detect,
    _detect_critical_category, _safe_critical_log,
    disable_auto_popup_handling, enable_auto_popup_handling,
    disable_auto_login_detection, enable_auto_login_detection,
    is_work_category, WORK_CATEGORIES,
)
from .page_helper_nav import (  # noqa: F401
    page_goto, page_goto_wait, page_wait_visible, page_wait_nav,
)
from .page_helper_interact import (  # noqa: F401
    page_check_error, page_wait_click, page_click_then_wait, page_wait_type,
)
from .page_helper_watch import (  # noqa: F401
    NetworkLog, page_watch_network,
    DomChangeLog, page_watch_dom,
    page_poll_until, VerifyResult, page_submit_and_verify,
)
from .page_helper_inspect import page_inspect  # noqa: F401
