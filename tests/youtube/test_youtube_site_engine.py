"""YouTube site_engine 연결 테스트."""
from __future__ import annotations


def test_youtube_profile_import():
    from scripts.youtube.site_profile import YOUTUBE_PROFILE
    assert YOUTUBE_PROFILE.key == "youtube"


def test_upload_action_approval_required():
    from scripts.site_engine.site_types import SiteCapability
    from scripts.youtube.site_profile import YOUTUBE_PROFILE
    policy = YOUTUBE_PROFILE.action_policies.get(SiteCapability.UPLOAD)
    assert policy is not None
    assert policy.requires_approval is True


def test_publish_action_approval_required():
    from scripts.site_engine.site_types import SiteCapability
    from scripts.youtube.site_profile import YOUTUBE_PROFILE
    policy = YOUTUBE_PROFILE.action_policies.get(SiteCapability.PUBLISH)
    assert policy is not None
    assert policy.requires_approval is True


def test_read_not_approval_required():
    from scripts.site_engine.site_types import SiteCapability
    from scripts.youtube.site_profile import YOUTUBE_PROFILE
    policy = YOUTUBE_PROFILE.action_policies.get(SiteCapability.READ)
    assert policy is None or policy.requires_approval is False


def test_gate_upload_plan_returns_result():
    from scripts.youtube.gates import gate_youtube_upload_plan
    from scripts.site_engine.execution_gate import ExecutionGateResult
    result = gate_youtube_upload_plan()
    assert isinstance(result, ExecutionGateResult)


def test_gate_publish_plan_returns_result():
    from scripts.youtube.gates import gate_youtube_publish_plan
    from scripts.site_engine.execution_gate import ExecutionGateResult
    result = gate_youtube_publish_plan()
    assert isinstance(result, ExecutionGateResult)


def test_gate_oauth_returns_result():
    from scripts.youtube.gates import gate_youtube_oauth_required
    from scripts.site_engine.execution_gate import ExecutionGateResult
    result = gate_youtube_oauth_required()
    assert isinstance(result, ExecutionGateResult)


def test_router_import_smoke():
    import scripts.youtube.router  # noqa: F401


def test_validate_no_plain_secret_clean():
    from scripts.youtube.validators import validate_youtube_no_plain_secret
    result = validate_youtube_no_plain_secret({"title": "Local Work", "privacy": "private"})
    assert result.is_valid is True


def test_validate_no_plain_secret_detects_token():
    from scripts.youtube.validators import validate_youtube_no_plain_secret
    result = validate_youtube_no_plain_secret({"token": "abc123secret"})
    assert result.is_valid is False
