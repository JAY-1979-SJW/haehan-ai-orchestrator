"""page_helper 공개 API — popup/nav/interact/watch/inspect leaf 모듈 aggregator. [docs/module_separation_standard.md]"""

from __future__ import annotations

from .page_helper_common import (  # noqa: F401
    WORK_CATEGORIES,
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
