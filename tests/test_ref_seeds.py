"""ref_seeds — 바뀐 비-.py 파일을 문자열로 읽는 .py 를 영향 시험 선별의 출발점에 더한다 (verify_change·merge_step_check 공용)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools import verify_change as vc
from tools.code_map import ref_seeds

NL = chr(10)


def _repo(tmp_path: Path, files: dict[str, str]) -> list[str]:
    for rel, body in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body + NL, encoding="utf-8")
    return sorted(files)


def test_py_that_reads_a_changed_config_by_path_is_found(tmp_path):
    tracked = [
        *_repo(
            tmp_path,
            {
                "scripts/ops/folder_gate.py": 'REGISTRY = ROOT / "configs/folder_registry.json"',
                "tests/test_unrelated.py": "x = 1",
            },
        ),
        "configs/folder_registry.json",
    ]
    got = ref_seeds.py_files_referencing_non_py(tmp_path, ["configs/folder_registry.json"], tracked)
    assert got == {"scripts/ops/folder_gate.py": ["configs/folder_registry.json"]}


def test_path_join_style_reference_matches_by_unique_file_name(tmp_path):
    tracked = [
        *_repo(tmp_path, {"tests/test_a.py": 'p = ROOT / "configs" / "dup_baseline.json"'}),
        "configs/dup_baseline.json",
    ]
    assert list(ref_seeds.py_files_referencing_non_py(tmp_path, ["configs/dup_baseline.json"], tracked)) == [
        "tests/test_a.py"
    ]


def test_ambiguous_file_name_needs_the_full_path(tmp_path):
    """package.json 처럼 이름이 여러 파일에 있으면 파일명만으로는 맞추지 않는다(전부 끌려 들어오는 것을 막는다)."""
    tracked = [
        *_repo(
            tmp_path,
            {
                "tests/test_name_only.py": 'x = "package.json"',
                "tests/test_full_path.py": 'x = "admin-web/package.json"',
            },
        ),
        "package.json",
        "admin-web/package.json",
    ]
    assert list(ref_seeds.py_files_referencing_non_py(tmp_path, ["admin-web/package.json"], tracked)) == [
        "tests/test_full_path.py"
    ]


def test_docs_images_and_py_files_are_not_targets(tmp_path):
    tracked = [
        *_repo(tmp_path, {"tests/test_a.py": 'x = "README.md" + "logo.png" + "tool.py"'}),
        "README.md",
        "logo.png",
        "tool.py",
    ]
    assert ref_seeds.py_files_referencing_non_py(tmp_path, ["README.md", "logo.png", "tool.py"], tracked) == {}


def test_seeds_for_keeps_all_changed_files_and_adds_the_readers(tmp_path):
    tracked = [
        *_repo(tmp_path, {"scripts/ops/folder_gate.py": 'R = "configs/folder_registry.json"'}),
        "configs/folder_registry.json",
    ]
    seeds = ref_seeds.seeds_for(tmp_path, ["configs/folder_registry.json", "pkg/mod.py"], tracked)
    assert seeds == ["configs/folder_registry.json", "pkg/mod.py", "scripts/ops/folder_gate.py"]


def test_verify_change_affected_tests_reaches_the_test_through_the_tool_that_reads_the_config(tmp_path, monkeypatch):
    """W3 364f4b83 사례: configs/folder_registry.json 만 바뀌어도, 그 파일을 여는 folder_gate.py 를 import 하는 test_folder_gate 가 선택된다."""
    tracked = [
        *_repo(
            tmp_path,
            {
                "scripts/ops/folder_gate.py": 'REGISTRY = "configs/folder_registry.json"',
                "tests/test_folder_gate.py": "from scripts.ops import folder_gate",
                "tests/test_other.py": "x = 1",
            },
        ),
        "configs/folder_registry.json",
    ]
    (tmp_path / "data" / "code_map").mkdir(parents=True)
    edges = {"tests/test_folder_gate.py": ["scripts/ops/folder_gate.py"]}
    (tmp_path / "data" / "code_map" / "map.json").write_text(json.dumps({"all_edges": edges}), encoding="utf-8")
    monkeypatch.setattr(vc, "ROOT", tmp_path)
    monkeypatch.setattr(
        vc, "run", lambda cmd, cwd, timeout=0: subprocess.CompletedProcess(cmd, 0, NL.join(tracked), "")
    )
    assert vc.affected_tests(["configs/folder_registry.json"]) == [
        "tests/test_folder_gate.py"
    ]  # .py 가 하나도 안 바뀌어도
    assert vc.affected_tests(["docs/a.md"]) == []  # 문서만 바뀌면 시험 없음
