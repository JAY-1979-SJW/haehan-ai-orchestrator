"""AI 에이전트 작업 분배 P2 — 충돌 정책(순수) 시험. 기준서 2026-10-02_app_agent_dispatch §4·§6."""

from __future__ import annotations

import pytest

from ai_orchestrator.agent_dispatch import agent_dispatch_policy as pol


def T(tid, resources=None, *, read_only=False, deps=None, **kw):
    d = {"id": tid, "read_only": read_only, "depends_on": deps or []}
    if resources is not None:
        d["resources"] = resources
    d.update(kw)
    return d


def C(**kw):
    return pol.claim_of(T("x", **kw))


# ── claim_of / conflicts ────────────────────────────────────────────────
@pytest.mark.parametrize("res", ["git", "db", "server", "deploy", "delete", "permission", "secret"])
def test_global_resources_conflict_with_everything_non_free(res):
    g = pol.claim_of(T("g", [res]))
    other = pol.claim_of(T("o", ["path:C:/a"]))
    assert g.is_global
    assert pol.conflicts(g, other) and pol.conflicts(other, g)
    assert pol.conflicts(g, g)


def test_read_only_without_resources_is_free_except_against_global():
    free = pol.claim_of(T("r", [], read_only=True))
    assert free.free
    assert not pol.conflicts(free, free)
    assert not pol.conflicts(free, pol.claim_of(T("p", ["path:C:/a"])))  # 비전역 작업과는 병렬
    # 전역 직렬 작업은 읽기 전용 작업과도 동시에 돌지 않는다(기준서 §4 — 리뷰어 재현: 둘이 같이 시작됐음)
    assert pol.conflicts(free, pol.claim_of(T("g", ["git"])))
    assert pol.conflicts(pol.claim_of(T("g", ["git"])), free)


@pytest.mark.parametrize(
    "task",
    [
        T("a"),  # 자원 선언 없음
        T("b", []),  # 쓰기 작업인데 빈 선언
        T("c", ["whatever"]),  # 모르는 토큰
        T("d", ["cdp:"]),  # 빈 접두
        T("e", [1]),  # 문자열 아님
        T("f", "git"),  # 리스트 아님
        T("g", None, read_only=True),  # 읽기 전용이어도 선언 자체가 없으면 모호
    ],
)
def test_ambiguous_is_fail_closed(task):
    claim = pol.claim_of(task)
    assert claim.is_global and not claim.free


def test_exclusive_tokens_conflict_only_when_same():
    ui = pol.claim_of(T("u", ["ui"]))
    assert pol.conflicts(ui, pol.claim_of(T("u2", ["ui"])))
    assert not pol.conflicts(ui, pol.claim_of(T("p", ["path:C:/a"])))
    n1, n2 = pol.claim_of(T("n1", ["cdp:naver"])), pol.claim_of(T("n2", ["CDP:Naver"]))
    assert pol.conflicts(n1, n2)
    assert not pol.conflicts(n1, pol.claim_of(T("h", ["cdp:hanafax"])))


def test_path_overlap_by_containment_not_prefix_string():
    parent = pol.claim_of(T("p", [r"path:C:\Work\App"]))
    child = pol.claim_of(T("c", ["path:c:/work/app/src"]))
    sibling = pol.claim_of(T("s", ["path:C:/Work/AppOther"]))
    assert pol.conflicts(parent, child)
    assert not pol.conflicts(parent, sibling)


# ── validate_plan ───────────────────────────────────────────────────────
def ok(tid, **kw):
    return T(tid, ["path:C:/" + tid], **kw)


def test_valid_plan_passes():
    assert pol.validate_plan([ok("a"), ok("b", deps=["a"])]) == []


def test_validate_rejects_bad_plans():
    assert pol.validate_plan([])
    assert pol.validate_plan([ok(str(i)) for i in range(7)])  # 6개 초과
    assert pol.validate_plan([ok("a"), ok("a")])  # 중복 id
    assert pol.validate_plan([ok("a", deps=["zz"])])  # 없는 의존
    assert pol.validate_plan([ok("a", deps=["a"])])  # 자기 의존
    assert pol.validate_plan([ok("a", deps=["b"]), ok("b", deps=["a"])])  # 순환
    assert pol.validate_plan([ok("a", budget_usd=1.5)])  # 작업당 상한
    assert pol.validate_plan([ok("a", budget_usd=0)])
    assert pol.validate_plan([ok("a", timeout_sec=10)])
    assert pol.validate_plan([ok("a", timeout_sec=99999)])
    assert pol.validate_plan([ok("a", budget_usd="x")])


