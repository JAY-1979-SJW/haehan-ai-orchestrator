"""실행 전달 shim: 실제 구현은 scripts/naver/cafe/ops/daily_cafe_marketing_pipeline.py
(docs/architecture/TOOL_HOME_MAP.md). Windows 작업 스케줄러(HaehanAI_DailyCafeMarketing)가
이 파일을 경로로 직접 실행하므로, 파일 자체는 남기고 실행만 새 위치로 넘긴다.
"""

from __future__ import annotations

from scripts.naver.cafe.ops.daily_cafe_marketing_pipeline import *  # noqa: F403
from scripts.naver.cafe.ops.daily_cafe_marketing_pipeline import main

if __name__ == "__main__":
    raise SystemExit(main())
