"""폴더 순환(_cycle_edges) — `# haehan-shim:` 호환 파일에서 나가는 간선은 제외한다
(2026-10-09). shim 은 메커니즘상 항상 "옛 폴더 shim → 실제 폴더"를 가리켜 가짜 순환을
만든다(실측 8건 중 7건이 이 패턴 — _find_layer_inversions 와 같은 수정)."""

from __future__ import annotations

from tools.code_map import modules as M


def test_shim_source_edge_is_excluded_from_cycle_edges(monkeypatch):
    import_edges = {
        "pkg_a/real.py": ["pkg_b/real.py"],
        "pkg_b/shim.py": ["pkg_a/real.py"],
    }
    monkeypatch.setattr(M, "_is_shim_file", lambda s: s == "pkg_b/shim.py")

    edges = M._cycle_edges(import_edges)

    assert "pkg_b/shim.py" not in edges
    assert edges["pkg_a/real.py"] == ["pkg_b/real.py"]


def test_non_shim_edges_still_make_a_cycle(monkeypatch):
    import_edges = {
        "pkg_a/real.py": ["pkg_b/real.py"],
        "pkg_b/real2.py": ["pkg_a/real.py"],
    }
    monkeypatch.setattr(M, "_is_shim_file", lambda s: False)

    edges = M._cycle_edges(import_edges)
    mod = {"pkg_a/real.py": "pkg_a", "pkg_b/real.py": "pkg_b", "pkg_b/real2.py": "pkg_b"}
    nodes = {k: {"class": "LIVE"} for k in mod}

    cycles = M._cycle_pairs(edges, mod, nodes)

    assert cycles == [("pkg_a", "pkg_b")]
