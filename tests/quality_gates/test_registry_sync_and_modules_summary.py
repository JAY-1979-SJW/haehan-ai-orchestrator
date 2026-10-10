"""registry_sync(overrides 반영·낡은 override 정리)와 modules.py 요약 줄(layer_inversions total)의 회귀 시험.

2026-10-07 기준선 감사: 층간 위반이 실제 30건인데 요약 줄은 '3'(dict 키 수)으로 보였고, 원인은 paths/* L1 override 가
정본에 반영되지 않은 것(registry_sync --fix 가 기존 키의 override 변경을 무시)이었다.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.code_map import modules, registry_sync


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", check=True
    ).stdout


def _entry(layer: str = "L4", role: str = "generic", source: str = "rule") -> dict:
    return {"layer": layer, "role": role, "domain": "common", "reason": "기본", "confidence": "low", "source": source}


@pytest.fixture()
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "configs").mkdir()
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "leaf.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "pkg" / "other.py").write_text("Y = 1\n", encoding="utf-8")
    (tmp_path / "configs" / "module_registry.json").write_text(
        json.dumps(
            {"layers": {}, "files": {"pkg/leaf.py": _entry(), "pkg/other.py": _entry()}}, ensure_ascii=False, indent=1
        )
        + "\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _set_overrides(root: Path, data: dict) -> None:
    (root / "configs" / "module_registry.overrides.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def test_fix_applies_overrides_to_existing_registry_entries(repo):
    """① 이미 정본에 있는 항목도 override 를 고치면 --fix 가 반영한다(예전에는 새 파일에만 적용)."""
    _set_overrides(repo, {"pkg/leaf.py": {"layer": "L1", "role": "shared", "reason": "잎"}})
    assert registry_sync.check(repo) == 1  # 반영 안 된 override 를 --check 도 알려 준다
    assert registry_sync.fix(repo) == 0
    entry = registry_sync.load_registry(repo)["files"]["pkg/leaf.py"]
    assert (entry["layer"], entry["role"], entry["source"], entry["confidence"]) == (
        "L1",
        "shared",
        "confirmed",
        "high",
    )
    assert registry_sync.load_registry(repo)["files"]["pkg/other.py"]["layer"] == "L4"  # override 없는 항목은 그대로
    assert registry_sync.check(repo) == 0


def test_fix_removes_overrides_of_files_that_no_longer_exist(repo):
    """② 삭제·이동으로 없어진 파일의 낡은 override 는 --fix 가 지운다."""
    _set_overrides(
        repo,
        {
            "gone/old_shim.py": {"layer": "L8", "role": "api", "reason": "삭제된 shim"},
            "pkg/leaf.py": {"layer": "L1", "role": "shared"},
        },
    )
    assert registry_sync.fix(repo) == 0
    kept = registry_sync.load_overrides(repo)
    assert "gone/old_shim.py" not in kept and "pkg/leaf.py" in kept


def test_fix_is_idempotent_and_does_not_touch_entries_without_drift(repo):
    _set_overrides(repo, {"pkg/leaf.py": {"layer": "L1", "role": "shared"}})
    registry_sync.fix(repo)
    first = (repo / "configs" / "module_registry.json").read_bytes()
    registry_sync.fix(repo)
    assert (repo / "configs" / "module_registry.json").read_bytes() == first


def test_override_drift_and_stale_helpers():
    files = {"a.py": _entry(), "b.py": _entry("L1", "shared", "confirmed") | {"confidence": "high"}}
    overrides = {"a.py": {"layer": "L2"}, "b.py": {"layer": "L1", "role": "shared"}, "c.py": {"layer": "L3"}}
    assert registry_sync.override_drift(files, overrides) == ["a.py"]  # b 는 이미 반영됨, c 는 정본에 없음
    assert registry_sync.stale_overrides(overrides, {"a.py", "b.py"}) == ["c.py"]


def test_summary_line_prints_the_inversion_total_not_the_key_count():
    """③ layer_inversions 는 키 수(3)가 아니라 total 로 요약한다."""
    crosscheck = {
        "layer_inversions": {"total": 30, "by_pair": {"L7->L4": 23}, "samples": []},
        "module_cycles": [["a", "b"], ["c", "d"]],
        "forbidden_import_hits": [],
        "declared_modules": [{"name": "x"}],
        "count": 7,
    }
    out = modules._crosscheck_summary(crosscheck)
    assert out["layer_inversions"] == 30
    assert (
        out["module_cycles"] == 2
        and out["forbidden_import_hits"] == 0
        and out["declared_modules"] == 1
        and out["count"] == 7
    )


def test_summary_line_dict_without_total_still_reports_key_count():
    assert modules._crosscheck_summary({"x": {"a": 1, "b": 2}}) == {"x": 2}
