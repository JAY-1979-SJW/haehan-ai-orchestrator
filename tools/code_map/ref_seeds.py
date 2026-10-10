"""영향 시험 선별용 '문자열 참조 출발점' — 바뀐 비-.py 파일을 문자열로 읽는 .py 를 찾는다.

코드맵 간선은 .py import 만 따라가므로, configs/folder_registry.json 처럼 .py 가 아닌 파일이 바뀌면 그 파일을 읽는 시험이
영향 시험에서 빠진다(2026-10-08 W3 364f4b83: tests/test_folder_gate.py 는 json 을 직접 언급하지 않고, 그 json 을 여는
scripts/ops/folder_gate.py 를 import 한다). 그래서 모든 추적 .py 를 훑어 바뀐 비-.py 의 경로나 파일명을 문자열로 담은 .py 를
'바뀐 .py'처럼 역방향 탐색의 출발점에 더한다. verify_change(CI)와 merge_step_check(합본 점검)가 이 함수를 같이 쓴다.
"""

from __future__ import annotations

from pathlib import Path

NON_PY_SKIP_SUFFIX = (
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".lock",
)  # 문서·이미지는 시험이 경로로 읽는 설정이 아니다


def py_files_referencing_non_py(root: Path, changed: list[str], tracked: list[str]) -> dict[str, list[str]]:
    """바뀐 비-.py 파일을 **문자열로 읽는** .py 파일 → 참조한 파일 목록.

    일치 규칙: 저장소 상대 경로 전체(슬래시·역슬래시)가 소스에 들어 있거나, 파일명이 따옴표로 둘러싸여 있으면(`"folder_registry.json"`,
    경로 조인) 참조로 본다. 파일명만으로 맞추는 것은 추적 파일 중 그 이름이 하나뿐일 때만 한다(package.json 처럼 여럿이면 전체 경로로만).
    """
    targets = [c for c in changed if not c.endswith(".py") and not c.endswith(NON_PY_SKIP_SUFFIX)]
    if not targets:
        return {}
    name_counts: dict[str, int] = {}
    for f in tracked:
        name = f.rsplit("/", 1)[-1]
        name_counts[name] = name_counts.get(name, 0) + 1
    needles: dict[str, list[str]] = {}
    for rel in targets:
        name = rel.rsplit("/", 1)[-1]
        keys = [rel, rel.replace("/", chr(92))]
        if name_counts.get(name, 0) <= 1:  # 이름이 유일할 때만 파일명 단독 일치를 허용
            keys += [f'"{name}"', f"'{name}'"]
        needles[rel] = keys
    found: dict[str, list[str]] = {}
    for src in (f for f in tracked if f.endswith(".py")):
        try:
            text = (root / src).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hit = [rel for rel, keys in needles.items() if any(k in text for k in keys)]
        if hit:
            found[src] = hit
    return found


def seeds_for(root: Path, changed: list[str], tracked: list[str]) -> list[str]:
    """역방향 탐색의 출발점 = 바뀐 파일 전부 + 바뀐 비-.py 를 문자열로 참조하는 .py."""
    return sorted({*changed, *py_files_referencing_non_py(root, changed, tracked)})
