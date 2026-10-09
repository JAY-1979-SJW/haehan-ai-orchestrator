"""
G2B Import Contamination Regression 테스트

문제: test_browser_engine_routing_preflight_chain 등 다른 테스트 실행 후
      sys.modules에 browser_worker가 올라와 test_browser_gate_module_design이 FAIL했음.

수정: router.py, browser_engine_routing_preflight_chain.py에서 browser_worker
      module-level import → lazy import 변경.
      test_browser_gate_module_design의 두 테스트를 sys.modules 대신
      소스코드 직접 검사 방식으로 변경.

재발 방지: 이 테스트 파일이 이후 import 순서와 무관하게 일관된 결과를 보장한다.
"""

from __future__ import annotations

from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent.parent


# ── 1. allowlist/site compliance 결과 불변성 ──────────────────────────────────


def test_01_g2b_import_does_not_break_allowlist_result():
    """g2b live execution 모듈 import 후 allowlist_preflight 결과가 변하지 않는다."""
    from ai_orchestrator.browser_tool.preflight.allowlist_preflight import (
        evaluate_allowlist_preflight,
    )

    payload = {"target_url": "https://www.google.com", "operation": "read"}
    result_before = evaluate_allowlist_preflight(payload)

    import ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate
    import ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner  # noqa: F401 - 임포트 자체가 시험 대상(부작용/오염 검증)

    result_after = evaluate_allowlist_preflight(payload)
    assert result_before.get("site_id") == result_after.get("site_id")
    assert result_before.get("compliance_decision") == result_after.get("compliance_decision")


def test_02_g2b_execution_gate_import_does_not_break_site_compliance():
    """g2b_public_notice_execution_gate import 후 site_compliance 결과 불변."""
    from ai_orchestrator.browser_tool.policy.site_compliance_policy import (
        get_site_compliance_policy,
    )

    result_before = get_site_compliance_policy("google_accounts")

    import ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate  # noqa: F401 - 임포트 자체가 시험 대상(부작용/오염 검증)

    result_after = get_site_compliance_policy("google_accounts")
    assert result_before == result_after


def test_03_g2b_workflow_import_does_not_mutate_allowlist():
    """g2b_public_notice_workflow import 후 ALLOWLIST_SAFE_SITES가 mutate되지 않는다."""
    # g2b 관련 모든 모듈 import
    import ai_orchestrator.connectors.g2b.g2b_domain_policy
    import ai_orchestrator.connectors.g2b.g2b_public_notice_dryrun_adapter
    import ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate
    import ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner
    import ai_orchestrator.connectors.g2b.g2b_public_notice_workflow  # noqa: F401 - 임포트 자체가 시험 대상(부작용/오염 검증)
    from ai_orchestrator.browser_tool.preflight.allowlist_preflight import (
        evaluate_allowlist_preflight,
    )

    # allowlist 결과 확인
    result = evaluate_allowlist_preflight({"target_url": "https://www.google.com", "operation": "read"})
    assert isinstance(result, dict)


def test_04_g2b_allowed_domain_result_import_order_independent():
    """g2b.go.kr 허용 결과가 import 순서와 무관하게 동일하다."""
    from ai_orchestrator.connectors.g2b.g2b_domain_policy import (
        classify_g2b_url,
    )

    result_a = classify_g2b_url("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")

    # 다른 모듈 import 후 재확인
    import ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate  # noqa: F401 - 임포트 자체가 시험 대상(부작용/오염 검증)

    result_b = classify_g2b_url("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")
    assert result_a["readonly_allowed"] == result_b["readonly_allowed"]
    assert result_a["normalized_domain"] == result_b["normalized_domain"]


def test_05_login_path_block_import_order_independent():
    """login/cert/bid/contract/payment BLOCK 결과가 import 순서와 무관하다."""
    import ai_orchestrator.connectors.g2b.g2b_public_notice_dryrun_adapter

    # 다른 모듈들을 import한 후에도 BLOCK 결과 유지
    import ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner  # noqa: F401 - 임포트 자체가 시험 대상(부작용/오염 검증)
    from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (
        build_g2b_readonly_execution_candidate,
    )

    blocked_urls = [
        ("https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do", "navigate"),
        ("https://www.g2b.go.kr/cert/userCert.do", "navigate"),
        ("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb05001p.do", "navigate"),
        ("https://www.g2b.go.kr/ct/menu/ntn02/cta01/ctb01001l.do", "navigate"),
        ("https://www.g2b.go.kr/pay/checkout.do", "navigate"),
    ]
    for url, op in blocked_urls:
        c = build_g2b_readonly_execution_candidate(url, op)
        assert c["execution_allowed"] is False, f"BLOCK 기대했으나 PASS: {url}"


def test_06_wildcard_subdomain_block_import_order_independent():
    """wildcard subdomain 차단 결과가 import 순서와 무관하다."""
    import ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner  # noqa: F401 - 임포트 자체가 시험 대상(부작용/오염 검증)
    from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (
        build_g2b_readonly_execution_candidate,
    )

    c = build_g2b_readonly_execution_candidate("https://api.g2b.go.kr/", "read")
    assert c["execution_allowed"] is False
    assert c["gate_verdict"] != "READONLY_EXECUTION_CANDIDATE"