def test_total_budget_cap():
    six = [ok(str(i), budget_usd=1.0) for i in range(6)]
    assert pol.validate_plan(six) == []  # 6 x 1.0 = 6.0 (경계 허용)
    six[0]["budget_usd"] = 1.0
    assert pol.validate_plan([*six[:5], ok("z", budget_usd=1.0)]) == []


# ── next_step / preview_waves ───────────────────────────────────────────
def states(**kw):
    return dict(kw)


def test_parallel_when_independent_and_cap_respected():
    tasks = [ok("a"), ok("b"), ok("c")]
    start, skipped = pol.next_step(tasks, {}, max_parallel=2)
    assert start == ["a", "b"] and skipped == []
    start, _ = pol.next_step(tasks, {"a": pol.RUNNING, "b": pol.RUNNING}, max_parallel=2)
    assert start == []
    start, _ = pol.next_step(tasks, {"a": pol.DONE, "b": pol.RUNNING}, max_parallel=2)
    assert start == ["c"]


def test_global_task_runs_alone():
    tasks = [ok("a"), T("g", ["git"]), ok("b")]
    start, _ = pol.next_step(tasks, {}, max_parallel=3)
    assert start == ["a", "b"]  # g 는 a 와 충돌해 대기, 무관한 b 는 a 와 동시 시작
    assert pol.next_step(tasks, {"a": pol.DONE, "b": pol.DONE}, 3)[0] == ["g"]
    assert pol.next_step(tasks, {"a": pol.DONE, "b": pol.RUNNING}, 3)[0] == []  # b 실행 중이면 g 대기
    assert pol.next_step(tasks, {"a": pol.DONE, "b": pol.DONE, "g": pol.RUNNING}, 3)[0] == []
    assert pol.next_step(tasks, {"a": pol.DONE, "b": pol.DONE, "g": pol.DONE}, 3)[0] == []


def test_ui_tasks_serialized_but_read_only_free():
    tasks = [T("u1", ["ui"]), T("u2", ["ui"]), T("r", [], read_only=True)]
    assert pol.next_step(tasks, {}, 3)[0] == ["u1", "r"]


def test_dependency_and_cascade_skip():
    tasks = [ok("a"), ok("b", deps=["a"]), ok("c", deps=["b"]), ok("d")]
    start, skipped = pol.next_step(tasks, {"a": pol.FAILED}, 3)
    assert skipped == ["b"] and start == ["d"]
    start, skipped = pol.next_step(tasks, {"a": pol.FAILED, "b": pol.SKIPPED}, 3)
    assert skipped == ["c"]


def test_parallel_cap_is_clamped():
    assert pol.clamp_parallel(99) == 3
    assert pol.clamp_parallel(0) == 1
    assert pol.clamp_parallel("x") == pol.DEFAULT_PARALLEL
    tasks = [ok(str(i)) for i in range(5)]
    assert len(pol.next_step(tasks, {}, 99)[0]) == 3


def test_preview_waves():
    tasks = [ok("a"), ok("b"), T("g", ["deploy"], deps=["a", "b"]), ok("c", deps=["g"])]
    assert pol.preview_waves(tasks, 2) == [["a", "b"], ["g"], ["c"]]
    assert pol.preview_waves([ok("a"), ok("b")], 1) == [["a"], ["b"]]


def test_global_task_never_overlaps_read_only_in_scheduler():
    r = T("r", [], read_only=True)
    g = T("g", ["git"])
    assert pol.next_step([r, g], {}, 3)[0] == ["r"]  # g 는 r 이 도는 동안 시작하지 않는다
    assert pol.next_step([g, r], {}, 3)[0] == ["g"]  # g 가 시작되면 r 은 대기
    assert pol.next_step([g, r], {"g": pol.RUNNING}, 3)[0] == []
    assert pol.next_step([r, g], {"r": pol.RUNNING}, 3)[0] == []
    assert pol.next_step([r, g], {"r": pol.DONE}, 3)[0] == ["g"]
