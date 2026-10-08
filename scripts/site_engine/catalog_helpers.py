"""사이트 도구 공용 카탈로그·대상 선택·요약 출력 함수 — 사이트 무관(순수 함수 + 파일 읽기).

여러 사이트 도구가 똑같이 복사해 쓰던 본문을 한 곳으로 모았다(BASELINE_AUDIT §4 N7).
- load_or_build_catalog: hiworks/naver smartstore actions.load_action_catalog
- select_named_targets: hiworks service_explorer.selected_targets · naver content.select_targets
- print_keyed_summary: hiworks actions.print_prepare_plan_summary · naver content.print_action_summary

도구별 값(기본 경로·빌드/저장 함수·대상 표·제목·출력 항목)은 호출 시점에 넘긴다
(시험이 각 모듈 상수·함수를 바꿔 끼우는 방식 유지).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


def load_or_build_catalog(
    path: str | Path | None,
    default_path: Path,
    build: Callable[[], dict[str, Any]],
    save: Callable[[dict[str, Any], Path], Any],
) -> dict[str, Any]:
    """path(없으면 default_path)에 저장된 카탈로그를 읽고, 없으면 build() 로 만들어 save 한 뒤 돌려준다."""
    source = Path(path) if path else default_path
    if source.exists():
        return json.loads(source.read_text(encoding="utf-8"))
    catalog = build()
    save(catalog, source)
    return catalog


def select_named_targets(
    targets: Mapping[str, dict[str, str]], name: str | None, label: str
) -> dict[str, dict[str, str]]:
    """name 이 없거나 'all' 이면 전체 사본, 아니면 소문자 키 1개만. 없는 키면 KeyError(f"unknown {label}: {name}")."""
    if not name or name == "all":
        return dict(targets)
    key = name.strip().lower()
    if key not in targets:
        raise KeyError(f"unknown {label}: {name}")
    return {key: targets[key]}


def print_keyed_summary(
    title: str,
    items: Sequence[dict[str, Any]],
    fields: Sequence[tuple[str, str]],
    path: Path | None = None,
) -> None:
    """'=' 줄로 감싼 제목 뒤에 항목마다 "- <key>: label=값 ..." 한 줄(값은 summary[field], 없으면 0), path 가 있으면 saved 줄."""
    print("=" * 60)
    print(title)
    print("=" * 60)
    for item in items:
        summary = item.get("summary") or {}
        print(f"- {item.get('key')}: " + " ".join(f"{label}={summary.get(field, 0)}" for label, field in fields))
    if path:
        print(f"saved: {path}")
