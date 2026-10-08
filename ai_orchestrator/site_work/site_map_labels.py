"""L1 Shared Contracts — 사이트 업무 지도의 이름 정리·전역 메뉴 분리 규칙 (순수, 입출력 없음).

기준서: docs/specs/2026-10-05_site_task_map_m7_onboarding_auto_prepare.md §8 (지도 품질 S1.2)

왜 필요한가(2026-10-05 네이버 카페 실검증): 버튼 원문 텍스트(줄바꿈·화면 수치 포함)가 업무 이름이 되고, 모든 화면에 있는 상단 메뉴가
화면마다 업무로 쌓여 17건 중 실질 업무가 2~3건이었다.

- W3C accname 1.2 는 이름을 하위 텍스트 전체를 공백 정규화해 이어 붙인 한 줄로 만들고 **길이 제한이 없다** — 표준만으로는 짧은 이름을 얻을 수
  없으므로 표시·실행용 이름은 이 모듈의 규칙(첫 의미 있는 줄·수치 줄 제외·40자·제어문자 제거)으로 만든다. 명시적 `aria-label` 은 내용보다 우선(accname 2번째 단계).
- 전역 메뉴: ARIA 랜드마크 banner·navigation·contentinfo 안의 읽기 컨트롤, 또는 여러 화면에 반복되는 읽기 이동 버튼 — 업무가 아니라 지도의 `global_nav` 로 한 번만 기록.
- 위험(쓰기·제출) 컨트롤은 전역 영역에 있어도 절대 전역으로 빼지 않는다(위험 등급 게이트가 항상 적용되도록 업무로 남긴다).
- 값은 저장하지 않는다. 이름은 짧게 잘라 제어문자를 지운다 — 사이트가 정한 글자는 자료일 뿐 지시가 아니다.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

LABEL_MAX = 40
GLOBAL_NAV_MAX = 40
GLOBAL_LANDMARKS = ("banner", "navigation", "contentinfo")
FREQUENCY_MIN_PAGES = 3  # 한 번의 탐색에서 이만큼 이상의 서로 다른 화면에 있는 읽기 이동 버튼은 전역으로 본다

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏  ]")
_SPACES = re.compile(r"[ \t 　]+")
# "362만 인용", "12,345건", "3.2K" 처럼 숫자로 시작하고 짧은 단위만 붙은 줄은 화면 수치다(이름이 아니다).
_STAT_LINE = re.compile(r"^\W*\d[\d.,]*\s*[^\W\d_]{0,4}(\s+[^\W\d_]{1,4})?\W*$")


def _normalize(text: str) -> str:
    return _SPACES.sub(" ", _CONTROL_CHARS.sub("", text)).strip()


def clean_label(text: str, aria: str = "") -> str:
    """버튼의 표시·실행용 이름. 명시적 aria-label 이 있으면 그것, 없으면 원문의 첫 의미 있는 줄(수치 줄 제외)을 40자까지."""
    explicit = _normalize(str(aria or ""))
    if explicit:
        return explicit[:LABEL_MAX].strip()
    lines = [n for line in re.split(r"[\r\n]+", str(text or "")) if (n := _normalize(line))]
    if not lines:
        return ""
    chosen = next((line for line in lines if not _STAT_LINE.match(line)), lines[0])
    return chosen[:LABEL_MAX].strip()


def is_global_landmark(landmark: Any) -> bool:
    return str(landmark or "") in GLOBAL_LANDMARKS


def global_nav_labels(snapshot: dict[str, Any], *, risk_of: Callable[[list[str]], str]) -> list[str]:
    """스냅샷에서 전역 랜드마크 안의 **읽기 등급** 버튼 이름들(중복 제거, 순서 유지). 위험 컨트롤은 포함하지 않는다."""
    path = urlparse(str(snapshot.get("url") or "")).path or "/"
    found: list[str] = []
    for frame in snapshot.get("frames", []):
        if "error" in frame:
            continue
        for b in frame.get("buttons", []):
            if not is_global_landmark(b.get("landmark")) or not b.get("visible", True):
                continue
            label = clean_label(str(b.get("text") or ""), str(b.get("aria") or ""))
            if label and label not in found and risk_of([label, path]) == "read":
                found.append(label)
    return found


def _is_nav_button(task: dict[str, Any]) -> bool:
    return task.get("category") == "navigate" and task.get("risk") == "read" and "#btn_" in str(task.get("id", ""))


def split_by_frequency(
    tasks: list[dict[str, Any]], *, min_pages: int = FREQUENCY_MIN_PAGES
) -> tuple[list[dict[str, Any]], list[str]]:
    """여러 화면에 반복되는 읽기 이동 버튼을 업무에서 빼 전역 이름 목록으로 돌려준다. (남은 업무, 전역 이름)."""
    urls_by_label: dict[str, set[str]] = defaultdict(set)
    for t in tasks:
        if _is_nav_button(t):
            urls_by_label[clean_label(str(t.get("control") or ""))].add(str(t.get("url") or ""))
    global_labels = {label for label, urls in urls_by_label.items() if label and len(urls) >= min_pages}
    kept = [t for t in tasks if not (_is_nav_button(t) and clean_label(str(t.get("control") or "")) in global_labels)]
    return kept, sorted(global_labels)


def merge_global_nav(site_map: dict[str, Any], labels: list[str], *, now: str) -> dict[str, Any]:
    """지도에 전역 메뉴 이름을 합친다(새 dict). 새로 알게 된 것이 없으면 그대로 돌려준다."""
    existing = [str(x) for x in (site_map.get("global_nav") or [])]
    merged = sorted({*existing, *[x for x in labels if x]})[:GLOBAL_NAV_MAX]
    if merged == existing:
        return site_map
    return {**site_map, "global_nav": merged, "global_nav_at": now}


def prune_legacy(site_map: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """예전 형식(원문 텍스트가 이름)으로 저장됐거나 전역 메뉴인 **미검증 읽기 이동 업무**만 지운다.

    verified 업무·쓰기·제출 업무·사람이 분류를 확정한 업무는 절대 지우지 않는다(다음 탐색이 깨끗한 형식으로 다시 만든다).
    """
    glob = set(site_map.get("global_nav") or [])

    def removable(t: dict[str, Any]) -> bool:
        if (
            not _is_nav_button(t) or t.get("state") != "observed" or t.get("purpose")
        ):  # 목적을 적었으면 사람이 다룬 업무
            return False
        control = str(t.get("control") or "")
        label = clean_label(control)
        return label != control or label in glob

    tasks = site_map.get("tasks", [])
    kept = [t for t in tasks if not removable(t)]
    if len(kept) == len(tasks):
        return site_map, 0
    return {**site_map, "tasks": kept}, len(tasks) - len(kept)


SEEN_PAGES_MAX = 20


def _is_action_button(task: dict[str, Any]) -> bool:
    return task.get("risk") in ("write", "submit") and "#btn_" in str(task.get("id", ""))


def collapse_duplicate_actions(site_map: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """같은 글자의 쓰기·제출 **버튼 업무**가 화면마다 쌓인 것을 하나로 합치고 본 화면 수(`seen_pages`)만 기록한다.

    예: 상품 목록 20쪽의 "Add to basket" 21개 → 1개(seen_pages=20). verified 업무·목적을 적은 업무는 지우지 않고(있으면 그것을 대표로),
    이름 끝의 "(화면 제목)" 꼬리는 자동으로 붙은 것일 때만 뗀다. 위험 등급은 그대로 둔다(내리지 않는다).
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for t in site_map.get("tasks", []):
        if _is_action_button(t):
            groups[(clean_label(str(t.get("control") or "")), str(t.get("risk")))].append(t)
    drop: set[str] = set()
    update: dict[str, dict[str, Any]] = {}
    for (label, _risk), members in groups.items():
        if len(members) < 2 or not label:
            continue
        members = sorted(members, key=lambda t: (t.get("state") != "verified", not t.get("purpose"), str(t.get("id"))))
        keep = members[0]
        for other in members[1:]:
            if other.get("state") == "observed" and not other.get("purpose"):
                drop.add(str(other["id"]))
        seen = min(SEEN_PAGES_MAX, max(int(keep.get("seen_pages") or 0), len(members)))
        changes: dict[str, Any] = {"seen_pages": seen}
        if str(keep.get("name", "")).startswith(f"{label} ("):
            changes["name"] = label
        update[str(keep["id"])] = changes
    if not drop and not update:
        return site_map, 0
    tasks = [dict(t, **update.get(str(t.get("id")), {})) for t in site_map.get("tasks", []) if str(t.get("id")) not in drop]
    return {**site_map, "tasks": tasks}, len(drop)
