"""EUM 도구 JSON 결과 저장 공용 함수.

access_explorer.save_accessible_pages·workspace.save_work_index 가 똑같이 복사해 쓰던
"데이터 폴더 만들고 → 지정 경로(없으면 기본 파일명)에 들여쓰기 JSON 저장" 본문을 한 곳으로 모았다.
데이터 폴더(DATA_DIR)는 각 모듈 상수를 호출 시점에 넘긴다(시험이 모듈 상수를 바꿔 끼우는 방식 유지).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def save_json(data: Any, data_dir: Path, default_name: str, path: Path | None = None) -> Path:
    """data_dir 를 만들고 path(없으면 data_dir/default_name)에 data 를 UTF-8 JSON(indent=2)으로 저장한다."""
    data_dir.mkdir(parents=True, exist_ok=True)
    out = path or (data_dir / default_name)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
