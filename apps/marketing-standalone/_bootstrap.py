"""이 앱의 모든 진입점이 맨 위에서 import하는 부트스트랩.

디렉터리명(`marketing-standalone`)에 하이픈이 있어 `apps.marketing-standalone.*`
형태의 점(dot) import가 불가능하다. 대신 이 폴더 자체를 sys.path에 추가해
`core.xxx` / `connectors.xxx` 형태로 임포트한다. scripts.common.logger 등 원본
저장소에도 의존하지 않는다 — 이 앱은 통째로 다른 저장소로 옮겨져도 동작해야
한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def get_logger(name: str):
    import logging

    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)-5s %(name)s │ %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
