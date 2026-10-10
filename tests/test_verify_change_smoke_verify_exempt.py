"""verify_change._measure_violations — tools/smoke/·tools/verify/ 스크립트는 층간 위반에서 제외.

PR165 layer-violation 조사(2026-10-10, sonnet 서브에이전트 확인): 이 스크립트들은 사람/CI 가
직접 돌리는 한번용 스모크·드라이런 진입점이라 설계상 런타임 내부를 깊이 가로질러 가져온다
(실제로 다른 코드에서 import 되지 않는다) — 층 규칙과 무관하게 항상 위반으로 잡혔다.
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


def test_smoke_script_source_is_excluded_from_violations(tmp_path):
    _write(tmp_path / "tools" / "smoke" / "some_smoke.py", "import pkg.deep\n")
    _write(tmp_path / "pkg" / "deep.py", "X = 1\n")
    _registry(tmp_path, {"tools/smoke/some_smoke.py": "L2", "pkg/deep.py": "L8"})
    m = {"import_edges": {"tools/smoke/some_smoke.py": ["pkg/deep.py"]}, "all_edges": {}}

    viol = vc._measure_violations(tmp_path, m)

    assert viol == [], f"smoke 소스인데 위반으로 잡힘: {viol}"


def test_verify_script_source_is_excluded_from_violations(tmp_path):
    _write(tmp_path / "tools" / "verify" / "some_verify.py", "import pkg.deep\n")
    _write(tmp_path / "pkg" / "deep.py", "X = 1\n")
    _registry(tmp_path, {"tools/verify/some_verify.py": "L2", "pkg/deep.py": "L8"})
    m = {"import_edges": {"tools/verify/some_verify.py": ["pkg/deep.py"]}, "all_edges": {}}

    viol = vc._measure_violations(tmp_path, m)

    assert viol == [], f"verify 소스인데 위반으로 잡힘: {viol}"


def test_non_smoke_file_with_same_edge_is_still_a_violation(tmp_path):
    """smoke/verify 가 아닌 일반 파일이 같은 모양(L2 -> L8)으로 import 하면 그대로
    위반이어야 한다(예외가 전체 판정을 꺼버리는 게 아님을 증명하는 양성 대조)."""
    _write(tmp_path / "tools" / "other" / "some_tool.py", "import pkg.deep\n")
    _write(tmp_path / "pkg" / "deep.py", "X = 1\n")
    _registry(tmp_path, {"tools/other/some_tool.py": "L2", "pkg/deep.py": "L8"})
    m = {"import_edges": {"tools/other/some_tool.py": ["pkg/deep.py"]}, "all_edges": {}}

    viol = vc._measure_violations(tmp_path, m)

    assert viol == ["tools/other/some_tool.py -> pkg/deep.py"]


def test_is_smoke_or_verify_script():
    assert vc._is_smoke_or_verify_script("tools/smoke/x.py") is True
    assert vc._is_smoke_or_verify_script("tools/verify/x.py") is True
    assert vc._is_smoke_or_verify_script("tools/other/x.py") is False
