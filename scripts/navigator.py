"""navigator 공개 API — 책임별 leaf 모듈 aggregator.

goto/scan/interact/verify/blog/session 기능이 각 leaf 에 구현돼 있다.
[docs/module_separation_standard.md]
"""
from __future__ import annotations

from .navigator_common import resolve, _find_element_in_frames, _normalize_text  # noqa: F401
from .navigator_nav import goto, wait_login  # noqa: F401
from .navigator_scan import scan_links, scan_page  # noqa: F401
from .navigator_interact import type_into, click_link, click_button, paste_image  # noqa: F401
from .navigator_verify import (  # noqa: F401
    verify_input, verify_text, is_ready, handle_draft_restore_popup,
)
from .navigator_blog import write_blog_post  # noqa: F401
from .navigator_session import save_session  # noqa: F401
