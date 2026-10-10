"""verify_change._measure_violations — 호환 shim 파일(`# haehan-shim:`)은 층간 위반에서 제외.

PR #165 CI 분석(2026-10-09, backup\\ci165_analysis_W4.md): shim 은 메커니즘상 항상 "낮은 층
shim 파일 → 실제(보통 더 높은 층) 모듈"을 import 해 층 규칙과 무관하게 위반으로 잡혔다
(실측 10건 전부 shim 패턴). 코드를 고칠 게 아니라 측정 자체에서 shim 을 빼야 한다.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.ops import verify_change as vc


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _registry(tmp_path: Path, files: dict[str, str]) -> None:
    reg = {
        "layers": {},
        "allowed_note": "",
        "allowed_deps": {"L2": ["L1", "L2"], "L8": ["L1", "L2", "L8"]},
        "files": {p: {"layer": layer} for p, layer in files.items()},
    }
    _write(tmp_path / "configs" / "module_registry.json", json.dumps(reg, ensure_ascii=False))


def test_shim_file_source_is_excluded_from_violations(tmp_path):
    _write(
        tmp_path / "pkg" / "old_router.py",
        "# haehan-shim: pkg.new.router\n# 호환 shim\nimport importlib\n",
    )
    _write(tmp_path / "pkg" / "new" / "router.py", "X = 1\n")
    _registry(tmp_path, {"pkg/old_router.py": "L2", "pkg/new/router.py": "L8"})
    m = {"import_edges": {"pkg/old_router.py": ["pkg/new/router.py"]}, "all_edges": {}}

    viol = vc._measure_violations(tmp_path, m)

    assert viol == [], f"shim 소스인데 위반으로 잡힘: {viol}"


def test_non_shim_file_with_same_edge_is_still_a_violation(tmp_path):
    """shim 이 아닌 일반 파일이 같은 모양(L2 -> L8)으로 import 하면 그대로 위반이어야 한다
    (shim 예외가 전체 판정을 꺼버리는 게 아님을 증명하는 양성 대조)."""
    _write(tmp_path / "pkg" / "old_router.py", "import pkg.new.router\n")  # shim 마커 없음
    _write(tmp_path / "pkg" / "new" / "router.py", "X = 1\n")
    _registry(tmp_path, {"pkg/old_router.py": "L2", "pkg/new/router.py": "L8"})
    m = {"import_edges": {"pkg/old_router.py": ["pkg/new/router.py"]}, "all_edges": {}}

    viol = vc._measure_violations(tmp_path, m)

    assert viol == ["pkg/old_router.py -> pkg/new/router.py"]


def test_is_shim_file_requires_marker_on_first_line(tmp_path):
    _write(tmp_path / "a.py", "X = 1\n# haehan-shim: not first line\n")
    assert vc._is_shim_file(tmp_path, "a.py") is False


def test_is_shim_file_true_for_real_shim_marker(tmp_path):
    _write(tmp_path / "a.py", "# haehan-shim: pkg.b\nimport importlib\n")
    assert vc._is_shim_file(tmp_path, "a.py") is True


def test_is_shim_file_missing_file_returns_false(tmp_path):
    assert vc._is_shim_file(tmp_path, "nope.py") is False
