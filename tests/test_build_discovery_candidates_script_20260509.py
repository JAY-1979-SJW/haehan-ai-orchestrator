"""build_discovery_candidates_from_fixture 스크립트 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from build_discovery_candidates_from_fixture import (
    load_fixture, build_candidates, _BUILTIN_FIXTURES,
)


def test_g2b_builtin_fixture_loaded():
    items = load_fixture("g2b", None)
    assert len(items) > 0


def test_hometax_builtin_fixture_loaded():
    items = load_fixture("hometax", None)
    assert len(items) > 0


def test_mss_builtin_fixture_loaded():
    items = load_fixture("mss", None)
    assert len(items) > 0


def test_unknown_site_returns_empty():
    items = load_fixture("nonexistent_xyz", None)
    assert items == []


def test_g2b_candidates_all_ok():
    items = load_fixture("g2b", None)
    results = build_candidates("g2b", items)
    assert all(r.get("ok") for r in results)


def test_candidates_have_selector_fingerprint():
    items = load_fixture("g2b", None)
    results = build_candidates("g2b", items)
    for r in results:
        c = r.get("candidate", {})
        fp = c.get("selector_fingerprint", "")
        assert len(fp) == 16, f"fingerprint 길이 오류: {fp!r}"


def test_candidates_source_site_id_set():
    items = load_fixture("g2b", None)
    results = build_candidates("g2b", items)
    for r in results:
        assert r["candidate"]["source_site_id"] == "g2b"
