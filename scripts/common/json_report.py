"""JSON 결과 파일 저장 공용 함수(표준 라이브러리만).

naver company_seo.save_plan/save_diagnosis·keyword_tools.save_payload·shopping_competitor.save_competitor_report
가 기본 경로만 다르게 똑같이 복사해 쓰던 본문을 한 곳으로 모았다. 데이터 폴더·기본 경로는 호출 시점에 넘긴다
(시험이 각 모듈 상수를 바꿔 끼우는 방식 유지).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def save_json_report(data: Any, data_dir: Path, default_path: Path, output: str | Path | None = None) -> Path:
    """data_dir 를 만들고 output(없으면 default_path)에 data 를 UTF-8 JSON(indent=2, ensure_ascii=False)으로 저장한다."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = Path(output) if output else default_path
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
