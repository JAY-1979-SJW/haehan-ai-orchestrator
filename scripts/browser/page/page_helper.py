"""page_helper 공개 API — 책임별 leaf 모듈 aggregator.

popup/nav/interact/watch/inspect 기능이 각 leaf 에 구현돼 있다.
이 모듈은 공개 API 를 묶어 단일 진입점으로 제공한다.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

from .page_helper_common import (  # noqa: F401
    _AUTO_POPUP_HANDLE,
    _CRITICAL_SITE_PATTERNS,
    _ERROR_SELECTORS,
    _GOV_FALLBACK_TLD,
    WORK_CATEGORIES,
    _detect_critical_category,
    _find_frame,
    _safe_auto_login_detect,
    _safe_auto_popup,
    _safe_critical_log,
    disable_auto_login_detection,
    disable_auto_popup_handling,
    enable_auto_login_detection,
    enable_auto_popup_handling,
    is_work_category,
)
from .page_helper_inspect import page_inspect  # noqa: F401
from .page_helper_interact import (  # noqa: F401
    page_check_error,
    page_click_then_wait,
    page_wait_click,
    page_wait_type,
)
from .page_helper_nav import (  # noqa: F401
    page_goto,
    page_goto_wait,
    page_wait_nav,
    page_wait_visible,
)
from .page_helper_watch import (  # noqa: F401
    DomChangeLog,
    NetworkLog,
    VerifyResult,
    page_poll_until,
    page_submit_and_verify,
    page_watch_dom,
    page_watch_network,
)
