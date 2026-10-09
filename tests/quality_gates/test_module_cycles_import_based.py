"""폴더 순환 측정 — 실제 import 기준, 조상 __init__ 암묵 간선 제외(2026-10-07 대표님 승인).

예전에는 all_edges(경로 문자열 언급 포함)로 재서 '문자열로만 서로 언급하는' 폴더 쌍이 순환으로 잡혔고, a/b/c.py 를 import 하면 a/__init__.py 도 실행된다는
암묵 간선이 상위↔하위 폴더 순환을 만들었다. 층간 위반(import_edges 기준)과 같은 기준으로 맞췄다. 실제 import 순환은 그대로 검출된다.
"""

from __future__ import annotations

from tools.code_map import modules as M


def _mod(files: list[str]) -> dict[str, str]:
    return {f: M.module_of(f) for f in files}


def _nodes(files: list[str]) -> dict[str, dict]:
    return {f: {"class": "LIVE"} for f in files}


def _pairs(import_edges: dict) -> list[tuple[str, str]]:
    files = sorted({*import_edges, *(t for ts in import_edges.values() for t in ts)})
    return M._cycle_pairs(import_edges, _mod(files), _nodes(files))


def test_real_import_cycle_between_two_folders_is_still_detected():
    """③ 실제 import 순환(a→b, b→a)은 그대로 검출한다."""
    cycles = _pairs({"pkg_a/x.py": ["pkg_b/y.py"], "pkg_b/y.py": ["pkg_a/x.py"]})
    assert cycles == [("pkg_a", "pkg_b")]


def test_one_way_dependency_is_not_a_cycle():
    assert _pairs({"pkg_a/x.py": ["pkg_b/y.py"], "pkg_b/y.py": []}) == []


def test_pair_that_only_mentions_each_other_by_path_string_is_not_a_cycle():
    """① 문자열 경로 언급만 있는 쌍은 순환이 아니다 — import_edges 에는 한쪽 방향만 있고, 반대쪽은 all_edges 에만(문자열 언급) 있다."""
    import_edges = {"tool_a/run.py": ["tool_b/impl.py"], "tool_b/impl.py": []}
    all_edges = {
        "tool_a/run.py": ["tool_b/impl.py"],
        "tool_b/impl.py": ["tool_a/run.py"],
    }  # impl 이 run.py 를 문자열로만 언급
    files = sorted(all_edges)
    # 예전 방식(all_edges)이면 순환으로 잡혔을 구성
    acc_old: dict = M.defaultdict(M._make_module_accumulator)
    M._accumulate_module_edges(all_edges, _mod(files), _nodes(files), acc_old)
    assert M._module_edges_and_cycles(acc_old)[1] == [("tool_a", "tool_b")]
    # 새 방식(import_edges)에서는 순환이 아니다
    assert M._cycle_pairs(import_edges, _mod(files), _nodes(files)) == []


def test_implicit_ancestor_init_edge_does_not_create_a_parent_child_cycle():
    """② 하위 모듈이 상위 패키지 __init__ 으로 가는 암묵 간선(+ 상위가 하위를 import)은 순환이 아니다."""
    import_edges = {
        "pkg/sub/mod.py": ["pkg/__init__.py"],  # pkg.sub.mod 를 import 하면 pkg/__init__.py 도 실행되는 암묵 간선
        "pkg/runner.py": ["pkg/sub/mod.py"],
        "pkg/__init__.py": ["pkg/runner.py"],  # 상위 init 이 하위를 재수출
    }
    assert _pairs(import_edges) == []


def test_explicit_import_of_a_non_ancestor_init_still_counts():
    """조상이 아닌 다른 패키지의 __init__ 로 가는 import 는 의존이다 — 반대쪽 의존과 함께 순환으로 잡힌다."""
    assert _pairs({"a/x.py": ["b/__init__.py"], "b/y.py": ["a/x.py"]}) == [("a", "b")]


def test_ancestor_init_helper_cases():
    f = M._is_ancestor_init_edge
    assert f("pkg/sub/mod.py", "pkg/__init__.py")  # 조상
    assert f("pkg/sub/mod.py", "pkg/sub/__init__.py")  # 같은 패키지
    assert f("a/b/c/d.py", "a/__init__.py")  # 먼 조상
    assert not f("pkg/sub/mod.py", "other/__init__.py")  # 조상이 아님
    assert not f("pkg2/x.py", "pkg/__init__.py")  # 이름이 접두사로만 같음
    assert not f("pkg/sub/mod.py", "pkg/other.py")  # __init__ 아님
    assert not f("top.py", "__init__.py")  # 저장소 루트는 대상 아님


def test_cycle_edges_drops_only_ancestor_init_targets():
    edges = {"pkg/sub/mod.py": ["pkg/__init__.py", "pkg/other.py", "elsewhere/__init__.py"]}
    assert M._cycle_edges(edges) == {"pkg/sub/mod.py": ["pkg/other.py", "elsewhere/__init__.py"]}
