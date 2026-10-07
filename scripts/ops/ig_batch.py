# 호환 shim: 실제 스크립트는 scripts/instagram/ops/ig_batch.py (docs/architecture/TOOL_HOME_MAP.md — 도구 집으로 이동)
# 직접 실행(python scripts/ops/ig_batch.py ...)과 skill·문서의 옛 경로 호출이 그대로 동작하도록 실행을 전달한다.
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.instagram.ops.ig_batch import main  # noqa: E402

if __name__ == "__main__":
    main()
