"""시험 경로를 문자열로 적어 둔 설정·스크립트가 실제 존재하는 파일을 가리키는지 확인한다.

B0-a(TESTS_STRUCTURE_DESIGN.md §1-3-B) — 시험을 `tests/<기능>/`로 옮기기 전에, 그런 참조가
어디에 있는지와 지금 이미 깨진 참조(기준선)를 고정해 둔다. 이동 배치마다 참조 문자열을
같이 갱신하므로, 이 시험은 "이동 후 참조 갱신을 빠뜨리지 않았는가"를 잡는다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 시험 경로 문자열을 담고 있는 파일(§1-3-B 표) — 자유 텍스트(docs/, 주석)는 대상 밖.
SOURCE_FILES = [
    ROOT / "tools" / "quality" / "required_quality_gate.py",
    ROOT / "tools" / "quality" / "module_quality_gate_modules.py",
    ROOT / "tools" / "quality" / "module_quality_gate_checks_repo.py",
    ROOT / "configs" / "site_automation_status_index.json",
    ROOT / "configs" / "module_boundaries.json",
    ROOT / "tools" / "audits" / "google" / "audit_google_automation_baseline_contract.py",
]

# `tests/x/y.py` 또는 `ai_orchestrator/tests/x.py` 형태(끝에 `::func` 가 붙을 수 있음).
PATH_RE = re.compile(r"(?:ai_orchestrator/)?tests/[\w./-]+\.py")

# 이 시험을 추가하는 시점(B0-a)에 이미 깨져 있던 참조 — 새로 깨지는 것만 잡기 위한 기준선.
# (이동 배치가 끝나면 참조도 같이 갱신되므로 이 목록은 줄어들어야 하며, 늘어나면 안 된다.)
_BASELINE_PATH = ROOT / "tests" / "data" / "test_path_refs_baseline.json"


def _extract_paths(text: str) -> set[str]:
    found = set()
    for m in PATH_RE.finditer(text):
        raw = m.group(0)
        # `::func` 접미사가 붙은 경우 테스트 nodeid 문자열 안이므로 분리.
        raw = raw.split("::", 1)[0]
        found.add(raw)
    return found


def _all_referenced_paths() -> dict[str, set[str]]:
    by_source: dict[str, set[str]] = {}
    for src in SOURCE_FILES:
        if not src.exists():
            continue
        text = src.read_text(encoding="utf-8")
        by_source[str(src.relative_to(ROOT)).replace("\\", "/")] = _extract_paths(text)
    return by_source


def test_source_files_exist():
    """대상 파일 목록 자체가 저장소에서 사라지지 않았는지(이름 변경 시 이 시험도 갱신 필요)."""
    assert SOURCE_FILES, "SOURCE_FILES 가 비어 있음 — 아래 missing 검사가 공허하게 통과한다"
    missing = [str(src.relative_to(ROOT)) for src in SOURCE_FILES if not src.exists()]
    assert not missing, f"시험 경로 참조 대상 파일이 없음(경로 갱신 필요): {missing}"


def test_referenced_test_paths_exist_or_are_baselined():
    """각 소스가 가리키는 tests/... 경로가 실제 파일인지 — 기존 깨짐은 기준선으로 허용."""
    baseline: set[str] = set()
    if _BASELINE_PATH.exists():
        baseline = set(json.loads(_BASELINE_PATH.read_text(encoding="utf-8")))

    by_source = _all_referenced_paths()
    total_refs = sum(len(paths) for paths in by_source.values())
    assert total_refs > 0, "대상 파일에서 tests/...test_*.py 참조를 하나도 못 찾음 — PATH_RE/SOURCE_FILES 를 확인하세요"

    broken_new: dict[str, list[str]] = {}
    for source, paths in by_source.items():
        for rel in sorted(paths):
            if (ROOT / rel).exists():
                continue
            if rel in baseline:
                continue
            broken_new.setdefault(source, []).append(rel)

    assert not broken_new, (
        "새로 깨진 시험 경로 참조 발견(이동 배치에서 문자열 갱신을 빠뜨렸을 가능성):\n"
        + json.dumps(broken_new, ensure_ascii=False, indent=1)
        + "\n→ 의도된 이동이면 tests/data/test_path_refs_baseline.json 을 갱신하세요."
    )


def test_baseline_entries_are_still_actually_broken():
    """기준선에 올려 둔 경로가 사실은 이미 고쳐졌는데 목록만 안 지운 경우를 잡는다(목록 축소 유도).

    기준선 파일이 없으면(=8건 모두 해소되어 2026-10-08 삭제됨) 확인할 대상이 없으니 통과."""
    if not _BASELINE_PATH.exists():
        return
    baseline: list[str] = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    assert baseline, "기준선이 비어 있음 — 아래 stale 검사가 공허하게 통과하니 빈 상태면 이 파일 자체를 삭제하세요"
    stale = [rel for rel in baseline if (ROOT / rel).exists()]
    assert not stale, (
        "기준선의 다음 경로는 이제 실제로 존재함 — "
        "tests/data/test_path_refs_baseline.json 에서 제거하세요: " + str(stale)
    )
