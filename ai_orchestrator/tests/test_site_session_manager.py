"""session_manager 및 profile path 분리 검증."""

from __future__ import annotations

import pytest

from ai_orchestrator.sites import secrets_policy, session_manager


@pytest.fixture(autouse=True)
def _isolated_secrets_root(tmp_path, monkeypatch):
    """각 테스트마다 별도 SECRETS_ROOT 로 고정 → 실제 secrets/ 오염 방지."""
    monkeypatch.setenv("SECRETS_ROOT", str(tmp_path))
    yield


def test_profile_path_is_per_site(tmp_path):
    p_naver = secrets_policy.browser_profile_dir("naver_cafe")
    p_procure = secrets_policy.browser_profile_dir("procurement")
    assert p_naver != p_procure
    # 상위가 동일한 browser_profiles 인지 확인
    assert p_naver.parent == p_procure.parent == (tmp_path / "browser_profiles")
    # 고정 경로: 같은 site_id 는 같은 디렉터리
    assert secrets_policy.browser_profile_dir("naver_cafe") == p_naver


def test_ensure_profile_dir_creates_directory():
    p = session_manager.ensure_profile_dir("example_portal")
    assert p.is_dir()


def test_invalid_site_name_rejected():
    with pytest.raises(ValueError):
        secrets_policy.browser_profile_dir("../etc/passwd")
    with pytest.raises(ValueError):
        secrets_policy.browser_profile_dir("")
    with pytest.raises(ValueError):
        secrets_policy.session_meta_path("bad name with space")


def test_meta_roundtrip_and_update():
    session_manager.clear_meta_for_tests("example_portal")
    m0 = session_manager.get_meta("example_portal")
    assert m0.status == "UNKNOWN"
    assert m0.paused_job_id == ""

    session_manager.mark_reauth_required(
        "example_portal",
        reason="redirected_to_login",
        detected_url="https://example.test/login",
        paused_job_id="job-1",
    )
    m1 = session_manager.get_meta("example_portal")
    assert m1.status == "REAUTH_REQUIRED"
    assert m1.last_reason == "redirected_to_login"
    assert m1.paused_job_id == "job-1"
    assert m1.detected_url.endswith("/login")

    session_manager.mark_reauth_success(
        "example_portal",
        detected_url="https://example.test/",
    )
    m2 = session_manager.get_meta("example_portal")
    assert m2.status == "ACTIVE"
    assert m2.paused_job_id == ""
    assert m2.last_reauth_at  # set
    assert m2.last_verified_at  # set


def test_meta_does_not_leak_to_stdout(caplog):
    """메타 갱신 로그에는 민감 원문이 남지 않아야 한다."""
    import logging

    caplog.set_level(logging.INFO, logger="ai_orchestrator.sites.session_manager")
    session_manager.mark_active(
        "example_portal",
        detected_url="https://example.test/dashboard?token=SHOULDNOTLEAK",
    )
    # detected_url 은 상태 파일엔 저장되지만 로그 메시지에는 포함시키지 않는다.
    # (update_meta 로그 포맷 확인)
    messages = [r.getMessage() for r in caplog.records]
    joined = "\n".join(messages)
    assert "SHOULDNOTLEAK" not in joined
    assert "password" not in joined.lower()
    assert "cookie" not in joined.lower()
