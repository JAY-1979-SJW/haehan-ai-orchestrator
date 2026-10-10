"""코드맵 — 실행 문장이 없는 __init__.py 는 부모 패키지 의존 간선에서 제외한다(2026-10-07 대표님 승인).

배경: `from ai_orchestrator.paths.runtime import x` 처럼 하위 모듈을 import 하면 부모 패키지의 __init__.py 도 실행되므로
코드맵은 부모 init 로 가는 간선을 세었다. 그런데 ai_orchestrator/__init__.py 는 0바이트(빈 파일)라 실행되는 것이 없다.
이 가짜 간선 때문에 `ai_orchestrator <-> 하위 폴더` 순환이 늘어나 CI 순환 게이트가 FAIL 했다.
범위는 최소: AST 로 본 Module.body 가 비었거나 docstring 만 있는 __init__ 만 제외한다. 실행 코드가 있으면 기존대로 간선을 유지한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.code_map.reach import Resolver

from tools.code_map import modules, scan

FILES = [
    "pkg/__init__.py",
    "pkg/sub/__init__.py",
    "pkg/sub/mod.py",
    "user.py",
]


@pytest.fixture
def tree(tmp_path: Path, monkeypatch):
    """scan._read 가 읽는 저장소 루트를 임시 폴더로 돌려, 실제 파일 내용으로 init 를 판정하게 한다."""
    monkeypatch.setattr(scan, "ROOT", tmp_path)

    def make(pkg_init: str, sub_init: str = "") -> Resolver:
        for rel in FILES:
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "pkg/__init__.py").write_text(pkg_init, encoding="utf-8")
        (tmp_path / "pkg/sub/__init__.py").write_text(sub_init, encoding="utf-8")
        (tmp_path / "pkg/sub/mod.py").write_text("X = 1\n", encoding="utf-8")
        (tmp_path / "user.py").write_text("from pkg.sub.mod import X\n", encoding="utf-8")
        return Resolver(FILES)

    return make


def _targets(res: Resolver) -> set[str]:
    targets, status = res.resolve_import("user.py", "pkg.sub.mod", 0, ("X",))
    assert status == "internal"
    return set(targets)


def test_empty_and_docstring_only_init_are_not_dependency_edges(tree):
    """① 빈 __init__.py 와 docstring/주석만 있는 __init__.py 는 부모 간선에서 제외된다."""
    res = tree("", '"""설명만 있는 패키지."""\n# 주석\n')
    got = _targets(res)
    assert "pkg/sub/mod.py" in got  # 실제 대상은 그대로
    assert "pkg/__init__.py" not in got and "pkg/sub/__init__.py" not in got


@pytest.mark.parametrize(
    "executable_init",
    [
        "import os\n",  # import
        "VALUE = 1\n",  # 대입
        "from __future__ import annotations\n",  # future import 도 실행 문장으로 본다(보수적)
        '"""설명"""\nregister()\n',  # docstring 뒤 호출
    ],
)
def test_init_with_executable_code_keeps_its_edge(tree, executable_init):
    """② 실행 코드가 있는 __init__.py 는 기존처럼 부모 간선을 유지한다."""
    res = tree(executable_init, "")
    got = _targets(res)
    assert "pkg/__init__.py" in got
    assert "pkg/sub/__init__.py" not in got  # 빈 init 는 여전히 제외


def test_unreadable_or_broken_init_is_kept_conservatively(tree, tmp_path):
    """읽거나 파싱할 수 없으면 간선을 유지한다(제외하지 않는다)."""
    res = tree("def broken(:\n", "")
    assert "pkg/__init__.py" in _targets(res)


def test_real_two_way_dependency_is_still_a_cycle():
    """③ 이 보정은 init 간선만 다룬다 — 두 모듈이 서로 import 하는 실제 순환은 그대로 검출된다."""
    acc = {name: modules._make_module_accumulator() for name in ("a", "b", "c")}
    acc["a"]["out"]["b"] += 1  # a -> b
    acc["b"]["out"]["a"] += 1  # b -> a  (실제 양방향)
    acc["c"]["out"]["a"] += 1  # c -> a  (한 방향이라 순환 아님)
    _edges, cycles = modules._module_edges_and_cycles(acc)
    assert cycles == [("a", "b")]


def test_real_repo_ai_orchestrator_init_is_inert():
    """이 저장소의 ai_orchestrator/__init__.py 는 빈 파일이라 부모 간선에서 제외 대상이다(보정의 동기)."""
    real = Path(__file__).resolve().parents[2] / "ai_orchestrator" / "__init__.py"
    assert real.exists() and real.read_text(encoding="utf-8").strip() == ""
    res = Resolver(
        ["ai_orchestrator/__init__.py", "ai_orchestrator/paths/__init__.py", "ai_orchestrator/paths/runtime.py"]
    )
    assert res._inert_init("ai_orchestrator/__init__.py") is True
