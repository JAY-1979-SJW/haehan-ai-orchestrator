"""모듈 분리 게이트 테스트."""
from tools.repo_gates.module_separation_gate import SEPARATED_MODULES, run_gate


def test_current_tree_passes_gate():
    """현재 작업트리는 모듈 분리 게이트를 통과해야 한다."""
    result = run_gate()
    assert not result.failed, (
        "모듈 분리 위반:\n" + "\n".join(f"[{f.category}] {f.detail}" for f in result.findings)
    )


def test_local_agent_router_registered():
    names = {m["name"] for m in SEPARATED_MODULES}
    assert "local_agent_router" in names


def test_blog_mixin_registered():
    names = {m["name"] for m in SEPARATED_MODULES}
    assert "blog_mixin" in names


def test_no_root_too_large():
    result = run_gate()
    assert result.count("ROOT_TOO_LARGE") == 0


def test_no_leaf_coupling():
    result = run_gate()
    assert result.count("LEAF_COUPLING") == 0
