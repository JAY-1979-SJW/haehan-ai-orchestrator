"""경쟁사 상품 상세 수집 (공개 스토어프론트 기준).

adcr 광고 링크를 열지 않고 __NEXT_DATA__ 의 직접 URL 로만 접근한다.
"""

from __future__ import annotations

from scripts.naver.shopping.competitor_detail.detail_parser import (  # noqa: F401
    CompetitorDetailParser,
)
from scripts.naver.shopping.competitor_detail.models import (  # noqa: F401
    CONF_HIGH,
    CONF_LOW,
    CONF_MED,
    SRC_DOM,
    SRC_JSON,
    SRC_VISION,
    CompetitorProduct,
    Field,
    OptionCombo,
)
from scripts.naver.shopping.competitor_detail.url_finder import (  # noqa: F401
    find_direct_urls,
    is_safe_product_url,
)
