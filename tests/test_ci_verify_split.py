"""ci.yml — verify 를 refs · verify-static · verify-tests(matrix) · verify(최종 판정)로 나눈 구조를 고정한다.

필수 검사 이름 `verify` 는 그대로 남고(브랜치 보호), 시험 묶음이 하나라도 빠지면 최종 판정이 FAIL 해야 한다.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _run_text(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in job["steps"])


def test_final_job_is_still_named_verify_and_waits_for_every_part():
    jobs = _jobs()
    assert {"refs", "verify-static", "verify-tests", "verify"} <= set(jobs)
    assert set(jobs["verify"]["needs"]) == {"refs", "verify-static", "verify-tests"}
    assert "always()" in str(jobs["verify"]["if"])  # 앞선 job 이 실패해도 최종 job 이 돌아 실패를 드러낸다


def test_final_job_fails_unless_static_and_tests_succeeded():
    run = _run_text(_jobs()["verify"])
    assert "needs.verify-static.result" in str(_jobs()["verify"]["steps"][0]["env"]) and "exit 1" in run


def test_shard_count_matches_between_matrix_tests_command_and_report():
    jobs = _jobs()
    shards = jobs["verify-tests"]["strategy"]["matrix"]["shard"]
    count = len(shards)
    assert shards == list(range(1, count + 1))
    tests_cmd = _run_text(jobs["verify-tests"])
    assert f"--shard ${{{{ matrix.shard }}}}/{count}" in tests_cmd
    report_cmd = _run_text(jobs["verify"])
    assert (
        len(re.findall(r"verify-tests-\d/verify_tests_\d\.json", report_cmd)) == count
    )  # 보고 단계가 모든 묶음 결과를 받는다


def test_static_job_runs_the_static_phase_and_gates_stay_in_it():
    jobs = _jobs()
    static_cmd = _run_text(jobs["verify-static"])
    assert "--phase static" in static_cmd and "--phase tests" not in static_cmd
    for gate in (
        "folder_gate.py --check-all",
        "tool_home_gate.py --check-all",
        "dup_gate.py check --all",
        "root_calc_gate.py --check-diff",
    ):
        assert gate in static_cmd  # 게이트 단계는 약해지지 않고 그대로 남는다
    others = {name: job for name, job in jobs.items() if name != "refs"}
    assert "steps.refs" not in yaml.safe_dump(
        others
    )  # base/head 는 refs job 의 출력만 쓴다(옛 steps.refs 참조가 남으면 빈 값이 된다)


def test_base_head_come_from_the_refs_job_everywhere():
    jobs = _jobs()
    for name in ("verify-static", "verify-tests", "verify"):
        assert "needs.refs.outputs.base" in _run_text(jobs[name]) and "needs.refs.outputs.head" in _run_text(jobs[name])
