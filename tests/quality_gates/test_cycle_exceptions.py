"""폴더 순환 승인 예외(configs/cycle_exceptions.json) — _cycle_pairs() 가 그 목록의 쌍을
결과에서 뺀다. tools/selector_health<->sites(2026-10-09 지휘창 승인, 플러그인 레지스트리
상호의존)는 그대로 둔 채 측정에서만 제외한다."""

from __future__ import annotations

import json

from tools.code_map import modules as M


def test_approved_pair_is_excluded_from_cycle_pairs(monkeypatch, tmp_path):
    exceptions_file = tmp_path / "cycle_exceptions.json"
    exceptions_file.write_text(
        json.dumps({"exceptions": [{"pair": ["pkg_a", "pkg_b"], "reason": "test"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(M, "CYCLE_EXCEPTIONS_FILE", exceptions_file)
    import_edges = {"pkg_a/x.py": ["pkg_b/y.py"], "pkg_b/y.py": ["pkg_a/x.py"]}
    mod = {"pkg_a/x.py": "pkg_a", "pkg_b/y.py": "pkg_b"}
    nodes = {k: {"class": "LIVE"} for k in mod}

    cycles = M._cycle_pairs(import_edges, mod, nodes)

    assert cycles == []


def test_non_approved_pair_still_reported(monkeypatch, tmp_path):
    exceptions_file = tmp_path / "cycle_exceptions.json"
    exceptions_file.write_text(
        json.dumps({"exceptions": [{"pair": ["pkg_a", "pkg_b"], "reason": "test"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(M, "CYCLE_EXCEPTIONS_FILE", exceptions_file)
    import_edges = {"pkg_c/x.py": ["pkg_d/y.py"], "pkg_d/y.py": ["pkg_c/x.py"]}
    mod = {"pkg_c/x.py": "pkg_c", "pkg_d/y.py": "pkg_d"}
    nodes = {k: {"class": "LIVE"} for k in mod}

    cycles = M._cycle_pairs(import_edges, mod, nodes)

    assert cycles == [("pkg_c", "pkg_d")]


def test_missing_exceptions_file_means_no_exceptions(monkeypatch, tmp_path):
    monkeypatch.setattr(M, "CYCLE_EXCEPTIONS_FILE", tmp_path / "does_not_exist.json")
    assert M._load_cycle_exceptions() == set()


def test_real_repo_selector_health_cycle_is_an_approved_exception():
    """실제 저장소: tools/selector_health<->sites 가 cycle_exceptions.json 에 등록돼
    _cycle_pairs() 결과(module_cycles)에서 빠지는지 — crosscheck 전체는 여기선 재측정 안 하고
    설정 파일 하나만 확인(가벼운 확인)."""
    data = json.loads(M.CYCLE_EXCEPTIONS_FILE.read_text(encoding="utf-8"))
    pairs = {tuple(sorted(e["pair"])) for e in data["exceptions"]}
    assert ("tools/selector_health", "tools/selector_health/sites") in pairs