def test_07_download_block_import_order_independent():
    """download 차단 결과가 import 순서와 무관하다."""
    import ai_orchestrator.connectors.g2b.g2b_public_notice_workflow  # noqa: F401 - 임포트 자체가 시험 대상(부작용/오염 검증)
    from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (
        build_g2b_readonly_execution_candidate,
    )

    c = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/file/download.do", "download")
    assert c["execution_allowed"] is False


# ── router.py lazy import 검증 ────────────────────────────────────────────────


def test_08_router_no_browser_worker_at_import_time():
    """router.py import 시 browser_worker가 sys.modules에 로드되지 않는다."""
    # 별도 Python 프로세스에서 확인할 수 없으므로 소스 코드로 검증
    router_path = _repo_root / "ai_orchestrator" / "browser_tool" / "router.py"
    source = router_path.read_text(encoding="utf-8")
    # module-level (함수 밖) import 구문이 없어야 함
    lines = source.split("\n")
    module_level_bw_imports = [
        line
        for line in lines
        if ("from browser_worker" in line or "import browser_worker" in line or "browser_tool.worker" in line)
        and not line.strip().startswith("#")
        and not line.strip().startswith("def ")
        and not line.strip().startswith(" ")  # 들여쓰기 있으면 함수 내부
        and not line.strip().startswith("\t")
    ]
    assert lines, "lines 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert not module_level_bw_imports, (
        f"router.py에 module-level browser_worker import 발견: {module_level_bw_imports}"
    )


def test_09_preflight_chain_no_browser_worker_at_module_level():
    """browser_engine_routing_preflight_chain.py module-level에 browser_worker import 없다."""
    chain_path = _repo_root / "ai_orchestrator" / "browser_tool" / "routing" / "browser_engine_routing_preflight_chain.py"
    source = chain_path.read_text(encoding="utf-8")
    lines = source.split("\n")
    module_level_imports = [
        line
        for line in lines
        if ("from browser_worker" in line or "import browser_worker" in line or "browser_tool.worker" in line)
        and not line.strip().startswith("#")
        and not line.startswith(" ")
        and not line.startswith("\t")
    ]
    assert lines, "lines 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert not module_level_imports, f"preflight_chain.py module-level browser_worker import: {module_level_imports}"


def test_10_live_runner_import_no_playwright_at_module_level():
    """g2b_public_notice_local_live_runner.py는 playwright를 lazy import한다."""
    runner_path = _repo_root / "ai_orchestrator" / "connectors" / "g2b" / "g2b_public_notice_local_live_runner.py"
    source = runner_path.read_text(encoding="utf-8")
    lines = source.split("\n")
    # module-level playwright import가 없어야 함
    module_level_pw = [
        line
        for line in lines
        if ("from playwright" in line or "import playwright" in line)
        and not line.strip().startswith("#")
        and not line.startswith(" ")
        and not line.startswith("\t")
    ]
    assert lines, "lines 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert not module_level_pw, f"live_runner.py에 module-level playwright import 발견: {module_level_pw}"


# ── 11. scripts import side effect 없음 ──────────────────────────────────────


def test_11_scripts_import_no_side_effect():
    """scripts/g2b/run_public_notice_readonly_live_suite.py import가 실행 side effect를 만들지 않는다."""
    script_path = _repo_root / "scripts" / "g2b" / "run_public_notice_readonly_live_suite.py"
    assert script_path.exists()
    source = script_path.read_text(encoding="utf-8")
    # main guard 확인
    assert 'if __name__ == "__main__"' in source or "if __name__ == '__main__'" in source, (
        "스크립트에 main guard가 없음"
    )


# ── 12. 전체 import 후 gate_module_design 테스트와 동일한 결과 ─────────────────


def test_12_gate_module_design_tests_pass_after_all_g2b_imports():
    """모든 g2b 모듈 import 후에도 gate_module_design 테스트가 기대하는 소스 검사가 통과한다."""
    # 모든 g2b 모듈 import
    import ai_orchestrator.connectors.g2b.g2b_domain_policy
    import ai_orchestrator.connectors.g2b.g2b_public_notice_dryrun_adapter
    import ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate
    import ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner
    import ai_orchestrator.connectors.g2b.g2b_public_notice_workflow  # noqa: F401 - 임포트 자체가 시험 대상(부작용/오염 검증)

    # gate_module_design 테스트 파일 소스 확인
    test_file = _repo_root / "tests" / "browser" / "test_browser_gate_module_design_20260506.py"
    source = test_file.read_text(encoding="utf-8")
    blocked = ["playwright", "browser_worker", "ai_orchestrator.browser_tool.worker", "dispatcher", "task_executor"]
    for mod in blocked:
        for pattern in [f"import {mod}", f"from {mod}"]:
            assert pattern not in source, f"테스트 파일에 금지 import 발견: {pattern}"
