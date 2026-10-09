"""tools/write_gates/duplicate_impl_gate.py 단위 테스트 (모듈 직접 호출)."""

from __future__ import annotations

from tools.write_gates import duplicate_impl_gate as gate


def test_is_automation_path_relative():
    assert gate.is_automation_path("scripts/naver/blog/new_file.py")
    assert gate.is_automation_path("ai_orchestrator/connectors/new_router.py")
    assert not gate.is_automation_path("tests/test_foo.py")


def test_is_automation_path_absolute():
    assert gate.is_automation_path(r"C:\work\01. haehan-ai-orchestrator\scripts\naver\blog\new_file.py")
    assert not gate.is_automation_path(r"C:\work\01. haehan-ai-orchestrator\tests\test_foo.py")


def test_extract_keywords_skips_common_parts():
    keywords = gate.extract_keywords("scripts/naver/cafe/new_helper.py")
    assert "cafe" in keywords
    assert "scripts" not in keywords
    assert "naver" not in keywords


def test_check_skips_non_automation_path():
    assert gate.check("tests/test_foo.py", "") is None


def test_check_skips_existing_file():
    # 이 훅 파일 자신은 실제로 존재하므로 신규 파일 검사를 건너뛰어야 한다
    existing = "scripts/naver/blog/core/writer.py"
    assert gate.check(existing, "") is None
