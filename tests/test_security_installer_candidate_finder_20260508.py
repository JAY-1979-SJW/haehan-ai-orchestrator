"""tests/test_security_installer_candidate_finder_20260508.py"""

from core.agent_runtime.runtime.security_program.security_installer_candidate_finder import (
    find_installer_candidates,
    validate_installer_url,
)

_BASE_PAGE = {
    "url": "https://bank.example.com/install",
    "title": "설치 안내",
    "text_content": "보안프로그램 설치",
    "buttons": ["다운로드"],
    "links": [],
    "form_labels": [],
    "heading_texts": [],
}


def _page_with_links(*links):
    return {**_BASE_PAGE, "links": list(links)}


def test_official_domain_exe_allowed():
    page = _page_with_links("https://bank.example.com/setup.exe")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["allowed"]) == 1
    assert r["server_browser_used"] is False


def test_official_domain_msi_allowed():
    page = _page_with_links("https://bank.example.com/install.msi")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["allowed"]) == 1


def test_unofficial_domain_blocked():
    page = _page_with_links("https://malicious.net/setup.exe")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["allowed"]) == 0
    assert len(r["blocked"]) == 1


def test_bat_extension_blocked():
    page = _page_with_links("https://bank.example.com/install.bat")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["blocked"]) == 1
    assert "차단 확장자" in r["blocked"][0]["block_reason"]


def test_cmd_extension_blocked():
    page = _page_with_links("install.cmd")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["blocked"]) == 1


def test_ps1_extension_blocked():
    page = _page_with_links("install.ps1")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["blocked"]) == 1


def test_js_extension_blocked():
    page = _page_with_links("install.js")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["blocked"]) == 1


def test_vbs_extension_blocked():
    page = _page_with_links("install.vbs")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["blocked"]) == 1


def test_pfx_extension_blocked():
    page = _page_with_links("cert.pfx")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["blocked"]) == 1


def test_pem_extension_blocked():
    page = _page_with_links("key.pem")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["blocked"]) == 1


def test_npki_path_blocked():
    page = _page_with_links("https://bank.example.com/NPKI/setup.exe")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["blocked"]) == 1
    assert "NPKI" in r["blocked"][0]["block_reason"]


def test_shorturl_blocked():
    page = _page_with_links("https://bit.ly/abc123")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["blocked"]) == 1


def test_password_filename_blocked():
    page = _page_with_links("password_setup.exe")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["blocked"]) == 1


def test_zip_needs_extra_approval():
    page = _page_with_links("https://bank.example.com/security.zip")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["allowed"]) == 1
    assert r["allowed"][0]["needs_extra_approval"] is True


def test_subdomain_allowed():
    page = _page_with_links("https://download.bank.example.com/setup.exe")
    r = find_installer_candidates(page, source_host="bank.example.com")
    assert len(r["allowed"]) == 1


def test_validate_installer_url_official():
    r = validate_installer_url("https://bank.example.com/setup.exe", "bank.example.com")
    assert r["allowed"] is True


def test_validate_installer_url_unofficial():
    r = validate_installer_url("https://evil.com/setup.exe", "bank.example.com")
    assert r["allowed"] is False
