"""Google 도구 보고서 저장·요약 출력 공용 함수.

scripts/google/ 의 카탈로그·보고서 모듈(surfaces·workflows_catalog·live_inputs_coverage·
live_surface_explorer·cloud/live_console_explorer·android_app_dev_report·domain_taxonomy)이 똑같이 복사해 쓰던 "타임스탬프 JSON + latest 사본 저장"과
"요약 출력" 본문을 한 곳으로 모았다. 경로 상수는 각 모듈에 그대로 두고 호출 시점 값을 넘긴다
(시험이 모듈 상수를 바꿔 끼우는 방식을 그대로 지원).
vision_usage_gate 는 L2(정책) 모듈이라 L5 인 이 모듈을 import 하지 않는다(층 역전 방지).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_stamp() -> str:
    """파일명용 UTC 시각 문자열(YYYYmmdd_HHMMSS)."""
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def save_json_with_latest(
    data: Any,
    report_dir: Path,
    latest: Path,
    prefix: str,
    path: Path | None = None,
    *,
    ensure_ascii: bool = False,
) -> Path:
    """data 를 report_dir/<prefix>_<UTC시각>.json(또는 path)과 latest 에 같은 내용으로 저장하고 저장 경로를 돌려준다."""
    report_dir.mkdir(parents=True, exist_ok=True)
    latest.parent.mkdir(parents=True, exist_ok=True)
    timestamp = utc_stamp()
    target = path or report_dir / f"{prefix}_{timestamp}.json"
    text = json.dumps(data, ensure_ascii=ensure_ascii, indent=2)
    target.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    return target


def save_json_md_report(
    report: dict[str, Any],
    data_dir: Path,
    doc_dir: Path,
    latest: Path,
    prefix: str,
    render_markdown: Callable[[dict[str, Any]], str],
) -> tuple[Path, Path]:
    """JSON(data_dir)·latest 사본·마크다운(doc_dir)을 같은 타임스탬프로 저장하고 (json 경로, md 경로)를 돌려준다.

    마크다운은 JSON 두 벌을 쓴 뒤에 render_markdown(report)로 만든다(기존 저장 순서 유지).
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    doc_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_stamp()
    json_path = save_json_with_latest(report, data_dir, latest, prefix, data_dir / f"{prefix}_{timestamp}.json")
    md_path = doc_dir / f"{prefix}_{timestamp}.md"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def print_report_summary(
    title: str,
    counts: dict[str, Any],
    fields: Iterable[tuple[str, str]],
    json_path: Path,
    md_path: Path,
    latest: Path,
) -> None:
    """'=' 줄로 감싼 제목, (표시명, counts 키) 순서의 개수, 저장 경로 3개를 출력한다."""
    print("=" * 60)
    print(title)
    print("=" * 60)
    for label, key in fields:
        print(f"{label}: {counts[key]}")
    print(f"json: {json_path}")
    print(f"markdown: {md_path}")
    print(f"latest: {latest}")
