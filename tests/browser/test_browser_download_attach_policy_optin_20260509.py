"""browser.download_file / attach_file opt-in 정책 검증."""
from __future__ import annotations

import pytest

from core.agent_runtime.runtime.site_profile.browser_policy_integration import (
    attach_with_policy,
    download_with_policy,
)
from core.agent_runtime.runtime.site_profile.browser_site_registry import (
    SitePolicy,
    clear_all,
    register_site,
)


@pytest.fixture(autouse=True)
def _setup():
    clear_all()
    register_site(SitePolicy(
        site_id="g2b", label="조달청",
        allowed_hosts=("www.g2b.go.kr",),
    ))
    yield
    clear_all()


# --- download tests ---

def test_download_readonly_link_allowed():
    res = download_with_policy(use_policy_registry=True,
                               site_id="g2b",
                               selector_label="공고문 다운로드",
                               expected_extension=".pdf")
    assert res["ok"] is True
    assert res["auto_approve"] is True


def test_download_raw_url_unregistered_blocked():
    res = download_with_policy(use_policy_registry=True,
                               source_url="https://random.example.com/file.pdf")
    assert res["ok"] is False


def test_download_raw_url_registered_host_allowed():
    res = download_with_policy(use_policy_registry=True,
                               source_url="https://www.g2b.go.kr/notice/file.pdf",
                               selector_label="공고문")
    assert res["ok"] is True


def test_download_no_site_blocked():
    res = download_with_policy(use_policy_registry=True)
    assert res["ok"] is False


def test_download_forbidden_label_blocked():
    res = download_with_policy(use_policy_registry=True,
                               site_id="g2b",
                               selector_label="비밀번호")
    assert res["ok"] is False


def test_download_credential_purpose_blocked():
    res = download_with_policy(use_policy_registry=True,
                               site_id="g2b",
                               selector_label="공고",
                               intended_purpose="cookie_capture")
    assert res["ok"] is False


# --- attach tests ---

def test_attach_no_approval_blocked():
    res = attach_with_policy(use_policy_registry=True,
                             site_id="g2b",
                             file_basename="proposal.pdf")
    assert res["ok"] is False
    assert res["required_approval"] is True


def test_attach_with_approval_allowed():
    res = attach_with_policy(use_policy_registry=True,
                             site_id="g2b",
                             file_basename="proposal.pdf",
                             approval_token="tok123")
    assert res["ok"] is True
    assert res["risk_level"] == "MEDIUM"


def test_attach_path_traversal_blocked():
    res = attach_with_policy(use_policy_registry=True,
                             site_id="g2b",
                             file_basename="../../etc/passwd",
                             approval_token="tok")
    assert res["ok"] is False


def test_attach_absolute_path_blocked():
    res = attach_with_policy(use_policy_registry=True,
                             site_id="g2b",
                             file_basename="/home/user/x.pdf",
                             approval_token="tok")
    assert res["ok"] is False


def test_attach_windows_path_blocked():
    res = attach_with_policy(use_policy_registry=True,
                             site_id="g2b",
                             file_basename="C:\\Users\\x.pdf",
                             approval_token="tok")
    assert res["ok"] is False


def test_submit_after_attach_blocked():
    res = attach_with_policy(use_policy_registry=True,
                             site_id="g2b",
                             file_basename="x.pdf",
                             approval_token="tok",
                             submit_after_attach=True)
    assert res["ok"] is False


def test_attach_unknown_site_blocked():
    res = attach_with_policy(use_policy_registry=True,
                             site_id="nonexistent",
                             file_basename="x.pdf",
                             approval_token="tok")
    assert res["ok"] is False


def test_attach_no_basename_blocked():
    res = attach_with_policy(use_policy_registry=True,
                             site_id="g2b",
                             approval_token="tok")
    assert res["ok"] is False
