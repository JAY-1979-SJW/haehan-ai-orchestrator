"""verify_change._route_check_for — 각 트리 자신의 route_check 로 라우트 수를 잰다(진입점 이름 변경 대응)."""

import json

from tools import verify_change as vc


def _tree(tmp_path, route_check):
    cfg = tmp_path / "configs"
    cfg.mkdir()
    if route_check is not None:
        (cfg / "verify_change.json").write_text(json.dumps({"route_check": route_check}), encoding="utf-8")
    return tmp_path


def test_tree_config_wins_over_current_config(tmp_path, monkeypatch):
    monkeypatch.setitem(vc.CFG, "route_check", "print('새 이름')")
    assert vc._route_check_for(_tree(tmp_path, "print('옛 이름')")) == "print('옛 이름')"


def test_falls_back_when_tree_has_no_config(tmp_path, monkeypatch):
    monkeypatch.setitem(vc.CFG, "route_check", "print(1)")
    assert vc._route_check_for(tmp_path) == "print(1)"


def test_falls_back_on_broken_json(tmp_path, monkeypatch):
    monkeypatch.setitem(vc.CFG, "route_check", "print(2)")
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "verify_change.json").write_text("{not json", encoding="utf-8")
    assert vc._route_check_for(tmp_path) == "print(2)"


def test_falls_back_when_tree_config_has_no_route_check(tmp_path, monkeypatch):
    monkeypatch.setitem(vc.CFG, "route_check", "print(3)")
    assert vc._route_check_for(_tree(tmp_path, "")) == "print(3)"


def test_measure_routes_uses_each_trees_own_command(tmp_path, monkeypatch):
    """기준 트리(옛 이름)와 변경 트리(새 이름)가 각자의 명령으로 재어져 같은 값이 나온다."""
    monkeypatch.setitem(vc.CFG, "route_check", "print('NEW-COMMAND')")
    (tmp_path / "base").mkdir()
    (tmp_path / "head").mkdir()
    base = _tree(tmp_path / "base", "print(7)")
    head = _tree(tmp_path / "head", "print(7)")
    assert vc._measure_routes(base) == "7" == vc._measure_routes(head)


def test_measure_routes_dash_when_no_check_anywhere(tmp_path, monkeypatch):
    monkeypatch.setitem(vc.CFG, "route_check", None)
    assert vc._measure_routes(tmp_path) == "-"
