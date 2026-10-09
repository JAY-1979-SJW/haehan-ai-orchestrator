"""층 역전(_find_layer_inversions) — `# haehan-shim:` 호환 파일은 제외한다(2026-10-09).

shim 은 메커니즘상 항상 "낮은 층 shim → 실제(보통 더 높은 층) 모듈"을 가리켜 역전으로 잡힌다
(실측 10건 전부 이 패턴이었음 — verify_change.py·tool_home_gate.py 의 같은 종류 판정에서
이미 제외한 것과 같은 수정)."""

from __future__ import annotations

from pathlib import Path

from tools.code_map import modules as M

ALLOWED = {"L2": ["L1", "L2"], "L8": ["L1", "L2", "L8"]}
LAYER = {"pkg/old_router.py": ("L2", "x"), "pkg/new/router.py": ("L8", "x")}


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_shim_source_is_excluded_from_layer_inversions(tmp_path, monkeypatch):
    _write(tmp_path / "pkg" / "old_router.py", "# haehan-shim: pkg.new.router\nimport importlib\n")
    monkeypatch.setattr(M, "ROOT", tmp_path)

    inv_pairs, inv_samples = M._find_layer_inversions(
        {"pkg/old_router.py": ["pkg/new/router.py"]},
        LAYER,
        ALLOWED,
    )

    assert inv_pairs.total() == 0
    assert inv_samples == {}


def test_non_shim_file_with_same_edge_is_still_an_inversion(tmp_path, monkeypatch):
    """shim 예외가 전체 판정을 꺼버리는 게 아님을 증명하는 양성 대조."""
    _write(tmp_path / "pkg" / "old_router.py", "import pkg.new.router\n")  # shim 마커 없음
    monkeypatch.setattr(M, "ROOT", tmp_path)

    inv_pairs, inv_samples = M._find_layer_inversions(
        {"pkg/old_router.py": ["pkg/new/router.py"]},
        LAYER,
        ALLOWED,
    )

    assert inv_pairs == {"L2->L8": 1}
    assert inv_samples == {"L2->L8": ["pkg/old_router.py -> pkg/new/router.py"]}


def test_is_shim_file_requires_marker_on_first_line(tmp_path, monkeypatch):
    _write(tmp_path / "a.py", "X = 1\n# haehan-shim: not first line\n")
    monkeypatch.setattr(M, "ROOT", tmp_path)
    assert M._is_shim_file("a.py") is False


def test_is_shim_file_missing_file_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "ROOT", tmp_path)
    assert M._is_shim_file("nope.py") is False
